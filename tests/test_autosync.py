"""The background updater: what a cycle does, how it fails and recovers, and that it never takes the app down. No network, no real process."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from app.config import Settings
from app.errors import UpstreamError
from app.data import matchclock
from app.events import ledger
from app.sync.autosync import BACKOFF_BASE, CLEARANCE, EVENT_BATCH, EVENT_RECHECK, EVENT_REST, FAIL_PREFIX, FT_RETRY, AutoSync, next_midnight
from app.workbench import Workbench

from .events_kit import AWAY, end, ev, match, player

TODAY = date(2026, 10, 2)    # the 2026 season is under way; 2025 is the previous one


def make(tmp_path, **overrides):
    settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=True, min_interval=0, page_pace=0, **overrides)
    from tests.conftest import FakeProvider, raw_league

    provider = FakeProvider(raw_league(played=3))
    wb = Workbench(settings, provider=provider, today=TODAY)
    wb.enricher.schedule_rosters = lambda targets: 0          # squad lists are tested on their own; nothing here may reach ESPN
    return wb, provider


def run(coro):
    return asyncio.run(coro)


class Proc:
    """A stand-in for the event-fetcher process."""

    def __init__(self, code=0):
        self.returncode, self.code, self.killed = None, code, False

    async def wait(self):
        self.returncode = self.code
        return self.code

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.killed, self.returncode = True, -9


class Stubborn(Proc):
    """A fetcher that ignores the polite request to stop and never ends by itself."""

    def terminate(self):
        pass

    async def wait(self):
        while self.returncode is None:
            await asyncio.sleep(0.01)
        return self.returncode


def test_a_cycle_refreshes_every_tracked_league_season_and_fetches_only_missing_match_pages(tmp_path):
    async def go():
        wb, provider = make(tmp_path)
        try:
            result = await wb.auto.run_once()
            tracked = len(wb.auto.tracked())
            assert tracked == 10 and len(result["leagues"]) == 10 and all(v["state"] == "ok" for v in result["leagues"].values())
            assert result["backlog"] == 0 and result["errors"] == []
            assert sum(v["fetched"] for v in result["leagues"].values()) == 3                         # the fake serves the same 3 match ids for every league: stored once, found in the store afterwards
            assert len([c for c in provider.calls if c[0] == "league"]) == 10                         # one request per league season
            matches = len([c for c in provider.calls if c[0] == "match"])
            assert matches == 3
            again = await wb.auto.run_once()
            assert len([c for c in provider.calls if c[0] == "match"]) == matches                      # a second cycle fetches no page twice
            assert all(v.get("fetched", 0) == 0 for v in again["leagues"].values())
        finally:
            await wb.close()

    run(go())


def test_a_failing_league_is_retried_later_with_a_growing_delay_and_the_rest_carry_on(tmp_path):
    async def go():
        wb, provider = make(tmp_path)
        try:
            original = provider.league

            async def flaky(code, season):
                if (code, season) == ("La_liga", 2026):
                    raise UpstreamError("Understat returned HTTP 503.", upstream_status=503)
                return await original(code, season)

            provider.league = flaky
            first = await wb.auto.run_once()
            assert first["leagues"]["La_liga:2026"]["state"] == "failed" and any("La Liga 2026/27" in e for e in first["errors"])
            assert all(v["state"] == "ok" for k, v in first["leagues"].items() if k != "La_liga:2026")     # one league failing stops nobody else
            fail = wb.store.kv_get(FAIL_PREFIX + "La_liga:2026")
            assert fail["n"] == 1 and fail["next_try"] > fail["at"] and "503" in fail["error"]
            calls = len([c for c in provider.calls if c[:3] == ("league", "La_liga", 2026)])
            second = await wb.auto.run_once()
            assert second["leagues"]["La_liga:2026"]["state"] == "waiting"                               # inside its back-off window: left alone
            assert len([c for c in provider.calls if c[:3] == ("league", "La_liga", 2026)]) == calls
            wb.auto._clock = lambda: fail["next_try"] + 1
            wb.auto._fail("La_liga:2026", "still down")
            assert wb.store.kv_get(FAIL_PREFIX + "La_liga:2026")["next_try"] - wb.store.kv_get(FAIL_PREFIX + "La_liga:2026")["at"] == pytest.approx(BACKOFF_BASE * 2)   # doubles
            provider.league = original
            wb.auto._clock = lambda: fail["next_try"] + 10 * 3600
            recovered = await wb.auto.run_once()
            assert recovered["leagues"]["La_liga:2026"]["state"] == "ok" and wb.store.kv_get(FAIL_PREFIX + "La_liga:2026") is None   # success clears the failure
        finally:
            await wb.close()

    run(go())


def test_a_season_that_does_not_exist_yet_is_not_an_error(tmp_path):
    async def go():
        wb, provider = make(tmp_path)
        try:
            async def missing(code, season):
                raise UpstreamError("Understat returned HTTP 404.", upstream_status=404)

            provider.league = missing
            result = await wb.auto.run_once()
            assert result["errors"] == [] and all(v["state"] == "not available" for v in result["leagues"].values())
            assert wb.store.kv_prefix(FAIL_PREFIX) == {}
        finally:
            await wb.close()

    run(go())


def test_a_big_backlog_is_worked_off_over_several_cycles_within_a_time_budget(tmp_path, monkeypatch):
    import app.sync.autosync as mod

    async def go():
        wb, provider = make(tmp_path)
        try:
            monkeypatch.setattr(mod, "CYCLE_BUDGET", -1.0)           # the budget is spent before anything starts
            result = await wb.auto.run_once()
            assert result["backlog"] == 10 and not any(c[0] == "league" for c in provider.calls)    # everything is deferred, nothing is lost
            monkeypatch.setattr(mod, "CYCLE_BUDGET", 300.0)
            done = await wb.auto.run_once()
            assert done["backlog"] == 0 and len([c for c in provider.calls if c[0] == "league"]) == 10
        finally:
            await wb.close()

    run(go())


def test_the_event_fetcher_starts_only_when_enabled_available_and_something_is_missing(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []

        async def spawn(*cmd, **kw):
            spawned.append(cmd)
            return Proc()

        wb.auto._spawn = spawn
        monkeypatch.setattr(AutoSync, "events_capability", staticmethod(lambda: {"available": True, "reason": None, "browser": "/bin/true"}))
        try:
            off = await wb.auto.run_once()
            assert spawned == [] and off["events"]["enabled"] is False                  # nothing was ever fetched here: off until asked for (the Data page switch)
            wb.auto.set_prefs({"events": {"enabled": True, "leagues": ["EPL"], "seasons_back": 0}})
            on = await wb.auto.run_once()
            assert len(spawned) == 1 and on["events"]["started"] == "Premier League 2026/27"
            cmd = spawned[0]
            assert cmd[1:3] == ("-m", "app.cli") and "events" in cmd and cmd[cmd.index("--league") + 1] == "EPL" and cmd[cmd.index("--seasons") + 1] == "2026"
            assert cmd[cmd.index("--limit") + 1] == str(EVENT_BATCH) and cmd[cmd.index("--data-dir") + 1] == str(tmp_path)
            await asyncio.sleep(0)                                                       # let the reaper notice the process ended
            await asyncio.sleep(0)
            await wb.auto.run_once()
            assert len(spawned) == 1                                                     # looked at exactly 3 finished matches already, within the recheck window: not run again
            wb.auto._clock = lambda: wb.store.kv_get("autosync:events:EPL:2026")["at"] + EVENT_RECHECK + 5
            await wb.auto.run_once()
            assert len(spawned) == 2                                                     # ...but looked at again after the window, in case the site had more
        finally:
            await wb.close()

    run(go())


def test_no_event_fetcher_without_the_optional_dependencies_and_a_failed_one_backs_off(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []

        async def spawn(*cmd, **kw):
            spawned.append(cmd)
            return Proc(code=1)                                                          # it exits with an error

        wb.auto._spawn = spawn
        wb.auto.set_prefs({"events": {"enabled": True, "leagues": ["EPL"], "seasons_back": 0}})
        try:
            monkeypatch.setattr(AutoSync, "events_capability", staticmethod(lambda: {"available": False, "reason": "No browser", "hint": "Install one"}))
            result = await wb.auto.run_once()
            assert spawned == [] and result["events"]["available"] is False and result["events"]["reason"] == "No browser"
            monkeypatch.setattr(AutoSync, "events_capability", staticmethod(lambda: {"available": True, "reason": None, "browser": "/bin/true"}))
            await wb.auto.run_once()
            for _ in range(3):
                await asyncio.sleep(0)
            fail = wb.store.kv_get(FAIL_PREFIX + "events:EPL:2026")
            assert len(spawned) == 1 and fail and fail["n"] == 1 and "status 1" in fail["error"]
            await wb.auto.run_once()
            assert len(spawned) == 1                                                     # backing off: no hammering a site that is refusing us
        finally:
            await wb.close()

    run(go())


def test_stopping_the_app_stops_the_event_fetcher_and_kills_one_that_will_not_go(tmp_path, monkeypatch):
    import app.sync.autosync as mod

    monkeypatch.setattr(mod, "STOP_WAIT", 0.05)

    async def stop_with(proc):
        wb, _ = make(tmp_path)
        wb.auto._proc = proc
        await wb.close()
        return proc

    polite = run(stop_with(Proc()))
    assert polite.returncode is not None and not polite.killed                    # asked once, and it went
    stubborn = run(stop_with(Stubborn()))
    assert stubborn.killed and stubborn.returncode == -9                          # not left running in the background after the app has gone


def test_it_does_nothing_in_demo_or_offline_mode(tmp_path):
    async def go():
        from tests.conftest import FakeProvider

        for mode in ({"demo": True}, {"offline": True}):
            wb = Workbench(Settings(data_dir=tmp_path / next(iter(mode)), auto=True, min_interval=0, **mode), provider=FakeProvider(), today=TODAY)
            try:
                result = await wb.auto.run_once()
                assert result["skipped"] and result["leagues"] == {}
            finally:
                await wb.close()

    run(go())


def test_preferences_are_validated_persisted_and_shown(tmp_path):
    async def go():
        wb, _ = make(tmp_path)
        try:
            assert wb.auto.prefs()["enabled"] is True and wb.auto.prefs()["events"]["enabled"] is None
            saved = wb.auto.set_prefs({"seasons_back": 99, "events": {"enabled": True, "leagues": ["EPL", "Atlantis"], "seasons_back": -3}})
            assert saved["seasons_back"] == 4 and saved["events"] == {"enabled": True, "leagues": ["EPL"], "seasons_back": 0}      # clamped; unknown leagues dropped
            assert wb.auto.set_prefs({"events": {"leagues": ["Atlantis"]}})["events"]["leagues"] == ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]   # never an empty scope
            assert wb.store.kv_get("autosync:prefs")["seasons_back"] == 4
            state = wb.auto.state()
            assert state["prefs"]["seasons_back"] == 4 and state["events"]["capability"]["available"] in (True, False) and len(state["tracked"]) == 5 * 5
        finally:
            await wb.close()

    run(go())


def test_the_last_cycles_outcome_survives_a_restart(tmp_path):
    async def go():
        wb, _ = make(tmp_path)
        try:
            await wb.auto.run_once()
        finally:
            await wb.close()
        again, _ = make(tmp_path)
        try:
            state = again.auto.state()
            assert state["last"]["finished"] and len(state["last"]["leagues"]) == 10 and state["log"]
            json.dumps(state)
        finally:
            await again.close()

    run(go())


def test_a_cycle_adopts_event_pages_the_download_cache_holds_and_rebuilds_stale_derived_data(tmp_path):
    async def go():
        wb, _ = make(tmp_path)
        folder = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "ENG-Premier League_2526"
        folder.mkdir(parents=True)
        doc = match([ev("Pass", 1, minute=1 + i % 90) for i in range(60)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 90) for i in range(10)] + [end()],
                    home_players=[player(1)], away_players=[player(2, team_side="away")])
        (folder / "55.json").write_text(json.dumps(doc))
        try:
            result = await wb.auto.run_once()
            assert result["adopted"] == 1 and wb.events.match_ids("EPL", 2025) == [55]
            wb.store.delete("ws_gold")
            wb.store.kv_delete("events:derived")
            rebuilt = await wb.auto.run_once()
            assert rebuilt["rebuilt"] == 1 and wb.events.gold("EPL", 2025, 55) is not None
        finally:
            await wb.close()

    run(go())


# ---------------------------------------------------------------------- limits, rest, pause and retries a person asks for

def _events_on(wb, monkeypatch, spawned, proc=None):
    async def spawn(*cmd, **kw):
        spawned.append(cmd)
        return proc or Proc()

    wb.auto._spawn = spawn
    monkeypatch.setattr(AutoSync, "events_capability", staticmethod(lambda: {"available": True, "reason": None, "browser": "/bin/true"}))
    wb.auto.set_prefs({"events": {"enabled": True, "leagues": ["EPL"], "seasons_back": 0}})


def test_the_event_fetcher_rests_between_runs_and_keeps_to_todays_limit(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []
        _events_on(wb, monkeypatch, spawned)
        now = [1_800_000_000.0]
        wb.auto._clock = lambda: now[0]
        wb.auto.budget._clock = lambda: now[0]
        try:
            wb.auto.set_prefs({"limits": {"whoscored": 5}})
            await wb.auto.run_once()
            assert len(spawned) == 1 and spawned[0][spawned[0].index("--limit") + 1] == "5" and "--budget" in spawned[0]   # never more than today allows
            for _ in range(3):
                await asyncio.sleep(0)
            wb.store.kv_delete("autosync:events:EPL:2026")                              # as if the site had more to give
            now[0] += 60
            held = await wb.auto.run_once()
            assert len(spawned) == 1 and held["events"]["held"] == "resting between runs"
            now[0] += 25 * 60
            wb.auto.budget.spend("whoscored", 5)
            held = await wb.auto.run_once()
            assert len(spawned) == 1 and held["events"]["held"] == "today's limit reached"
            now[0] += 86400                                                              # a new day
            await wb.auto.run_once()
            assert len(spawned) == 2
        finally:
            await wb.close()

    run(go())


def test_pause_holds_every_run_until_resumed_and_a_retry_jumps_the_queue(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []
        _events_on(wb, monkeypatch, spawned)
        try:
            wb.auto.pause_events(True)
            held = await wb.auto.run_once()
            assert spawned == [] and held["events"]["held"] == "paused" and wb.auto.state()["events"]["control"]["paused"] is True
            wb.auto.pause_events(False)
            wb.store.kv_set("autosync:events:last_end", wb.auto._clock())                # it has only just finished a run...
            wb.auto.retry_event_match("EPL", 2026, 4242)
            await wb.auto.run_once()                                                     # ...but a person asked for this one: no rest for it
            assert len(spawned) == 1 and spawned[0][spawned[0].index("--game") + 1] == "4242" and "--budget" not in spawned[0]
            assert wb.auto.state()["events"]["retry"] == []
        finally:
            await wb.close()

    run(go())


def test_stop_asks_the_run_to_end_and_insists_after_the_grace(tmp_path, monkeypatch):
    async def go():
        import app.sync.autosync as A

        wb, _provider = make(tmp_path)
        spawned = []
        proc = Stubborn()
        _events_on(wb, monkeypatch, spawned, proc=proc)
        monkeypatch.setattr(A, "STOP_GRACE", 0.05)
        try:
            await wb.auto.run_once()
            assert len(spawned) == 1 and proc.returncode is None
            control = wb.auto.stop_events()
            assert control["stop_at"] > 0 and control["paused"] is False
            await asyncio.sleep(0.2)
            assert proc.returncode is None                                               # it ignored terminate too (Stubborn): close() kills it
        finally:
            await wb.close()
        assert proc.killed

    run(go())


def test_match_pages_keep_to_todays_limit(tmp_path):
    async def go():
        wb, _provider = make(tmp_path)
        try:
            wb.auto.set_prefs({"limits": {"understat": 0}})
            result = await wb.auto.run_once()
            entry = result["leagues"]["EPL:2026"]
            assert entry.get("held") == "today's limit reached" and entry["remaining"] > 0 and entry["fetched"] == 0
            wb.auto.set_prefs({"limits": {"understat": 2}})
            result = await wb.auto.run_once()
            assert result["leagues"]["EPL:2026"]["fetched"] <= 2 and wb.auto.budget.used("understat") <= 2
            plan = {(p["league"], p["season"]): p for p in wb.auto.plan()}
            assert plan[("EPL", 2026)]["pages_left"] == result["leagues"]["EPL:2026"]["remaining"]
        finally:
            await wb.close()

    run(go())


def test_a_new_install_fills_up_to_todays_limit_then_sleeps_until_midnight(tmp_path):
    async def go():
        wb, provider = make(tmp_path)                                                    # nothing stored yet
        now = [1_800_000_000.0]
        wb.auto._clock = wb.auto.budget._clock = wb.repo._clock = wb.matchsync._clock = lambda: now[0]
        try:
            wb.auto.set_prefs({"limits": {"understat": 2}})
            first = await wb.auto.run_once()
            assert len([c for c in provider.calls if c[0] == "league"]) == 10              # every table at once: tables are never held back
            assert wb.auto.budget.used("understat") == 2 and first["backlog"] > 0          # match pages: only today's share
            second = await wb.auto.run_once()                                            # the backlog look 90 seconds later
            assert second["backlog"] == 0 and len([c for c in provider.calls if c[0] == "match"]) == 2
            options = [(next_midnight(now[0]), "today's match-page limit is used up"),   # the limit's reset,
                       (now[0] + 12 * 3600, "Premier League: the twice-daily check for moved fixtures")]   # or the tables' twice-daily look
            assert wb.auto.next_wake() == min(options, key=lambda o: o[0])               # no retrying all day: whichever comes first
            now[0] = next_midnight(now[0]) + 1                                            # a new day: it carries on
            await wb.auto.run_once()
            assert len([c for c in provider.calls if c[0] == "match"]) == 3
        finally:
            await wb.close()

    run(go())


# ------------------------------------------------------------------ matchday reads

ROUND_TWO = 1755961200.0     # 2025-08-23 15:00 UTC: fixtures 1002 (played) and 1003 (not yet) of the fake league kick off


def _targets(cmd):
    return json.loads(cmd[cmd.index("--targets") + 1]) if "--targets" in cmd else None


def test_every_match_is_read_at_its_full_time_before_any_catching_up(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []
        _events_on(wb, monkeypatch, spawned)
        now = [ROUND_TWO + matchclock.FULL_TIME - CLEARANCE + 60]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            first = await wb.auto.run_once()                                             # nearly full time: nothing to read yet, and catching up waits
            assert spawned == [] and first["events"]["held"] == "matches are being played: catching up waits"
            when, why = wb.auto.next_wake()
            assert when == ROUND_TWO + matchclock.FULL_TIME and why.startswith(("full time of ", "full-time event data of "))
            now[0] = ROUND_TWO + matchclock.FULL_TIME + 30
            await wb.auto.run_once()
            assert [t["fixture"] for t in _targets(spawned[0])] == [1002, 1003] and {t["moment"] for t in _targets(spawned[0])} == {"ft"}
            assert "--limit" not in spawned[0] and "--budget" not in spawned[0]          # a matchday read is not a catching-up run
            for _ in range(3):
                await asyncio.sleep(0)
            # what the fetcher found: one finished, one still in stoppage time
            ledger.note_matchday(wb.store, "EPL", 2026, 1002, game=1, state="final", at=now[0], moment="ft")
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=2, state="live", at=now[0], moment="ft", elapsed="94")
            now[0] += 60
            held = await wb.auto.run_once()
            assert len(spawned) == 1 and held["events"]["held"] == "matches are being played: catching up waits"
            assert wb.auto.next_wake()[0] == now[0] - 60 + FT_RETRY                     # ten minutes after the last read
            now[0] += FT_RETRY
            await wb.auto.run_once()
            assert [t["fixture"] for t in _targets(spawned[1])] == [1003]                # only the one still in play
            for _ in range(3):
                await asyncio.sleep(0)
            ledger.note_matchday(wb.store, "EPL", 2026, 1003, game=2, state="final", at=now[0], moment="ft")
            now[0] += EVENT_REST + 60                                                    # the usual rest after a run, then
            later = await wb.auto.run_once()
            assert later["events"]["started"] == "Premier League 2026/27" and _targets(spawned[2]) is None   # now it catches up
        finally:
            await wb.close()

    run(go())


def test_the_matchday_allowance_follows_the_days_fixtures_and_holds_when_used_up(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []
        _events_on(wb, monkeypatch, spawned)
        now = [ROUND_TWO + matchclock.FULL_TIME + 30]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            assert wb.auto.matchday_allowance() == 10                                    # no fixture list stored yet: just the ones to spare
            await wb.repo.league("EPL", 2026)
            assert wb.auto.matchday_allowance() == 2 * 2 + 10                           # two matches today: half and full time each, and ten to spare
            assert wb.auto.budget.summary()["matchday"]["limit"] == 14
            wb.auto.set_prefs({"limits": {"matchday": 1}})
            assert "matchday" not in wb.auto.prefs()["limits"]                           # not a setting: worked out from the fixtures
            wb.auto.budget.spend("matchday", 14)
            held = await wb.auto.run_once()
            assert spawned == [] and held["events"]["matchday_held"] == "today's matchday reads are used up"
            assert wb.auto.next_wake() == (next_midnight(now[0]), "today's matchday reads are used up")
        finally:
            await wb.close()

    run(go())


def test_a_catching_up_run_makes_way_when_a_match_finishes(tmp_path, monkeypatch):
    async def go():
        wb, _provider = make(tmp_path)
        spawned = []
        _events_on(wb, monkeypatch, spawned, proc=Stubborn())
        now = [ROUND_TWO - 3 * 3600]
        wb.auto._clock = wb.auto.budget._clock = lambda: now[0]
        try:
            await wb.auto.run_once()
            assert len(spawned) == 1 and _targets(spawned[0]) is None                    # hours before kickoff: catching up runs
            assert wb.auto.next_wake()[0] <= ROUND_TWO + matchclock.FULL_TIME            # it still wakes for the full time while that runs
            now[0] = ROUND_TWO + matchclock.FULL_TIME + 30
            result = await wb.auto.run_once()
            assert result["events"]["held"] == "making way for a match that has finished" and ledger.control(wb.store)["stop_at"] == now[0]
        finally:
            spawned_proc = wb.auto._proc
            if spawned_proc is not None:
                spawned_proc.returncode = 0
            await wb.close()

    run(go())
