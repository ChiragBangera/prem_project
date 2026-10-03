"""The Compare page: two teams, or several players, side by side."""

from __future__ import annotations

from app.analytics import compare as compare_engine
from app.errors import NotFound
from app.workbench.part import Part


class ComparePage(Part):
    async def players(self, ids: list[int], league: str, season) -> dict:
        wb = self.wb
        code, s, _fetched, scope = await wb.seasons.scope(league, season)
        ds, _ = await wb.datasets.players([(code, s)])
        by_id = {r["id"]: r for r in ds.rows}
        missing = [i for i in ids if i not in by_id]
        if missing:
            raise NotFound(f"Player(s) {missing} have no minutes in {scope['league_name']} {scope['label']}.")
        rows = [by_id[i] for i in ids]
        result = compare_engine.compare_players(rows)
        result["facts"] = compare_engine.player_comparison_facts(rows)
        result["scope"] = scope
        return result

    async def teams(self, league: str, season, a: str, b: str) -> dict:
        _code, _s, fetched, scope = await self.wb.seasons.scope(league, season)
        result = compare_engine.compare_teams(fetched.data, a, b)
        result["scope"] = scope
        return result
