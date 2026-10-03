"""Stopping the app: Ctrl+C must always end the process, in seconds, even when a long job is still running inside it."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from app import cli

posix = pytest.mark.skipif(sys.platform == "win32", reason="relies on POSIX signals")


def test_the_countdown_exits_the_process_unless_it_is_cancelled(capsys):
    exits: list[int] = []
    cli.exit_after(0.05, hard_exit=exits.append)
    time.sleep(0.4)
    assert exits == [0] and "Still busy" in capsys.readouterr().err
    cancelled = cli.exit_after(0.2, hard_exit=exits.append)
    cancelled.cancel()
    time.sleep(0.5)
    assert exits == [0]


@posix
def test_the_event_fetcher_treats_the_updaters_terminate_as_ctrl_c(tmp_path, monkeypatch):
    """The updater stops the fetcher with SIGTERM when the app stops; the fetcher must see it as the Ctrl+C it is built to survive."""
    from app.events import fetch

    monkeypatch.setenv("PREM_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    before = signal.getsignal(signal.SIGTERM)

    def read(*args, **kwargs):
        os.kill(os.getpid(), signal.SIGTERM)       # what AutoSync.close() does to it
        time.sleep(2)                              # never reached: the signal raises first
        raise AssertionError("the fetcher carried on after being asked to stop")

    monkeypatch.setattr(fetch, "sync_season", read)
    args = cli.build_parser().parse_args(["events", "sync", "--league", "EPL", "--seasons", "2026", "--data-dir", str(tmp_path)])
    try:
        with pytest.raises(KeyboardInterrupt):
            cli.cmd_events_sync(args)
    finally:
        signal.signal(signal.SIGTERM, before)


DRIVER = """
import asyncio, sys, time
import app.cli as cli
from app.workbench import Workbench

port, data_dir, grace, job = sys.argv[1:5]
cli.SHUTDOWN_GRACE = float(grace)
if job == "stuck":
    started = Workbench.start

    async def start(self):
        await started(self)
        asyncio.get_running_loop().run_in_executor(None, time.sleep, 600)    # a job in a worker thread that nothing can interrupt

    Workbench.start = start
sys.exit(cli.main(["serve", "--demo", "--no-open", "--port", port, "--data-dir", data_dir]))
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(tmp_path, *, grace: float, job: str = "idle") -> tuple[subprocess.Popen, int]:
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-c", DRIVER, str(port), str(tmp_path), str(grace), job], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"the server ended while starting:\n{proc.communicate()[0]}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                return proc, port
        except OSError:
            time.sleep(0.2)
    proc.kill()
    proc.communicate()
    raise AssertionError("the server did not start")


def stop_with_ctrl_c(proc: subprocess.Popen, within: float) -> str:
    """Press Ctrl+C and return what the server printed; fail if it is still running ``within`` seconds later."""
    proc.send_signal(signal.SIGINT)
    try:
        return proc.communicate(timeout=within)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError(f"still running {within:.0f} s after Ctrl+C:\n{proc.communicate()[0]}") from None


@posix
def test_ctrl_c_stops_the_server_quickly_and_cleanly(tmp_path):
    proc, _ = serve(tmp_path, grace=30)
    output = stop_with_ctrl_c(proc, within=15)
    assert proc.returncode == 0 and "Still busy" not in output          # it finished by itself, long before the countdown


@posix
def test_ctrl_c_stops_the_server_even_when_a_long_job_is_still_running_in_it(tmp_path):
    proc, _ = serve(tmp_path, grace=2, job="stuck")        # without the countdown this takes the job's 600 seconds, and more
    output = stop_with_ctrl_c(proc, within=20)
    assert proc.returncode == 0 and "Still busy" in output


@posix
def test_a_server_that_cannot_start_ends_with_an_error_instead_of_waiting(tmp_path):
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    try:
        port = taken.getsockname()[1]
        done = subprocess.run([sys.executable, "-c", DRIVER, str(port), str(tmp_path), "30", "idle"], capture_output=True, text=True, timeout=40, check=False)
    finally:
        taken.close()
    assert done.returncode != 0
