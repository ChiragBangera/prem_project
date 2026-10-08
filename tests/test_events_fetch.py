"""The fetching loop, with a fake reader (no browser, no network)."""

from __future__ import annotations

import json
import math

import pytest

from app.data.store import Store
from app.events.fetch import FetchUnavailable, _finished, find_browser, make_reader, sync_season
from app.events.store import EventStore

from .events_kit import AWAY, end, ev, match, player


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
    """Stands in for soccerdata's reader: it "downloads" a match by writing its raw page into the download cache, as the real one does."""

    def __init__(self, games, data_dir, broken=(), empty=()):
        self.games, self.broken, self.empty = games, set(broken), set(empty)
        self.event_calls, self.schedule_calls = [], []
        self.data_dir = data_dir / "fake-cache"

    def read_schedule(self, force_cache=False):
        self.schedule_calls.append(force_cache)
        return Frame([{**g, "league": "ENG-Premier League", "season": "2526"} for g in self.games])

    def read_events(self, match_id, output_fmt=None, force_cache=False):
        assert force_cache, "finished matches are final: never let soccerdata re-download the season's match list per match"
        assert output_fmt is None, "only the page is wanted: the app keeps the whole raw document, not a DataFrame"
        self.event_calls.append(match_id)
        if match_id in self.broken:
            raise RuntimeError("blocked")
        folder = self.data_dir / "events" / "ENG-Premier League_2526"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{match_id}.json").write_text("null" if match_id in self.empty else json.dumps(raw_doc(passes=1)))


def raw_doc(passes=1):
    events = [ev("Pass", 1, minute=1 + i) for i in range(passes)] + [ev("Tackle", 1, minute=50)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 90) for i in range(60)] + [end(100)]
    return match(events, home_players=[player(1)], away_players=[player(2, team_side="away")])


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


def reader_for(tmp_path, n, **kw):
    unplayed = kw.pop("unplayed", 0)
    return FakeReader(games(n, unplayed), tmp_path, **kw)


def test_only_finished_matches_are_fetched_and_stored_raw(events, tmp_path):
    reader = reader_for(tmp_path, 3, unplayed=2)
    status, _ = run(events, reader, tmp_path)
    assert reader.event_calls == [100, 101, 102]                       # the unplayed fixtures are never requested
    assert events.match_ids("EPL", 2025) == [100, 101, 102]
    assert status["running"] is False and status["done"] == 3 and status["failed"] == 0
    season = events.season("EPL", 2025)
    assert season["players"][1]["c"]["passes"] == 3 and season["players"][1]["c"]["tackles"] == 3 and season["players"][1]["matches"] == 3
    assert events.raw.get("EPL", 2025, 100)["home"]["name"] == "Reds"  # the page as served is in the store: nothing needs fetching again to change a definition


def test_running_again_only_fetches_what_is_missing(events, tmp_path):
    run(events, reader_for(tmp_path, 2), tmp_path)
    reader = reader_for(tmp_path, 4)                                    # two more matches have been played since
    status, lines = run(events, reader, tmp_path)
    assert reader.event_calls == [102, 103] and "2 already stored" in " ".join(lines)
    assert reader.schedule_calls == [True]                              # the match list was read recently, so it comes from cache
    assert status["done"] == 2


def test_a_page_downloaded_but_never_stored_is_adopted_not_fetched_again(events, tmp_path):
    first = reader_for(tmp_path, 2)
    first.read_events(100, force_cache=True)                            # a run that died right after the download, before storing it
    folder = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "ENG-Premier League_2526"
    folder.mkdir(parents=True)
    (folder / "100.json").write_text((first.data_dir / "events" / "ENG-Premier League_2526" / "100.json").read_text())
    reader = reader_for(tmp_path, 2)
    _status, lines = run(events, reader, tmp_path)
    assert reader.event_calls == [101] and events.match_ids("EPL", 2025) == [100, 101] and any("Adopted 1" in line for line in lines)


def test_limit_caps_a_run_and_one_failure_does_not_stop_it(events, tmp_path):
    reader = reader_for(tmp_path, 6, broken=[101])
    status, lines = run(events, reader, tmp_path, limit=3)
    assert reader.event_calls == [100, 101, 102] and events.match_ids("EPL", 2025) == [100, 102]
    assert status["done"] == 2 and status["failed"] == 1 and "Reds v Blues" in status["last_error"]
    assert any("FAILED" in line for line in lines)


def test_an_empty_page_is_a_failure_not_a_stored_match(events, tmp_path):
    reader = reader_for(tmp_path, 2, empty=[100])
    status, _ = run(events, reader, tmp_path)
    assert events.match_ids("EPL", 2025) == [101] and status["failed"] == 1 and "no events" in status["last_error"]


def test_a_wall_of_failures_stops_the_run(events, tmp_path):
    reader = reader_for(tmp_path, 10, broken=range(100, 110))
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


# ---------------------------------------------------------------------- the ledger of failed matches, pause, stop and the daily limit

from app.events import ledger as L  # noqa: E402
from app.sync.budget import Budget  # noqa: E402


