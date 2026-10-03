"""The date the app works from: pinned when a caller, PREM_TODAY or the demo world says so; otherwise the calendar, so a long-running server moves on."""

from __future__ import annotations

from datetime import date

from app.config import Settings
from app.data.demo import DemoProvider
from app.workbench import Workbench

from .conftest import FakeProvider


class Clock:
    """Stands in for ``date`` inside the workbench so the calendar can be moved."""

    now = date(2026, 10, 2)

    @classmethod
    def today(cls) -> date:
        return cls.now

    @classmethod
    def fromisoformat(cls, text: str) -> date:
        return date.fromisoformat(text)


def make(tmp_path, monkeypatch, **kwargs) -> Workbench:
    monkeypatch.delenv("PREM_TODAY", raising=False)
    monkeypatch.setattr("app.workbench.date", Clock)
    return Workbench(Settings(data_dir=tmp_path, min_interval=0), provider=FakeProvider(), **kwargs)


async def test_a_real_run_follows_the_calendar_across_midnight_and_the_season_rollover(tmp_path, monkeypatch):
    wb = make(tmp_path, monkeypatch)
    try:
        Clock.now = date(2026, 10, 2)
        assert wb.today == date(2026, 10, 2)
        meta = await wb.meta()
        assert meta["today"] == "2026-10-02" and meta["current_season"] == 2026
        Clock.now = date(2026, 10, 3)
        assert wb.today == date(2026, 10, 3) and (await wb.meta())["today"] == "2026-10-03"   # the next morning, with no restart
        Clock.now = date(2027, 8, 20)
        assert (await wb.meta())["current_season"] == 2027                                     # and in August the next season
    finally:
        Clock.now = date(2026, 10, 2)
        await wb.close()


async def test_a_pinned_date_stays_put(tmp_path, monkeypatch):
    wb = make(tmp_path, monkeypatch, today=date(2021, 1, 15))
    try:
        Clock.now = date(2030, 1, 1)
        assert wb.today == date(2021, 1, 15) and (await wb.meta())["today"] == "2021-01-15"
        monkeypatch.setenv("PREM_TODAY", "2027-03-10")
        pinned_by_env = Workbench(Settings(data_dir=tmp_path / "env", min_interval=0), provider=FakeProvider())
        assert pinned_by_env.today == date(2027, 3, 10)
        await pinned_by_env.close()
        wb.today = date(2025, 5, 5)                                                          # a test may move the pinned date itself
        assert wb.today == date(2025, 5, 5)
    finally:
        Clock.now = date(2026, 10, 2)
        await wb.close()


async def test_the_demo_world_keeps_the_date_it_was_simulated_up_to(tmp_path, monkeypatch):
    monkeypatch.delenv("PREM_TODAY", raising=False)
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), provider=DemoProvider(today=date(2021, 1, 15)))
    try:
        assert wb.today == date(2021, 1, 15)
    finally:
        await wb.close()


async def test_views_that_read_the_date_are_rebuilt_when_the_day_changes(tmp_path, monkeypatch):
    wb = make(tmp_path, monkeypatch)
    built = []

    def compute():
        built.append(wb.today)
        return len(built)

    try:
        Clock.now = date(2026, 10, 2)
        assert await wb._memo_async(("view",), 1, compute) == 1
        assert await wb._memo_async(("view",), 1, compute) == 1                              # the same day: served from memory
        Clock.now = date(2026, 10, 3)
        assert await wb._memo_async(("view",), 1, compute) == 2                              # the next day: built again, for the new date
        assert built == [date(2026, 10, 2), date(2026, 10, 3)]
    finally:
        Clock.now = date(2026, 10, 2)
        await wb.close()
