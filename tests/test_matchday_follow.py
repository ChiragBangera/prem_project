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
            assert due == {} and (ROUND_TWO + matchclock.HT_READ, f"half-time event data of {f.home} v {f.away}") in later
            other = fixture(wb, 1002)
            assert not any(why == f"half-time event data of {other.home} v {other.away}" for _at, why in later)   # not followed: full time only
            now[0] = ROUND_TWO + matchclock.HT_READ + 60
            await wb.auto.run_once()
            assert targets(spawned[0]) == [{"fixture": 1003, "kickoff": f.dt, "home": f.home, "away": f.away, "moment": "ht"}]   # only the followed one
            for _ in range(3):
                await asyncio.sleep(0)
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=7, state="live", at=now[0], moment="ht", elapsed="HT")
            now[0] += 5 * 60
            assert wb.auto.matchday(now[0])[0] == {}                           # one half-time read is enough
            now[0] = ROUND_TWO + matchclock.FT_READ + 60
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
            assert view["next_read"] == {"at": ROUND_TWO + matchclock.HT_READ, "moment": "ht"}
            now[0] = ROUND_TWO + matchclock.HT_READ + 30
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
            players = {r["name"]: r for r in read["players"]}
            assert players["Home Ten"]["side"] == "home" and players["Away Six"]["side"] == "away" and players["Away Six"]["tackles"] == 1
            assert read["lineups"]["home"][0]["name"] == "Home Ten" and read["lineups"]["away"][0]["start"] is True
            assert read["shots"] == {"home": [], "away": []} and read["timeline"] == []
            assert wb.events.match_ids("EPL", 2026) == []                      # nothing counted anywhere else
            now[0] = ROUND_TWO + matchclock.FT_READ + 60
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


def test_a_half_time_read_that_caught_the_end_of_the_first_half_is_made_again_in_the_break(tmp_path, monkeypatch):
    """Seen on the first real match: read at 47 minutes, WhoScored's page still said "45+" (stoppage time). Read at 45 minutes, and again
    every three minutes while the page says first half, until it says HT or the second half starts."""
    async def go():
        wb = make(tmp_path)
        spawned = []
        events_on(wb, monkeypatch, spawned)
        now = [ROUND_TWO + 44 * 60]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.repo.league("EPL", 2026)
            wb.favourites.set("EPL", fixture(wb, 1003).home, True)
            assert wb.auto.matchday(now[0])[0] == {}                                     # 44 minutes: the first half is still on
            now[0] = ROUND_TWO + matchclock.HT_READ
            assert [t["moment"] for t in wb.auto.matchday(now[0])[0][("EPL", 2026)]] == ["ht"]
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=7, state="live", at=now[0], moment="ht", elapsed="45+")
            now[0] += 60
            assert wb.auto.matchday(now[0])[0] == {}                                     # not every minute ...
            now[0] += matchclock.HT_RETRY
            assert [t["moment"] for t in wb.auto.matchday(now[0])[0][("EPL", 2026)]] == ["ht"]   # ... but again three minutes on
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, state="live", at=now[0], moment="ht", elapsed="HT")
            now[0] += matchclock.HT_RETRY
            assert wb.auto.matchday(now[0])[0] == {}                                     # the page said HT: that is the half-time read
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, elapsed="45+")
            now[0] = ROUND_TWO + matchclock.HT_READ_LAST
            assert wb.auto.matchday(now[0])[0] == {}                                     # and never once the second half has started
            assert wb.auto.matchday_allowance() == 4 * 2 + 6 + 10                         # room for a favourite's extra half-time reads
        finally:
            await wb.close()

    run(go())


