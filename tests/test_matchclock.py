"""The match clock: a league table is read again when a match can have changed it, not on a timer; the updater sleeps until then."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from app.config import Settings
from app.data import matchclock as M
from app.data.models import Fixture
from app.data.repository import Repository
from app.workbench import Workbench

from .conftest import Clock, FakeProvider, raw_league


def at(text: str) -> float:
    return datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp()


def fx(dt: str, played: bool = False, fid: int = 1) -> Fixture:
    return Fixture(id=fid, dt=dt, home="Reds", away="Blues", home_short="RED", away_short="BLU", played=played)


def test_a_table_read_before_a_match_is_due_again_at_its_90th_minute_of_play():
    due = M.league_due([fx("2026-10-10 14:00:00"), fx("2026-10-17 14:00:00", fid=2)], at("2026-10-10 09:00:00"))
    assert due.why == "full_time" and due.fixture.id == 1 and due.at == at("2026-10-10 14:00:00") + M.UNDERSTAT_FIRST == at("2026-10-10 15:45:00")   # 45 + 15 + 45


def test_a_finished_match_missing_from_the_table_is_looked_for_every_three_minutes_then_slowly_then_not_at_all():
    match = fx("2026-10-10 14:00:00")
    k = at("2026-10-10 14:00:00")
    soon = M.league_due([match], k + M.UNDERSTAT_FIRST + 60)
    assert soon.why == "result" and soon.at == k + M.UNDERSTAT_FIRST + 60 + 3 * 60
    mid = M.league_due([match], k + 5 * 3600)                      # three hours of looking every three minutes are over
    assert mid.why == "result" and mid.at == k + 5 * 3600 + M.RESULT_POLL_MID
    later = M.league_due([match], k + 8 * 3600)
    assert later.why == "result" and later.at == k + 8 * 3600 + M.RESULT_POLL_SLOW
    gone = M.league_due([match], at("2026-10-13 14:00:00"))      # three days on: postponed; only the twice-daily check is left
    assert gone.why == "quiet" and gone.at == at("2026-10-13 14:00:00") + M.QUIET


def test_a_recent_result_is_read_again_while_its_xg_settles_and_a_finished_season_never():
    played = fx("2026-10-10 14:00:00", played=True)
    due = M.league_due([played], at("2026-10-10 18:00:00"))
    assert due.why == "settle" and due.at == at("2026-10-10 18:00:00") + M.SETTLE_POLL
    assert M.league_due([played], at("2026-10-13 18:00:00")).why == "quiet"
    assert M.league_due([played], at("2026-10-10 18:00:00"), complete=True) is None


def test_the_phase_of_a_match_by_the_clock():
    match = fx("2026-10-10 14:00:00")
    k = at("2026-10-10 14:00:00")
    assert [M.phase(match, k + m * 60) for m in (-1, 10, 50, 70, 120)] == ["upcoming", "first_half", "half_time", "second_half", "full_time"]
    assert M.phase(fx("2026-10-10 14:00:00", played=True), k) == "played"
    assert M.in_play(match, k - 60) and M.in_play(match, k + 100 * 60) and not M.in_play(match, k + M.FULL_TIME)


def test_the_repository_reads_a_live_table_after_full_time_not_every_few_hours(store, settings):
    provider = FakeProvider(raw_league(played=6))      # fixture 7 kicks off on 2025-09-06 at 15:00 UTC and is not played yet
    clock = Clock(at("2025-09-06 07:00:00"))
    repo = Repository(store, provider, settings, clock=clock)

    async def go():
        await repo.league("EPL", 2025)
        for when in ("09:30", "12:30", "15:30", "16:44"):      # a whole matchday morning and the match itself, up to its 90th minute: nothing
            clock.now = at(f"2025-09-06 {when}:00")
            await repo.league("EPL", 2025)
        assert len(provider.calls) == 1
        clock.now = at("2025-09-06 15:00:00") + M.UNDERSTAT_FIRST + 1   # the 90th minute of play: look
        await repo.league("EPL", 2025)
        assert len(provider.calls) == 2
        clock.advance(2 * 60)
        await repo.league("EPL", 2025)
        assert len(provider.calls) == 2                       # not listed yet: look again in three minutes, not before
        clock.advance(61)
        await repo.league("EPL", 2025)
        assert len(provider.calls) == 3
        due = repo.league_due("EPL", 2025)
        assert due.why == "result" and due.fixture.id == 1006

    asyncio.run(go())


def test_the_updater_sleeps_until_the_next_full_time_and_says_so(tmp_path):
    async def go():
        settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=True, min_interval=0, page_pace=0)
        wb = Workbench(settings, provider=FakeProvider(raw_league(played=6)), today=date(2025, 9, 6))
        wb.enricher.schedule_rosters = lambda targets: 0
        clock = Clock(at("2025-09-06 11:00:00"))
        wb.repo._clock = wb.auto._clock = wb.matchsync._clock = wb.auto.budget._clock = clock
        try:
            await wb.auto.run_once()
            when, why = wb.auto.next_wake()
            assert when == at("2025-09-06 15:00:00") + M.UNDERSTAT_FIRST          # hours away, not fifteen minutes
            assert why.startswith("Understat's result of ") and why.endswith("(Premier League), from the 90th minute")
            clock.now = at("2025-09-06 07:00:00")
            assert wb.auto.next_wake()[0] == at("2025-09-06 15:00:00") + M.UNDERSTAT_FIRST   # hours away: no wake-up in between
        finally:
            await wb.close()

    asyncio.run(go())


def test_a_long_sleep_ends_on_time_even_when_the_computer_slept_meanwhile(tmp_path, monkeypatch):
    """The event loop's clock stops while a laptop sleeps; the updater's sleep is checked against the wall clock in short steps."""
    from app.sync import autosync

    async def go():
        settings = Settings(data_dir=tmp_path, demo=False, offline=False, auto=True)
        wb = Workbench(settings, provider=FakeProvider(raw_league(played=6)), today=date(2025, 9, 6))
        wall = Clock(at("2025-09-06 12:00:00"))
        wb.auto._clock = wall
        monkeypatch.setattr(autosync, "CLOCK_CHECK", 0.01)
        steps = []
        real_wait_for = asyncio.wait_for

        async def wait_for(aw, timeout):
            steps.append(timeout)
            if len(steps) == 2:
                wall.advance(10 * 3600)                     # the lid was closed for ten hours during this step
            return await real_wait_for(aw, timeout)

        monkeypatch.setattr(autosync.asyncio, "wait_for", wait_for)
        try:
            await real_wait_for(wb.auto._sleep_until(wall.now + 8 * 3600), timeout=2)   # ends right after the jump, not 8 hours later
            assert len(steps) == 2                                                       # one short step, the step with the jump, done
        finally:
            await wb.close()

    asyncio.run(go())
