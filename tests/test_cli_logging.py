"""The server keeps its own log in the data folder, so a problem seen in the browser can be traced even when it was started in the background."""

from __future__ import annotations

import logging

import pytest

from app.cli import configure_logging


@pytest.fixture
def clean_root():
    root = logging.getLogger()
    before = (list(root.handlers), root.level)
    yield root
    for handler in list(root.handlers):
        if handler not in before[0]:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(before[1])


def test_what_the_app_logs_lands_in_the_data_folder_with_its_traceback(tmp_path, clean_root):
    path = configure_logging(tmp_path)
    assert path == tmp_path / "logs" / "server.log"
    try:
        raise ValueError("a bad row")
    except ValueError:
        logging.getLogger("prem.api").exception("unhandled error")
    logging.getLogger("prem.autosync").info("cycle done: 0 match pages fetched, 0 problems")
    for handler in clean_root.handlers:
        handler.flush()
    text = path.read_text()
    assert "ERROR prem.api: unhandled error" in text and "ValueError: a bad row" in text
    assert "INFO prem.autosync: cycle done" in text


def test_a_folder_that_cannot_be_written_does_not_stop_the_server(tmp_path, clean_root):
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    assert configure_logging(blocked) is None                       # the data "folder" is a file: no log, no crash
