"""Unified full-stack Windows/cross-platform launcher for QueryTrellis Studio.

Starts FastAPI (:8000) and Next.js (:3000) inside one supervised console session,
streams `[API]` and `[WEB]` logs cleanly, waits for readiness probes on both
services, and terminates both process trees cleanly on Ctrl+C or child failure.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _is_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _bootstrap_workspace() -> None:
    (PROJECT_ROOT / "data" / "sandboxes").mkdir(parents=True, exist_ok=True)
    env_file = PROJECT_ROOT / ".env"
    env_example = PROJECT_ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy2(env_example, env_file)
        print("[INIT] Created .env from .env.example")

    load_dotenv(env_file, override=False)

    from src.connectors.demo_sandbox import ensure_demo_duckdb, ensure_sample_export_files

    ensure_demo_duckdb()
    ensure_sample_export_files()


def _resolve_npm_executable() -> str:
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    return shutil.which("npm") or "npm"


def _stream_output(proc: subprocess.Popen, prefix: str) -> None:
    if proc.stdout is None:
        return
    try:
        for line in proc.stdout:
            text = line.rstrip("\r\n")
            if text:
                print(f"[{prefix}] {text}", flush=True)
    except Exception:
        pass


def _kill_proc_tree(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=4.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _wait_http_ok(
    url: str,
    proc: subprocess.Popen,
    name: str,
    timeout_s: float = 35.0,
) -> bool:
    deadline = time.time() + timeout_s
    with httpx.Client(timeout=2.0) as client:
        while time.time() < deadline:
            if proc.poll() is not None:
                print(f"[ERROR] {name} exited early with code {proc.returncode}.", flush=True)
                return False
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.4)
    print(f"[ERROR] Timed out waiting for {name} at {url}.", flush=True)
    return False


def launch_stack(
    dev_mode: bool = False,
    api_host: Optional[str] = None,
    api_port: Optional[int] = None,
    web_port: Optional[int] = None,
) -> int:
    _bootstrap_workspace()

    resolved_api_host = api_host if api_host is not None else os.getenv("QT_API_HOST", "127.0.0.1")
    resolved_api_port = api_port if api_port is not None else int(os.getenv("QT_API_PORT", "8000"))
    resolved_web_port = web_port if web_port is not None else int(os.getenv("QT_WEB_PORT", "3000"))

    if not _is_port_available(resolved_api_host, resolved_api_port):
        print(
            f"[ERROR] Port {resolved_api_port} on {resolved_api_host} is already in use. "
            f"Close any existing QueryTrellis/API server window first, or set QT_API_PORT in .env.",
            flush=True,
        )
        return 1

    if not _is_port_available("127.0.0.1", resolved_web_port):
        print(
            f"[ERROR] Port {resolved_web_port} on 127.0.0.1 is already in use. "
            f"Close any existing Next.js/web server first before relaunching.",
            flush=True,
        )
        return 1

    frontend_dir = PROJECT_ROOT / "frontend"
    if not (frontend_dir / "node_modules").exists():
        print("[ERROR] Frontend packages (frontend/node_modules) missing. Run setup.bat first.", flush=True)
        return 1

    use_dev = dev_mode or not (frontend_dir / ".next" / "BUILD_ID").exists()
    web_script = "dev" if use_dev else "start"
    npm_exe = _resolve_npm_executable()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["QT_INTERNAL_API_URL"] = f"http://{resolved_api_host}:{resolved_api_port}"
    env.setdefault("NEXT_PUBLIC_API_URL", f"http://{resolved_api_host}:{resolved_api_port}")

    api_proc: Optional[subprocess.Popen] = None
    web_proc: Optional[subprocess.Popen] = None

    try:
        print(f"[*] Starting FastAPI backend on http://{resolved_api_host}:{resolved_api_port} ...", flush=True)
        api_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.main:app",
                "--host",
                resolved_api_host,
                "--port",
                str(resolved_api_port),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=_stream_output, args=(api_proc, "API"), daemon=True).start()

        if not _wait_http_ok(
            f"http://{resolved_api_host}:{resolved_api_port}/api/health", api_proc, "FastAPI backend"
        ):
            return 1

        print(f"[*] Starting Next.js UI ({web_script} mode) on http://127.0.0.1:{resolved_web_port} ...", flush=True)
        web_proc = subprocess.Popen(
            [
                npm_exe,
                "--prefix",
                "frontend",
                "run",
                web_script,
                "--",
                "-p",
                str(resolved_web_port),
                "-H",
                "127.0.0.1",
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=_stream_output, args=(web_proc, "WEB"), daemon=True).start()

        if not _wait_http_ok(
            f"http://127.0.0.1:{resolved_web_port}/", web_proc, "Next.js frontend", timeout_s=45.0
        ):
            return 1

        print("", flush=True)
        print("======================================================================", flush=True)
        print("  QueryTrellis Studio is LIVE!", flush=True)
        print(f"    Workbench UI : http://127.0.0.1:{resolved_web_port}", flush=True)
        print(f"    API Docs     : http://{resolved_api_host}:{resolved_api_port}/docs", flush=True)
        print("    Legacy PG UI : .\\.venv\\Scripts\\python.exe -m streamlit run app/main.py", flush=True)
        print("    Press Ctrl+C to stop both services cleanly.", flush=True)
        print("======================================================================", flush=True)
        print("", flush=True)

        while True:
            time.sleep(0.5)
            if api_proc.poll() is not None:
                print(f"[ERROR] FastAPI backend stopped unexpectedly (code {api_proc.returncode}).", flush=True)
                return 1
            if web_proc.poll() is not None:
                print(f"[ERROR] Next.js UI stopped unexpectedly (code {web_proc.returncode}).", flush=True)
                return 1
    except KeyboardInterrupt:
        print("\n[*] Shutting down QueryTrellis Studio cleanly...", flush=True)
        return 0
    finally:
        _kill_proc_tree(web_proc)
        _kill_proc_tree(api_proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch QueryTrellis Studio full-stack services.")
    parser.add_argument("--dev", action="store_true", help="Force Next.js development server.")
    args = parser.parse_args()
    return launch_stack(dev_mode=args.dev)


if __name__ == "__main__":
    sys.exit(main())
