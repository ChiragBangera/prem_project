"""The browser opens when the server is listening, not on a timer."""

from __future__ import annotations

import socket
import threading
import time

from app import cli


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_browser_waits_until_the_server_listens(monkeypatch):
    port = _free_port()
    opened: list[float] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(time.monotonic()))
    worker = threading.Thread(target=cli._open_when_up, args=(f"http://127.0.0.1:{port}/", "127.0.0.1", port))
    worker.start()
    time.sleep(0.5)
    assert opened == []                          # nothing listens yet, so the browser is held back
    before_listening = time.monotonic()
    with socket.socket() as server:
        server.bind(("127.0.0.1", port))
        server.listen()
        worker.join(timeout=10)
    assert len(opened) == 1 and opened[0] >= before_listening


def test_browser_opens_anyway_when_the_server_never_listens(monkeypatch):
    port = _free_port()
    opened: list[str] = []
    monkeypatch.setattr(cli, "OPEN_WAIT", 0.3)
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    cli._open_when_up(f"http://127.0.0.1:{port}/", "127.0.0.1", port)
    assert opened == [f"http://127.0.0.1:{port}/"]