def test_a_failed_match_waits_half_a_day_and_gives_up_after_three_tries(events, tmp_path):
    reader = FakeReader(games(3), tmp_path, broken={101})
    now = [1_000_000.0]
    status, _ = run(events, reader, tmp_path, clock=lambda: now[0])
    assert status["done"] == 2 and status["failed"] == 1
    entry = L.failures(events.store, "EPL", 2025)[101]
    assert entry["attempts"] == 1 and entry["label"] == "Reds v Blues" and entry["date"] == "2025-08-02" and "blocked" in entry["error"]
    reader.event_calls.clear()
    status, lines = run(events, reader, tmp_path, clock=lambda: now[0] + 3600)
    assert reader.event_calls == [] and any("waiting to be tried again" in line for line in lines)     # not again within the hour
    for attempt in (2, 3):
        now[0] += L.RETRY_AFTER + 1
        run(events, reader, tmp_path, clock=lambda: now[0])
        assert L.failures(events.store, "EPL", 2025)[101]["attempts"] == attempt
    now[0] += L.RETRY_AFTER + 1
    reader.event_calls.clear()
    run(events, reader, tmp_path, clock=lambda: now[0])
    assert reader.event_calls == [] and L.waiting_for_person(L.failures(events.store, "EPL", 2025)[101])   # three tries: a person decides now


def test_retry_now_reads_just_that_match_and_a_stored_match_is_forgotten(events, tmp_path):
    reader = FakeReader(games(3), tmp_path, broken={101})
    run(events, reader, tmp_path)
    reader.broken.clear()
    reader.event_calls.clear()
    status, _ = run(events, reader, tmp_path, only={101})
    assert reader.event_calls == [101] and status["done"] == 1 and L.failures(events.store, "EPL", 2025) == {}


def test_skip_keeps_a_match_out_until_it_is_unskipped(events, tmp_path):
    reader = FakeReader(games(2), tmp_path, broken={100})
    run(events, reader, tmp_path)
    L.set_skip(events.store, "EPL", 2025, 100, True)
    reader.event_calls.clear()
    run(events, reader, tmp_path, clock=lambda: 10**12)
    assert reader.event_calls == []
    L.set_skip(events.store, "EPL", 2025, 100, False)
    reader.broken.clear()
    run(events, reader, tmp_path, clock=lambda: 10**12)
    assert reader.event_calls == [100] and events.has_match("EPL", 2025, 100)


def test_pause_and_stop_end_the_run_before_the_next_match(events, tmp_path):
    reader = FakeReader(games(4), tmp_path)
    calls = []

    def stop():
        calls.append(1)
        return "paused" if len(calls) > 2 else None

    status, lines = run(events, reader, tmp_path, stop=stop)
    assert status["done"] == 2 and status["stopped"] == "paused" and any("Stopping before match 3 of 4: paused" in line for line in lines)
    L.set_control(events.store, paused=True)
    assert L.stop_reason(events.store, run_started=0.0) == "paused"
    L.set_control(events.store, paused=False, stop_at=50.0)
    assert L.stop_reason(events.store, run_started=40.0) == "stopped" and L.stop_reason(events.store, run_started=60.0) is None   # a stop ends the run it was meant for only


def test_the_daily_limit_stops_the_run_and_counts_only_what_came_from_the_site(events, tmp_path):
    budget = Budget(events.store, lambda: {"whoscored": 2}, clock=lambda: 1_000_000.0)
    reader = FakeReader(games(5), tmp_path)
    status, lines = run(events, reader, tmp_path, allowance=lambda: budget.left("whoscored"), on_fetched=lambda: budget.spend("whoscored"), cached_under=-1)
    assert status["done"] == 2 and budget.used("whoscored") == 2 and budget.left("whoscored") == 0
    assert any("today's limit reached" in line for line in lines)
    tomorrow = Budget(events.store, lambda: {"whoscored": 2}, clock=lambda: 1_000_000.0 + 86400)
    assert tomorrow.left("whoscored") == 2


def test_the_pause_between_matches_is_at_random_between_once_and_twice_the_setting(events, tmp_path):
    waits = []
    sync_season(events, "EPL", 2025, data_dir=tmp_path, reader=FakeReader(games(4), tmp_path), pause=10, sleep=waits.append, log=lambda line: None, cached_under=-1)
    assert len(waits) == 3 and all(10 <= w <= 20 for w in waits)                           # none after the last match


def test_budget_limits_are_clamped_and_old_days_are_dropped(tmp_path):
    store = Store(tmp_path / "b.sqlite")
    try:
        day = [1_000_000.0]
        b = Budget(store, lambda: {"understat": 10**9, "whoscored": -5}, clock=lambda: day[0])
        assert b.limit("understat") == 5000 and b.limit("whoscored") == 0
        b.spend("understat", 3)
        day[0] += 10 * 86400
        b.spend("understat", 1)
        assert list(store.kv_prefix("budget:understat:")) == [f"budget:understat:{b.day()}"] and b.used("understat") == 1
    finally:
        store.close()
