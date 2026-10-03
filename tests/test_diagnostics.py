"""The connection check must say which step failed, in words a person can act on."""

from __future__ import annotations

from datetime import date

from app.config import Settings
from app.errors import UpstreamError
from app.workbench import Workbench


class Unreachable:
    source = "understat"

    async def league(self, league: str, season: int) -> dict:
        raise UpstreamError("Could not reach understat.com.", hint="Check the network or a proxy.")

    async def close(self) -> None:
        return None


class Garbled(Unreachable):
    async def league(self, league: str, season: int) -> dict:
        return {"teamsData": "not json we can use", "playersData": [], "datesData": []}


async def test_unreachable_upstream_stops_at_the_first_step(tmp_path):
    wb = Workbench(Settings(data_dir=tmp_path, min_interval=0, offline=True), provider=Unreachable(), today=date(2027, 3, 10))
    try:
        result = await wb.diagnostics.check()
    finally:
        await wb.close()
    assert not result["ok"]
    first = result["steps"][0]
    assert first["name"] == "Reach Understat" and not first["ok"]
    assert "understat.com" in first["detail"] and first["hint"] == "Check the network or a proxy."
    # later league-dependent steps are skipped, but the independent squad-list and birthdate steps still report
    assert [s["name"] for s in result["steps"]] == ["Reach Understat", "Read a squad list", "Look up birthdates"]


async def test_a_changed_page_format_is_reported_as_such(tmp_path):
    wb = Workbench(Settings(data_dir=tmp_path, min_interval=0, offline=True), provider=Garbled(), today=date(2027, 3, 10))
    try:
        result = await wb.diagnostics.check()
    finally:
        await wb.close()
    assert not result["ok"]
    failed = [s for s in result["steps"] if not s["ok"]]
    assert failed and failed[0]["name"] == "Read the league page"
    assert "format" in (failed[0]["hint"] or "") or "teams" in failed[0]["detail"]
