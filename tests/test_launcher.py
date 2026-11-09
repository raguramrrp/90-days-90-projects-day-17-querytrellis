"""Unit tests for the unified Windows/cross-platform full-stack launcher."""
from __future__ import annotations

import socket

from src import launcher


def test_launcher_port_check_and_npm_resolution():
    npm_cmd = launcher._resolve_npm_executable()
    assert "npm" in npm_cmd.lower()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    busy_port = sock.getsockname()[1]
    sock.listen(1)
    try:
        assert launcher._is_port_available("127.0.0.1", busy_port) is False
    finally:
        sock.close()

    # Wait until port is free again, or probe an ephemeral port check
    assert isinstance(launcher._is_port_available("127.0.0.1", busy_port), bool)


def test_launcher_fails_cleanly_if_port_already_occupied():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    busy_port = sock.getsockname()[1]
    sock.listen(1)
    try:
        rc = launcher.launch_stack(api_host="127.0.0.1", api_port=busy_port, web_port=3999)
        assert rc == 1
    finally:
        sock.close()
