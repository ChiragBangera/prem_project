"""What a first-time user meets when the port they asked for is already taken."""

from __future__ import annotations

import os
import socket
import subprocess
import sys


def run(args: list[str], tmp_path, **env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "app.cli", *args], capture_output=True, text=True, timeout=90, env={**os.environ, "PREM_DATA_DIR": str(tmp_path), **env})


def test_a_taken_port_says_so_and_how_to_pick_another(tmp_path):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        done = run(["serve", "--demo", "--no-open", "--port", str(port)], tmp_path)
    assert done.returncode == 3
    assert f"port {port} is probably in use" in done.stderr and f"prem serve --port {port + 1}" in done.stderr