def test_the_live_view_reads_shots_goals_cards_substitutions_and_line_ups_from_the_page(tmp_path, monkeypatch):
    from app.workbench.pages.matches import _live_detail

    doc = ht_doc()
    q = lambda *names: [{"type": {"displayName": n}} for n in names]   # noqa: E731
    doc["playerIdNameDictionary"] = {"1": "Home Ten", "2": "Away Six"}
    doc["events"] += [
        {**ev("SavedShot", 1, minute=20, x=88.0, y=40.0), "qualifiers": q("Head", "FromCorner")},
        {**ev("Goal", 1, minute=33, x=94.0, y=52.0), "qualifiers": q("RightFoot", "RegularPlay")},
        {**ev("Goal", 2, team=AWAY, minute=40, x=5.0, y=50.0), "qualifiers": q("OwnGoal")},
        {**ev("Card", 2, team=AWAY, minute=41, x=None, y=None), "qualifiers": q("Yellow")},
        {**ev("SubstitutionOn", 2, team=AWAY, minute=44, x=None, y=None)},
    ]
    out = _live_detail(doc)
    assert [(s["minute"], s["result"], s["situation"], s["type"]) for s in out["shots"]["home"]] == [(21, "SavedShot", "From a corner", "Head"), (34, "Goal", "Open play", "Right foot")]
    assert out["shots"]["away"] == [] and out["shots"]["home"][1]["x"] == 0.94 and out["shots"]["home"][1]["xg"] is None   # an own goal is not a shot
    assert [(t["minute"], t["kind"], t["side"], t["player"]) for t in out["timeline"]] == [
        (34, "goal", "home", "Home Ten"), (41, "own_goal", "home", "Away Six"), (42, "yellow", "away", "Away Six"), (45, "sub", "away", "Away Six")]


# ------------------------------------------------------------------ the full match page from a WhoScored read


def page_doc(elapsed="HT", status=3, score="1 : 0"):
    """A half-time page with a goal (assisted), a saved header from a corner marked a big chance, an own goal and a yellow card."""
    q = lambda *names: [{"type": {"displayName": n}} for n in names]   # noqa: E731
    doc = ht_doc(elapsed, status, score)
    doc["playerIdNameDictionary"] = {"1": "Home Ten", "2": "Away Six"}
    pass_ = {**ev("Pass", 1, minute=32, x=80.0, y=60.0), "eventId": 900, "qualifiers": q("Cross")}
    doc["events"] = doc["events"] + [
        pass_,
        {**ev("Goal", 1, minute=33, x=94.0, y=52.0), "qualifiers": q("RightFoot", "RegularPlay", "Assisted") + [{"type": {"displayName": "RelatedEventId"}, "value": "900"}]},
        {**ev("SavedShot", 1, minute=20, x=90.0, y=45.0), "qualifiers": q("Head", "FromCorner", "BigChance")},
        {**ev("Card", 2, team=AWAY, minute=41, x=None, y=None), "qualifiers": q("Yellow")},
    ]
    return doc


def test_a_whoscored_page_becomes_the_full_report_with_nothing_made_up():
    from app.analytics.live_page import live_match_page, live_report, score
    from app.data.models import Fixture

    doc = page_doc()
    fx = Fixture(id=5, dt="2026-10-10 14:00:00", home="Reds", away="Blues", home_short="RED", away_short="BLU", played=False, hg=1, ag=0)
    page = live_match_page(doc, match_id=5, season=2026, home="Reds", away="Blues", date="2026-10-10", understat_id={1: 101}.get)
    report = live_report(fx, page, doc)
    json.dumps(report, allow_nan=False)                                                      # no NaN anywhere
    assert score(doc) == (1, 0) and report["has_xg"] is False and report["deserved"] is None and report["timeline"] is None
    assert report["fixture"]["hxg"] is None and report["summary"]["home"]["xg"] is None and report["summary"]["home"]["shots"] == 2
    assert report["summary"]["home"]["big_chances"] == 1 and report["summary"]["home"]["on_target"] == 2   # Opta's big chance, not an xG threshold
    assert report["buckets"]["unit"] == "shots" and report["buckets"]["home"][1] == 1 and report["buckets"]["home"][2] == 1
    goal = next(s for s in report["shots"]["home"] if s["result"] == "Goal")
    assert goal["assisted_by"] == "Home Ten" and goal["xg"] is None and goal["situation"] == "OpenPlay" and goal["player_id"] == 101
    header = next(s for s in report["shots"]["home"] if s["result"] == "SavedShot")
    assert header["type"] == "Head" and header["situation"] == "FromCorner"
    assert [c["minute"] for c in report["key_chances"]] == [20, 33]                             # every shot, in the order it came
    home = {p["name"]: p for p in report["players"]["home"]}
    assert home["Home Ten"]["goals"] == 1 and home["Home Ten"]["shots"] == 2 and home["Home Ten"]["kp"] == 1 and home["Home Ten"]["xg"] is None
    away = {p["name"]: p for p in report["players"]["away"]}
    assert away["Away Six"]["yellow"] == 1 and away["Away Six"]["id"] == -2                     # not linked to Understat: shown, never linked


