"""The fetching loop, with a fake reader (no browser, no network)."""

from __future__ import annotations

import math
import time

import pytest

from app.data.store import Store
from app.events.fetch import FetchUnavailable, _finished, find_browser, make_reader, sync_season
from app.events.store import EventStore


class Frame:
    """Just enough of a DataFrame: reset_index().to_dict("records")."""

    def __init__(self, rows):
        self.rows = rows

    def reset_index(self):
        return self

    def to_dict(self, orient):
        assert orient == "records"
        return self.rows


def match_events(pid=1):
    base = {"outcome_type": "Successful", "team": "Reds", "team_id": 1, "x": 30.0, "y": 50.0, "end_x": 40.0, "end_y": 50.0, "period": "FirstHalf",
            "is_touch": True, "qualifiers": [], "player": f"P{pid}", "player_id": float(pid)}
    return [{**base, "type": "Pass", "expanded_minute": 5}, {**base, "type": "Tackle", "expanded_minute": 50}, {**base, "type": "End", "expanded_minute": 100, "player_id": math.nan}]


class FakeReader:
    def __init__(self, games, broken=()):
        self.games, self.broken = games, set(broken)
        self.event_calls, self.schedule_calls = [], []

    def read_schedule(self, force_cache=False):
        self.schedule_calls.append(force_cache)
        return Frame(self.games)

    def read_events(self, match_id, output_fmt="events", force_cache=False):
        assert force_cache, "finished matches are final: never let soccerdata re-download the season's match list per match"
        self.event_calls.append(match_id)
        if match_id in self.broken:
            raise RuntimeError("blocked")
        return Frame(match_events(1))   # the same player turns up in every match, so his totals add up


def games(n, unplayed=0):
    out = [{"game_id": 100 + i, "home_team": "Reds", "away_team": "Blues", "home_score": 1, "away_score": 0, "date": f"2025-08-{i + 1:02d}"} for i in range(n)]
    return out + [{"game_id": 900 + i, "home_team": "A", "away_team": "B", "home_score": math.nan, "away_score": math.nan, "date": "2026-05-01"} for i in range(unplayed)]


@pytest.fixture()
def events(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    yield EventStore(store)
    store.close()


def run(events, reader, tmp_path, **kw):
    lines = []
    status = sync_season(events, "EPL", 2025, data_dir=tmp_path, reader=reader, pause=0, sleep=lambda s: None, log=lines.append, **kw)
    return status, lines


def test_only_finished_matches_are_fetched_and_stored(events, tmp_path):
    reader = FakeReader(games(3, unplayed=2))
    status, _ = run(events, reader, tmp_path)
    assert reader.event_calls == [100, 101, 102]                       # the unplayed fixtures are never requested
    assert sorted(events.match_ids("EPL", 2025)) == [100, 101, 102]
    assert status["running"] is False and status["done"] == 3 and status["failed"] == 0
    totals = events.season_totals("EPL", 2025)
    assert totals[1]["passes"] == 3 and totals[1]["tackles"] == 3 and totals[1]["min"] == 270.0 and totals[1]["matches"] == 3


def test_running_again_only_fetches_what_is_missing(events, tmp_path):
    run(events, FakeReader(games(2)), tmp_path)
    reader = FakeReader(games(4))                                       # two more matches have been played since
    status, lines = run(events, reader, tmp_path)
    assert reader.event_calls == [102, 103] and "2 already stored" in " ".join(lines)
    assert reader.schedule_calls == [True]                              # the match list was read recently, so it comes from cache
    assert status["done"] == 2


def test_matches_stored_in_an_older_format_are_read_again(events, tmp_path):
    events.store.put("events", "EPL:2025:100", {"v": 1, "game": 100, "rows": []}, source="whoscored", complete=True)
    reader = FakeReader(games(2))
    run(events, reader, tmp_path)
    assert reader.event_calls == [100, 101] and events.has_current_match("EPL", 2025, 100)


def test_limit_caps_a_run_and_one_failure_does_not_stop_it(events, tmp_path):
    reader = FakeReader(games(6), broken=[101])
    status, lines = run(events, reader, tmp_path, limit=3)
    assert reader.event_calls == [100, 101, 102] and sorted(events.match_ids("EPL", 2025)) == [100, 102]
    assert status["done"] == 2 and status["failed"] == 1 and "101" not in status["last_error"] and "Reds v Blues" in status["last_error"]
    assert any("FAILED" in line for line in lines)


def test_a_wall_of_failures_stops_the_run(events, tmp_path):
    reader = FakeReader(games(10), broken=range(100, 110))
    status, lines = run(events, reader, tmp_path, max_failures=3)
    assert len(reader.event_calls) == 3 and status["failed"] == 3 and status["running"] is False
    assert "blocking" in lines[-1]


def test_a_reader_that_cannot_start_is_reported_not_raised(events, tmp_path):
    class NoBrowser:
        def read_schedule(self, force_cache=False):
            raise RuntimeError("chrome not found")

    with pytest.raises(RuntimeError):
        run(events, NoBrowser(), tmp_path)
    assert events.status("EPL", 2025)["running"] is False            # and it never stays marked as running


def test_helpers():
    assert [r["game_id"] for r in _finished(games(2, unplayed=3))] == [100, 101]
    with pytest.raises(FetchUnavailable):
        make_reader("Nonexistent_League", 2025, data_dir=__import__("pathlib").Path("."))
    assert find_browser() is None or isinstance(find_browser(), str)
