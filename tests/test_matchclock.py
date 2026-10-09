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


def test_a_table_read_before_a_match_is_due_again_at_its_full_time():
    due = M.league_due([fx("2026-10-10 14:00:00"), fx("2026-10-17 14:00:00", fid=2)], at("2026-10-10 09:00:00"))
    assert due.why == "full_time" and due.fixture.id == 1 and due.at == at("2026-10-10 14:00:00") + M.FULL_TIME


def test_a_finished_match_missing_from_the_table_is_looked_for_often_then_slowly_then_not_at_all():
    match = fx("2026-10-10 14:00:00")
    end = at("2026-10-10 14:00:00") + M.FULL_TIME
    soon = M.league_due([match], end + 60)
    assert soon.why == "result" and soon.at == end + 60 + M.RESULT_POLL
    later = M.league_due([match], end + 7 * 3600)
    assert later.why == "result" and later.at == end + 7 * 3600 + M.RESULT_POLL_SLOW
    gone = M.league_due([match], at("2026-10-13 14:00:00"))      # three days on: postponed; only the routine check is left
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
        for hour in ("09", "12", "15", "16"):                 # a whole matchday morning and the match itself: nothing to read
            clock.now = at(f"2025-09-06 {hour}:30:00")
            await repo.league("EPL", 2025)
        assert len(provider.calls) == 1
        clock.now = at("2025-09-06 15:00:00") + M.FULL_TIME + 1  # the final whistle: look
        await repo.league("EPL", 2025)
        assert len(provider.calls) == 2
        clock.advance(10 * 60)
        await repo.league("EPL", 2025)
        assert len(provider.calls) == 2                       # not listed yet: look again in twenty minutes, not before
        clock.advance(11 * 60)
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
            assert when == at("2025-09-06 15:00:00") + M.FULL_TIME                # hours away, not fifteen minutes
            assert why.startswith("full time of ") and why.endswith("(Premier League)")
            clock.now = at("2025-09-06 07:00:00")
            assert wb.auto.next_wake() == (clock.now + settings.auto_longest_sleep, "routine check")   # never longer than the longest sleep
        finally:
            await wb.close()

    asyncio.run(go())
