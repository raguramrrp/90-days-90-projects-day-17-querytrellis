"""Optional project-isolated local PostgreSQL cluster manager for Windows testing & demos.

Uses installed PostgreSQL ``initdb`` and ``pg_ctl`` binaries to initialize and run
a loopback-only (127.0.0.1) cluster inside ``data/pg_cluster`` without touching
any system-wide PostgreSQL service or credentials.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "pg_cluster"
DEFAULT_LOG_FILE = DEFAULT_DATA_DIR / "server.log"


def _find_pg_bin(exe_name: str) -> str:
    found = shutil.which(exe_name)
    if found:
        return found
    for ver in ("18", "17", "16", "15", "14"):
        candidate = Path(rf"C:\Program Files\PostgreSQL\{ver}\bin\{exe_name}.exe")
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        f"PostgreSQL binary '{exe_name}' was not found on PATH or C:\\Program Files\\PostgreSQL\\*\\bin."
    )


def init_cluster(data_dir: Path, username: str = "postgres") -> None:
    if (data_dir / "PG_VERSION").exists():
        print(f"[OK] Cluster already initialized at {data_dir}")
        return
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    initdb = _find_pg_bin("initdb")
    cmd = [
        initdb,
        "-D",
        str(data_dir),
        "-U",
        username,
        "-A",
        "trust",
        "--encoding=UTF8",
        "--locale=C",
    ]
    subprocess.run(cmd, check=True)
    print(f"[OK] Initialized PostgreSQL cluster at {data_dir} (user={username}, local trust auth).")


def start_cluster(data_dir: Path, port: int = 55432, username: str = "postgres") -> None:
    init_cluster(data_dir, username=username)
    pg_ctl = _find_pg_bin("pg_ctl")
    status = subprocess.run([pg_ctl, "-D", str(data_dir), "status"], capture_output=True, text=True)
    if status.returncode == 0:
        print(f"[OK] Cluster at {data_dir} is already running.")
        return
    opts = f"-p {port} -h 127.0.0.1"
    subprocess.run(
        [pg_ctl, "-D", str(data_dir), "-l", str(DEFAULT_LOG_FILE), "-o", opts, "-w", "start"],
        check=True,
    )
    print(f"[OK] Started local PostgreSQL cluster on 127.0.0.1:{port} (user={username}).")


def stop_cluster(data_dir: Path) -> None:
    if not (data_dir / "PG_VERSION").exists():
        print("[INFO] No local cluster initialized.")
        return
    pg_ctl = _find_pg_bin("pg_ctl")
    subprocess.run([pg_ctl, "-D", str(data_dir), "-m", "fast", "-w", "stop"], check=False)
    print(f"[OK] Stopped local PostgreSQL cluster at {data_dir}.")


def status_cluster(data_dir: Path) -> int:
    if not (data_dir / "PG_VERSION").exists():
        print("[INFO] Local cluster not initialized.")
        return 1
    pg_ctl = _find_pg_bin("pg_ctl")
    res = subprocess.run([pg_ctl, "-D", str(data_dir), "status"], capture_output=True, text=True)
    print(res.stdout.strip() or res.stderr.strip())
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage an isolated local PostgreSQL cluster for QueryTrellis.")
    parser.add_argument("action", choices=["init", "start", "stop", "status"])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--port", type=int, default=55432)
    parser.add_argument("--user", default="postgres")
    args = parser.parse_args()

    try:
        if args.action == "init":
            init_cluster(args.data_dir, username=args.user)
        elif args.action == "start":
            start_cluster(args.data_dir, port=args.port, username=args.user)
        elif args.action == "stop":
            stop_cluster(args.data_dir)
        elif args.action == "status":
            return status_cluster(args.data_dir)
        return 0
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