def test_the_report_comes_from_the_read_until_understat_publishes_and_then_is_the_normal_one(tmp_path, monkeypatch):
    async def go():
        wb = make(tmp_path)
        events_on(wb, monkeypatch, [])
        now = [ROUND_TWO + 55 * 60]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.repo.league("EPL", 2026)
            with pytest.raises(BadRequest):
                await wb.matches.report(1003, "EPL", "2026")                                    # no read yet: nothing to draw
            assert wb.events.ingest("EPL", 2026, 77, page_doc()) == "live"
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=77, state="live", at=now[0], moment="ht", elapsed="HT", score="1 : 0")
            live = await wb.matches.report(1003, "EPL", "2026")
            json.dumps(live, allow_nan=False)
            assert live["report"]["has_xg"] is False and live["live"]["elapsed"] == "HT" and live["insights"] == [] and live["stats"]["poss"]
            assert (live["report"]["fixture"]["hg"], live["report"]["fixture"]["ag"]) == (1, 0) and live["meta"]["source"] == "whoscored"
            deep = await wb.matches.players(1003, "EPL", "2026")
            json.dumps(deep, allow_nan=False)
            assert deep["rows"] and not any("xg" in k or k in ("xa", "xa90", "big90") for k in deep["keys"])   # no xG metric made of zeros
            # full time: the page replaces the half-time one, which leaves no trace
            now[0] = ROUND_TWO + matchclock.FT_READ + 60
            assert wb.events.ingest("EPL", 2026, 77, page_doc("FT", 6, "2 : 0")) == "final"
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, state="final", at=now[0], moment="ft", elapsed="FT", score="2 : 0")
            assert wb.events.live("EPL", 2026, 77) is None and wb.store.keys("ws_live") == []
            final = await wb.matches.report(1003, "EPL", "2026")
            assert final["live"]["final"] is True and (final["report"]["fixture"]["hg"], final["report"]["fixture"]["ag"]) == (2, 0)
            # Understat publishes: the report is Understat's own again, exactly as for any finished match
            other = await wb.matches.report(1000, "EPL", "2026")                                 # a fixture Understat has published
            assert "live" not in other and other["report"].get("has_xg", True) is True and other["report"]["timeline"]["home"]
        finally:
            await wb.close()

    run(go())


def test_a_half_time_page_that_never_got_its_full_time_read_is_deleted_after_two_days(tmp_path):
    from app.data.store import Store
    from app.events.store import EventStore

    store = Store(tmp_path / "s.sqlite")
    try:
        events = EventStore(store)
        assert events.ingest("EPL", 2026, 77, page_doc(), fetched_at=1000.0) == "live"
        assert events.ingest("EPL", 2026, 78, page_doc(), fetched_at=5000.0) == "live"
        assert events.raw.drop_old_live(older_than=2000.0) == 1
        assert events.live("EPL", 2026, 77) is None and events.live("EPL", 2026, 78) is not None and events.match_ids("EPL", 2026) == []
    finally:
        store.close()
