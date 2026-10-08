"""Steering the event data by hand: the review of what could not be matched, a person's own links, retry, skip, pause and stop, over the API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.events import ledger


class Client:
    """The app over HTTP, and its workbench, for one test."""

    def __init__(self, tmp_path):
        from tests.conftest import FakeProvider, raw_league

        settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=False, min_interval=0, page_pace=0)
        self.app = create_app(settings, provider=FakeProvider(raw_league(played=3)))
        self.http = TestClient(self.app)

    def __enter__(self):
        self.http.__enter__()
        return self.http, self.app.state.wb

    def __exit__(self, *exc):
        return self.http.__exit__(*exc)


def test_overrides_win_and_can_be_undone(tmp_path):
    with Client(tmp_path) as (http, wb):
        wb.links.set_override("EPL", 2026, "players", 77, 5)
        wb.links.set_override("EPL", 2026, "players", 78, 5)          # one Understat player belongs to one WhoScored player: the later choice wins
        assert wb.links.overrides("EPL", 2026)["players"] == {78: 5}
        wb.links.set_override("EPL", 2026, "players", 79, 0)          # not in Understat: leave him out
        wb.links.set_override("EPL", 2026, "players", 78, None)       # undo
        assert wb.links.overrides("EPL", 2026)["players"] == {79: 0}
        response = http.put("/api/events/link", json={"league": "EPL", "season": 2026, "kind": "matches", "ws": 5, "us": 0})
        assert response.status_code >= 400                              # a match can only be linked to a fixture


def test_retry_skip_pause_and_stop_over_the_api(tmp_path):
    with Client(tmp_path) as (http, wb):
        ledger.note_failure(wb.store, "EPL", 2026, 4242, label="A v B", date="2026-08-20", error="blocked", now=1.0)
        assert http.post("/api/events/skip", json={"league": "EPL", "season": 2026, "game": 4242, "skip": True}).json()["entry"]["skip"] is True
        queue = http.post("/api/events/retry", json={"league": "EPL", "season": 2026, "game": 4242}).json()["queue"]
        assert queue == [{"league": "EPL", "season": 2026, "game": 4242}] and ledger.failures(wb.store, "EPL", 2026)[4242]["skip"] is False   # asking again un-skips
        assert http.post("/api/events/pause", json={"paused": True}).json()["control"]["paused"] is True
        assert http.post("/api/events/stop").json()["control"]["stop_at"] > 0
        state = http.get("/api/data/auto").json()
        assert state["events"]["control"]["paused"] is True and state["budget"]["whoscored"]["limit"] == 40 and isinstance(state["plan"], list)
        review = http.get("/api/events/review", params={"league": "EPL", "season": 2026}).json()
        assert [f["game"] for f in review["failed"]] == [4242] and review["failed"][0]["label"] == "A v B"
