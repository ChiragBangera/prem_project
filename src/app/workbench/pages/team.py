"""The Team page and its tabs: the profile, the seasons side by side, the chances, the pitch maps, the shots and the matches."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from app.analytics.chances import MIN_LEAGUE_TEAMS, chance_insights, compare_to_league, league_baseline, prepare_breakdowns
from app.analytics.team import find_team, team_history, team_profile
from app.errors import AppError, BadRequest, DataUnavailable, NotFound
from app.events import maps as event_maps
from app.insights.core import dicts, rank
from app.insights.team import team_insights
from app.leagues import FIRST_SEASON, LEAGUES, season_label
from app.workbench.pages.mapdata import map_payload, pick_matches
from app.workbench.part import Part

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench.core import Workbench

HISTORY_DEFAULT_SEASONS = 5
HISTORY_MAX_SEASONS = 8  # one colour each in the charts
PACKAGED_MANAGERS = Path(__file__).resolve().parents[2] / "data" / "managers.json"


class TeamPage(Part):
    def __init__(self, wb: Workbench) -> None:
        super().__init__(wb)
        self.managers = self._load_managers()

    def _load_managers(self) -> list[dict]:
        stints: list[dict] = []
        for path in (PACKAGED_MANAGERS, self.settings.data_dir / "managers.json"):
            try:
                stints += json.loads(path.read_text())["stints"]
            except (OSError, ValueError, KeyError):
                continue
        return stints

    def eras_for(self, league: str, team: str) -> list[dict]:
        """The manager stints you or the project have written down for a club (none in the demo world: they describe real clubs)."""
        if self.settings.demo:
            return []
        return [s for s in self.managers if s.get("league") == league and s.get("team") == team]

    async def page(self, league: str, season, team: str) -> dict:
        code, _s, fetched, scope = await self.wb.seasons.scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)
        profile = team_profile(ls, t.name, eras=self.eras_for(code, t.name))
        cfg = LEAGUES[code]
        insights = rank(team_insights(profile, ucl_places=cfg.ucl_places, relegation_places=cfg.relegation_places))
        return {"scope": scope, "meta": fetched.meta.to_dict(), "profile": profile, "insights": dicts(insights),
                "teams": [{"name": x.name, "short": x.short} for x in sorted(ls.teams.values(), key=lambda x: x.name)]}

    async def history(self, league: str, team: str, seasons: list[int]) -> dict:
        """One team's seasons side by side, by matchweek. Seasons the team was not in the league come back flagged, not as errors."""
        wb = self.wb
        code = wb.seasons.league_code(league)
        cfg = LEAGUES[code]
        if not seasons:
            newest, _ = await wb.seasons.resolve(code, "auto")
            seasons = [s for s in range(newest, newest - HISTORY_DEFAULT_SEASONS, -1) if s >= FIRST_SEASON]
        seasons = list(dict.fromkeys(seasons))
        if len(seasons) > HISTORY_MAX_SEASONS:
            raise BadRequest(f"Pick at most {HISTORY_MAX_SEASONS} seasons to compare.")
        key = team.strip().lower()

        async def one(season: int):
            base = {"season": season, "label": season_label(season)}
            try:
                fetched = await wb.seasons.load(code, season)
            except AppError as exc:
                return {**base, "available": False, "reason": exc.message}, None
            try:
                data = await wb.memo(("team_history", code, season, key), wb.seasons.version((code, season)), lambda: team_history(fetched.data, team))
            except NotFound:
                return {**base, "available": False, "missing": True, "reason": f"Not in the {cfg.name} in {base['label']}."}, fetched.meta
            return {**base, "available": True, **data}, fetched.meta

        results = await asyncio.gather(*(one(s) for s in seasons))
        rows = sorted((r for r, _ in results), key=lambda r: -r["season"])
        metas = [m for _, m in results if m is not None]
        found = [r for r in rows if r["available"]]
        if not found:
            if any(r.get("missing") for r in rows):
                raise NotFound(f"'{team}' was not in the {cfg.name} in any of the selected seasons.", hint="Pick other seasons, or check the spelling.")
            raise DataUnavailable("None of the selected seasons could be loaded.", hint="Open the Data page to sync, or try other seasons.")
        return {
            "scope": {"league": code, "league_name": cfg.name},
            "team": found[0]["team"],
            "short": found[0]["short"],
            "seasons": rows,
            "rounds_max": max(len(r["points"]) for r in found),
            "n_teams_max": max(r["n_teams"] for r in found),
            "meta": {"stale": any(m.stale for m in metas), "errors": [m.error for m in metas if m.error]},
        }

    async def chances(self, league: str, season, team: str) -> dict:
        """The team's own chance breakdowns: fast (one page), no league context. See :meth:`chances_league` for that."""
        _code, s, fetched, scope = await self.wb.seasons.scope(league, season)
        t = find_team(fetched.data, team)
        page = await self.repo.team_page(t.name, s)
        prepared = prepare_breakdowns(page.data.groups, max(len(t.history), 1))
        return {
            "scope": scope, "meta": page.meta.to_dict(), "team": t.name, "games": len(t.history),
            "breakdowns": prepared, "insights": chance_insights(t.name, prepared),
        }

    async def chances_league(self, league: str, season, team: str) -> dict:
        """The same breakdowns set against every other team: ranks, league averages and league-aware findings.

        Loads each team's page (cached; finished seasons are fetched once, ever). If it cannot, the tab keeps working without it.
        """
        _code, s, fetched, _ = await self.wb.seasons.scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        async def page(name: str):
            try:
                return name, (await self.repo.team_page(name, s)).data.groups
            except AppError:
                return name, None

        try:
            results = await asyncio.wait_for(asyncio.gather(*(page(n) for n in ls.teams)), timeout=40)
        except TimeoutError:
            return {"available": False, "reason": "Comparing with the rest of the league took too long. Open the tab again in a moment: the pages already fetched are kept.", "of": len(ls.teams)}
        pages = {n: g for n, g in results if g}
        if len(pages) < MIN_LEAGUE_TEAMS or t.name not in pages:
            return {"available": False, "reason": "Not enough of the league's team pages could be loaded to compare against.", "loaded": len(pages), "of": len(ls.teams)}
        prepared = {n: prepare_breakdowns(g, max(len(ls.teams[n].history), 1)) for n, g in pages.items()}
        comparison = compare_to_league(t.name, prepared[t.name], league_baseline(prepared))
        return {
            "available": True, "team": t.name, "loaded": len(pages), "of": len(ls.teams),
            "comparison": comparison, "insights": chance_insights(t.name, prepared[t.name], comparison),
        }

    async def maps(self, league: str, season, team: str, *, venue: str = "all", last: int | None = None) -> dict:
        """Where a team touches the ball, passes, defends and carries, from its stored matches: grids, pass lines, defensive actions, a pass network."""
        if venue not in ("all", "h", "a"):
            raise BadRequest("venue must be 'all', 'h' or 'a'.")
        wb = self.wb
        code, s, fetched, scope = await wb.seasons.scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)
        key = ("team-maps", code, s, t.name, venue, last)
        version = (self.events.version(code, s), self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0))

        def compute():
            info = wb.links.for_season(ls)
            if info is None:
                return {"available": False, "reason": "No event data has been stored for this league and season yet."}
            ws = next((w for w, us in info["alias"].items() if us == t.name), None)
            agg = info["agg"]["teams"].get(ws) if ws else None
            if ws is None or agg is None:
                return {"available": False, "reason": f"{t.name} has no event data in this season."}
            log = pick_matches(agg["log"], venue, last)
            if not log:
                return {"available": False, "reason": "No matches fit those filters."}
            games = [(i, r["game"]) for i, r in enumerate(log)]
            fixtures = info["fixtures"]
            listing = [{"i": i, "game": r["game"], "date": r["date"], "opp": info["alias"].get(r["opp"], r["opp"]), "home": r["home"], "gf": r["gf"], "ga": r["ga"],
                        "match_id": fixtures[r["game"]].id if r["game"] in fixtures else None} for i, r in enumerate(log)]
            return map_payload(self.events, code, s, games, event_maps.Selection(team=ws), team=ws,
                               extra={"matches": listing, "formations": agg["formations"], "manager": max(agg["managers"], key=agg["managers"].get) if agg["managers"] else None})

        out = await wb.memo(key, version, compute)
        return {"scope": scope, "team": t.name, **out}

    async def shots(self, league: str, season, team: str, *, venue: str = "all", last: int | None = None) -> dict:
        """The team's shots and the shots it faced, from the stored Understat match pages: position, xG, result, scorer."""
        code, s, fetched, scope = await self.wb.seasons.scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        def compute():
            pages = self.matchbook.pages(ls)
            mine = [f for f in sorted(ls.fixtures, key=lambda f: (f.dt, f.id)) if f.played and t.name in (f.home, f.away) and f.id in pages]
            mine = [f for f in mine if venue == "all" or (venue == "h") == (f.home == t.name)]
            mine = mine[-last:] if last else mine
            for_, against = [], []
            for f in mine:
                side = "h" if f.home == t.name else "a"
                for sh in pages[f.id].shots.get(side, []):
                    for_.append([round(sh.x, 3), round(sh.y, 3), round(sh.xg, 3), sh.result, sh.minute, sh.player, sh.situation, sh.shot_type, f.id])
                for sh in pages[f.id].shots.get("a" if side == "h" else "h", []):
                    against.append([round(sh.x, 3), round(sh.y, 3), round(sh.xg, 3), sh.result, sh.minute, sh.player, sh.situation, sh.shot_type, f.id])
            have, total = self.matchbook.coverage(ls, pages)
            return {"for": for_, "against": against, "matches": len(mine), "coverage": [have, total]}

        out = await self.wb.memo(("team-shots", code, s, t.name, venue, last), (self.repo.version("league", f"{code}:{s}"), self.repo.epochs.get("match", 0)), compute)
        return {"scope": scope, "team": t.name, **out}

    async def matches(self, league: str, season, team: str) -> dict:
        """One team's season match by match: result, the chances, and (where event data exists) possession, passing and pressing in that match."""
        wb = self.wb
        code, s, fetched, scope = await wb.seasons.scope(league, season)
        ls = fetched.data
        t = find_team(ls, team)

        def compute():
            info = wb.links.for_season(ls)
            rows = {r["n"]: r for r in team_profile(ls, t.name)["matches"]}
            by_fixture = {}
            if info is not None:
                ws = next((w for w, us in info["alias"].items() if us == t.name), None)
                agg = info["agg"]["teams"].get(ws) if ws else None
                for r in (agg["log"] if agg else []):
                    f = info["fixtures"].get(r["game"])
                    if f is not None:
                        c, a = r["c"], r["a"]
                        pf, pa = c.get("passes", 0), a.get("passes", 0)
                        by_fixture[f.id] = {"poss": None if pf + pa == 0 else round(100 * pf / (pf + pa)), "passes": pf, "pass_acc": None if not pf else round(100 * c.get("pass_ok", 0) / pf),
                                            "prog": c.get("prog", 0), "tilt": None if not (c.get("touch_att3", 0) + a.get("touch_att3", 0)) else round(100 * c.get("touch_att3", 0) / (c.get("touch_att3", 0) + a.get("touch_att3", 0))),
                                            "tackles": c.get("tackles", 0), "interceptions": c.get("interceptions", 0), "recoveries": c.get("recoveries", 0),
                                            "fouls": c.get("fouls", 0), "corners": c.get("corners", 0), "formation": r["formation"], "manager": r["manager"]}
            return [{**row, **by_fixture.get(row["match_id"], {})} for row in rows.values()]

        out = await wb.memo(("team-matches", code, s, t.name), (self.repo.version("league", f"{code}:{s}"), self.events.version(code, s), self.repo.epochs.get("match", 0)), compute)
        return {"scope": scope, "team": t.name, "matches": out}
