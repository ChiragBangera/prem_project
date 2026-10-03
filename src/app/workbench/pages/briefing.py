"""The Briefing page: what is worth knowing about a league right now."""

from __future__ import annotations

from app.analytics.table import compute_table, league_context
from app.insights.briefing import compose_insights, movers, recent_matches
from app.insights.core import dicts, rank
from app.insights.league import league_insights
from app.insights.player import scouting_highlights
from app.leagues import LEAGUES
from app.workbench.part import Part


class BriefingPage(Part):
    async def page(self, league: str, season) -> dict:
        wb = self.wb
        code, s, fetched, scope = await wb.seasons.scope(league, season)
        ls = fetched.data
        cfg = LEAGUES[code]
        ctx = league_context(ls)
        table = compute_table(ls)
        league_side = league_insights(table, ctx, relegation_places=cfg.relegation_places)
        ds, _ = await wb.datasets.players([(code, s)])
        front = compose_insights(league_side, scouting_highlights(ds.rows), limit=8)
        n = len(table)
        gaps = {}
        if n >= 4 and not ctx["complete"]:
            pts = [r["pts"] for r in table]
            gaps = {"title": pts[0] - pts[1], "top": pts[cfg.ucl_places - 1] - pts[cfg.ucl_places] if cfg.ucl_places < n else None,
                    "safety": pts[n - cfg.relegation_places - 1] - pts[n - cfg.relegation_places] if cfg.relegation_places < n else None}
        summaries = await wb.matches.summaries(code, s, ls)
        latest = recent_matches(ls, limit=10)
        by_id = {f.id: f for f in ls.fixtures}
        recent_cards = [wb.matches.card(by_id[m["id"]], summaries, {m["id"]: m}) for m in latest if m["id"] in by_id]
        upcoming = []
        by_team = {r["team"]: r for r in table}
        for f in sorted(ls.upcoming, key=lambda f: (f.dt, f.id))[:10]:
            h, a = by_team.get(f.home), by_team.get(f.away)
            upcoming.append({"id": f.id, "date": f.date, "dt": f.dt, "utc": f.dt[:10] + "T" + f.dt[11:19] + "Z" if len(f.dt) >= 19 else None, "round": f.round, "home": f.home, "away": f.away,
                             "home_short": f.home_short, "away_short": f.away_short,
                             "home_rank": h and h["rank"], "away_rank": a and a["rank"], "home_form": h and h["form"], "away_form": a and a["form"],
                             "home_xgd": h and round(h["xgd_pg"], 2), "away_xgd": a and round(a["xgd_pg"], 2)})
        return {
            "scope": scope, "meta": fetched.meta.to_dict(), "context": ctx, "insights": dicts(front), "gaps": gaps,
            "table": [{k: r[k] for k in ("rank", "team", "short", "played", "pts", "gd", "xpts", "xpts_gap", "xgd_pg", "form", "trend_xgd", "rank_xpts")} for r in table],
            "recent": recent_cards, "movers": movers(ls), "upcoming": upcoming,
            "highlights": dicts(rank(scouting_highlights(ds.rows), limit=6, per_kind=2, diversify=True)),
        }
