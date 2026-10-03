"""The background updater: what a cycle does, how it fails and recovers, and that it never takes the app down. No network, no real process."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from app.config import Settings
from app.errors import UpstreamError
from app.sync.autosync import BACKOFF_BASE, EVENT_BATCH, EVENT_RECHECK, FAIL_PREFIX, AutoSync
from app.workbench import Workbench

from .events_kit import AWAY, end, ev, match, player

TODAY = date(2026, 10, 2)    # the 2026 season is under way; 2025 is the previous one


def make(tmp_path, **overrides):
    settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=True, min_interval=0, **overrides)
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
