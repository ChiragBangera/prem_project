"""Following matches: favourite teams that survive everything, half-time reads for the matches you follow, and the live match view."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from app.config import Settings
from app.data import matchclock
from app.errors import BadRequest
from app.events import ledger
from app.sync.autosync import AutoSync
from app.workbench import Workbench

from .conftest import FakeProvider, raw_league
from .events_kit import AWAY, end, ev, match, player

TODAY = date(2026, 10, 2)
ROUND_TWO = 1755961200.0     # 2025-08-23 15:00 UTC: fixtures 1002 (Alpha FC's, played) and 1003 (not yet) kick off; the fake serves them for 2026


def make(tmp_path):
    settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=True, min_interval=0, page_pace=0)
    wb = Workbench(settings, provider=FakeProvider(raw_league(played=3)), today=TODAY)
    wb.enricher.schedule_rosters = lambda targets: 0
    return wb


def run(coro):
    return asyncio.run(coro)


def events_on(wb, monkeypatch, spawned):
    async def spawn(*cmd, **kw):
        spawned.append(cmd)

        class Done:
            returncode = 0

            async def wait(self):
                return 0

        return Done()

    wb.auto._spawn = spawn
    monkeypatch.setattr(AutoSync, "events_capability", staticmethod(lambda: {"available": True, "reason": None, "browser": "/bin/true"}))
    wb.auto.set_prefs({"events": {"enabled": True, "leagues": ["EPL"], "seasons_back": 0}})


def targets(cmd):
    return json.loads(cmd[cmd.index("--targets") + 1]) if "--targets" in cmd else None


def fixture(wb, fid):
    return next(f for f in wb.repo.cached_league("EPL", 2026).fixtures if f.id == fid)


# ------------------------------------------------------------------ favourite teams


def test_favourite_teams_are_kept_through_a_restart_a_cache_clear_and_a_second_add(tmp_path):
    async def go():
        wb = make(tmp_path)
        try:
            wb.favourites.set("EPL", "Alpha FC", True)
            wb.favourites.set("EPL", "Alpha FC", True)                        # twice: still one entry
            wb.favourites.set("La_liga", "Beta United", True)
            assert [(t["league"], t["team"]) for t in wb.favourites.teams()] == [("EPL", "Alpha FC"), ("La_liga", "Beta United")]
            wb.store.clear()                                                   # "clear the cache" deletes stored pages, never settings
        finally:
            await wb.close()
        again = make(tmp_path)                                                 # a restart
        try:
            assert again.favourites.follows("EPL", "Alpha FC") and again.favourites.follows("La_liga", "Beta United")
            assert not again.favourites.follows("La_liga", "Alpha FC")         # a favourite belongs to its league
            again.favourites.set("EPL", "Alpha FC", False)
            assert [t["team"] for t in again.favourites.teams()] == ["Beta United"]
            with pytest.raises(BadRequest):
                again.favourites.set("Eredivisie", "Ajax", True)
            with pytest.raises(BadRequest):
                again.favourites.set("EPL", "  ", True)
        finally:
            await again.close()

    run(go())


# ------------------------------------------------------------------ half-time reads


def test_a_favourite_teams_match_is_read_at_half_time_first_and_again_at_full_time(tmp_path, monkeypatch):
    async def go():
        wb = make(tmp_path)
        spawned = []
        events_on(wb, monkeypatch, spawned)
        now = [ROUND_TWO + 20 * 60]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.repo.league("EPL", 2026)
            f = fixture(wb, 1003)
            wb.favourites.set("EPL", f.home, True)
            due, later = wb.auto.matchday(now[0])
            assert due == {} and (ROUND_TWO + matchclock.HALF_TIME, f"half-time event data of {f.home} v {f.away}") in later
            other = fixture(wb, 1002)
            assert not any(why == f"half-time event data of {other.home} v {other.away}" for _at, why in later)   # not followed: full time only
            now[0] = ROUND_TWO + matchclock.HALF_TIME + 60
            await wb.auto.run_once()
            assert targets(spawned[0]) == [{"fixture": 1003, "kickoff": f.dt, "home": f.home, "away": f.away, "moment": "ht"}]   # only the followed one
            for _ in range(3):
                await asyncio.sleep(0)
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=7, state="live", at=now[0], moment="ht", elapsed="HT")
            now[0] += 5 * 60
            assert wb.auto.matchday(now[0])[0] == {}                           # one half-time read is enough
            now[0] = ROUND_TWO + matchclock.FULL_TIME + 60
            await wb.auto.run_once()
            assert {(t["fixture"], t["moment"]) for t in targets(spawned[1])} == {(1002, "ft"), (1003, "ft")}   # and every match at full time
        finally:
            await wb.close()

    run(go())


def test_opening_a_match_while_it_is_played_follows_it_and_only_then(tmp_path, monkeypatch):
    async def go():
        wb = make(tmp_path)
        spawned = []
        events_on(wb, monkeypatch, spawned)
        now = [ROUND_TWO - 3 * 86400]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.repo.league("EPL", 2026)
            await wb.matches.live(1003, "EPL", "2026", follow=True)          # days before: opening it follows nothing
            assert wb.auto.followed("EPL", 2026, fixture(wb, 1003)) is None
            now[0] = ROUND_TWO + 10 * 60
            view = await wb.matches.live(1003, "EPL", "2026", follow=True)
            assert view["followed"] == "opened" and view["phase"] == "first_half"
            assert view["next_read"] == {"at": ROUND_TWO + matchclock.HALF_TIME, "moment": "ht"}
            now[0] = ROUND_TWO + matchclock.HALF_TIME + 30
            due, _later = wb.auto.matchday(now[0])
            assert [(t["fixture"], t["moment"]) for t in due[("EPL", 2026)]] == [(1003, "ht")]
            plain = await wb.matches.live(1002, "EPL", "2026")                 # looked at without following
            assert plain["followed"] is None and plain["next_read"]["moment"] == "ft"
        finally:
            await wb.close()

    run(go())


# ------------------------------------------------------------------ the live match view


def ht_doc(elapsed="HT", status=3, score="1 : 0"):
    events = [ev("Pass", 1, minute=1 + i % 45) for i in range(40)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 45) for i in range(20)]
    events += [ev("Tackle", 2, team=AWAY, minute=30)] + ([end(95)] if elapsed == "FT" else [])
    doc = match(events, home_players=[player(1, name="Home Ten")], away_players=[player(2, team_side="away", name="Away Six")], score=score)
    return {**doc, "elapsed": elapsed, "statusCode": status}


def test_the_live_view_shows_the_provisional_half_time_read_and_then_the_final_one(tmp_path, monkeypatch):
    async def go():
        wb = make(tmp_path)
        events_on(wb, monkeypatch, [])
        now = [ROUND_TWO + 55 * 60]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.repo.league("EPL", 2026)
            empty = await wb.matches.live(1003, "EPL", "2026")
            assert empty["phase"] == "half_time" and empty["read"] is None and empty["events_on"] is True
            assert wb.events.ingest("EPL", 2026, 77, ht_doc()) == "live"
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=77, state="live", at=now[0], moment="ht", elapsed="HT", score="1 : 0")
            view = await wb.matches.live(1003, "EPL", "2026")
            read = view["read"]
            assert read["final"] is False and read["elapsed"] == "HT" and read["score"] == "1 : 0"
            assert read["stats"]["poss"] == [67, 33] and {r["key"]: (r["home"], r["away"]) for r in read["stats"]["rows"]}["tackles"] == (0, 1)
            assert read["players"]["home"][0]["name"] == "Home Ten" and read["players"]["away"][0]["tackles"] == 1
            assert wb.events.match_ids("EPL", 2026) == []                      # nothing counted anywhere else
            now[0] = ROUND_TWO + matchclock.FULL_TIME + 60
            assert wb.events.ingest("EPL", 2026, 77, ht_doc("FT", 6, "2 : 0")) == "final"
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, state="final", at=now[0], moment="ft", elapsed="FT", score="2 : 0")
            final = await wb.matches.live(1003, "EPL", "2026")
            assert final["read"]["final"] is True and final["read"]["score"] == "2 : 0" and final["next_read"] is None
            assert final["phase"] == "full_time" and wb.events.match_ids("EPL", 2026) == [77]
        finally:
            await wb.close()

    run(go())


def test_with_event_data_off_the_live_view_says_so_and_follows_nothing(tmp_path):
    async def go():
        wb = make(tmp_path)
        wb.auto._clock = lambda: ROUND_TWO + 10 * 60
        try:
            await wb.repo.league("EPL", 2026)
            view = await wb.matches.live(1003, "EPL", "2026", follow=True)
            assert view["events_on"] is False and view["followed"] is None and view["next_read"] is None
            assert wb.store.kv_get("autosync:followed") is None
        finally:
            await wb.close()

    run(go())
