"""How WhoScored's event data lines up with Understat's seasons: the same matches, clubs and players, found under two different names."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.errors import AppError
from app.events.link import link_by_lineups, link_fixtures, link_season
from app.events.store import STATUS_PREFIX
from app.workbench.part import Part

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench.core import Workbench


class EventLinks(Part):
    def __init__(self, wb: Workbench) -> None:
        super().__init__(wb)
        self._links: dict[tuple[str, int], tuple[Any, dict]] = {}

    def for_season(self, ls, pages=None) -> dict | None:
        """How WhoScored's matches, clubs and players line up with this Understat season, remembered until either side changes. None without event data."""
        agg = self.events.season(ls.league, ls.season)
        if not agg["games"]:
            return None
        version = (self.events.version(ls.league, ls.season), self.repo.version("league", f"{ls.league}:{ls.season}"), self.repo.epochs.get("match", 0))
        hit = self._links.get((ls.league, ls.season))
        if hit is not None and hit[0] == version:
            return hit[1]
        fixtures, alias, unlinked_matches = link_fixtures(agg, ls.fixtures)
        totals = {pid: {"id": pid, "name": p["name"], "teams": p["teams"], "min": p["c"].get("min", 0)} for pid, p in agg["players"].items()}
        linked, unlinked = link_season(totals, ls.players)
        players = {uid: t["id"] for uid, t in linked.items()}
        by_id = {}
        if unlinked:
            pages = self.matchbook.pages(ls) if pages is None else pages
            if pages:
                left = [agg["players"][u["id"]] for u in unlinked]
                extra = link_by_lineups(left, ls.players, pages, fixtures, alias, taken=players.keys())
                players.update(extra)
                by_id = {w: uid for uid, w in extra.items()}
        left_out = [u for u in unlinked if u["id"] not in by_id]
        info = {"agg": agg, "fixtures": fixtures, "alias": alias, "players": players, "unlinked_matches": unlinked_matches, "unlinked_players": left_out}
        self._links[(ls.league, ls.season)] = (version, info)
        return info

    def player_events(self, ls, pages=None) -> dict[int, dict] | None:
        """Understat player id -> his event counters for this season. None when no event data has been stored for it."""
        info = self.for_season(ls, pages)
        if info is None:
            return None
        players = info["agg"]["players"]
        return {uid: {"c": players[w]["c"], "matches": players[w]["matches"], "starts": players[w]["starts"], "pos": players[w]["pos"]} for uid, w in info["players"].items()}

    def team_events(self, ls) -> dict[str, dict] | None:
        """Understat club -> its event totals (for and against) for this season. None without event data."""
        info = self.for_season(ls)
        if info is None:
            return None
        out = {}
        for ws, t in info["agg"]["teams"].items():
            us = info["alias"].get(ws)
            if us in ls.teams:
                out[us] = {"c": t["c"], "a": t["a"], "matches": t["matches"], "formations": t["formations"], "managers": t["managers"]}
        return out

    async def status(self) -> list[dict]:
        """Per league-season: matches stored, how many exist, how well they line up with Understat, and the state of any fetching run."""
        seen: dict[tuple[str, int], None] = {(lg, s): None for lg, s, _n in self.events.seasons()}
        for key in self.store.kv_prefix(STATUS_PREFIX):
            name, _, year = key[len(STATUS_PREFIX):].partition(":")
            if year.isdigit():
                seen.setdefault((name, int(year)), None)
        out = []
        for league, season in sorted(seen):
            entry: dict = {"league": league, "season": season, "matches": len(self.events.match_ids(league, season)), "total": None,
                           "status": self.events.status(league, season), "linked": None, "unlinked": [], "unlinked_n": 0, "matches_linked": None}
            if self.store.meta("league", f"{league}:{season}") is not None:   # only from the cache: this must never go to the network
                try:
                    fetched = await self.wb.seasons.load(league, season)
                    entry["total"] = len(fetched.data.played)
                    if entry["matches"]:
                        version = (self.events.version(league, season), self.repo.version("league", f"{league}:{season}"), self.repo.epochs.get("match", 0))

                        def report(ls=fetched.data):
                            info = self.for_season(ls)
                            if info is None:
                                return {}
                            left = sorted(info["unlinked_players"], key=lambda u: -u["minutes"])
                            return {"linked": len(info["players"]), "unlinked": left[:10], "unlinked_n": len(left),
                                    "matches_linked": len(info["fixtures"]), "matches_unlinked": len(info["unlinked_matches"])}

                        entry.update(await self.wb.memo(("events-link", league, season), version, report))
                except AppError:
                    pass
            out.append(entry)
        return out
