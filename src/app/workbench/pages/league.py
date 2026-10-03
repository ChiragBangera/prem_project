"""The League page: the table, filtered by venue, recent form or dates, with its rank trajectories and findings."""

from __future__ import annotations

from app.analytics.table import compute_table, league_context, rank_trajectories
from app.errors import BadRequest
from app.insights.core import dicts, rank
from app.insights.league import league_insights
from app.leagues import LEAGUES
from app.workbench.part import Part


class LeaguePage(Part):
    async def page(self, league: str, season, *, venue: str = "all", last: int | None = None,
                   date_from: str | None = None, date_to: str | None = None) -> dict:
        code, _season, fetched, scope = await self.wb.seasons.scope(league, season)
        if venue not in ("all", "h", "a"):
            raise BadRequest("venue must be 'all', 'h' or 'a'.")
        ls = fetched.data
        table = compute_table(ls, venue=venue, last_n=last, date_from=date_from, date_to=date_to)
        ctx = league_context(ls)
        cfg = LEAGUES[code]
        paths = rank_trajectories(ls)
        insights = rank(league_insights(compute_table(ls), ctx, relegation_places=cfg.relegation_places))
        return {
            "scope": scope, "meta": fetched.meta.to_dict(), "context": ctx,
            "filter": {"venue": venue, "last": last, "date_from": date_from, "date_to": date_to},
            "table": table, "trajectories": paths, "insights": dicts(insights),
        }
