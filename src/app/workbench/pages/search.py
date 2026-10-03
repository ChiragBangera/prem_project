"""Search: find a player or a team by any part of the name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.errors import AppError
from app.leagues import fold
from app.workbench.part import Part

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench.core import Workbench


class SearchPage(Part):
    def __init__(self, wb: Workbench) -> None:
        super().__init__(wb)
        self._index: tuple | None = None

    async def index(self) -> tuple[list[dict], list[dict]]:
        """Every player and team of the two newest cached seasons of each league, as search rows. Rebuilt when a league season changes."""
        cached = self.repo.cached_leagues()
        latest: dict[str, list[int]] = {}
        for item in cached:
            latest.setdefault(item["league"], []).append(item["season"])
        keep = [(lg, s) for lg, seasons in latest.items() for s in sorted(seasons, reverse=True)[:2]]
        token = tuple(sorted(keep)) + self.wb.seasons.version(*keep)
        if self._index is not None and self._index[0] == token:
            return self._index[1], self._index[2]
        players: dict[int, dict] = {}
        teams: dict[tuple[str, str], dict] = {}
        for league, season in sorted(keep, key=lambda t: t[1]):  # newest season last, so it wins
            try:
                ls = (await self.wb.seasons.load(league, season)).data
            except AppError:
                continue
            for team in ls.teams.values():
                teams[(league, team.name)] = {"name": team.name, "short": team.short, "league": league, "season": season}
            for p in ls.players:
                players[p.id] = {"id": p.id, "name": p.name, "team": p.team, "league": league, "season": season, "minutes": p.minutes, "key": fold(p.name)}
        rows, team_rows = list(players.values()), list(teams.values())
        self._index = (token, rows, team_rows)
        return rows, team_rows

    async def query(self, query: str, limit: int = 8) -> dict:
        needle = fold(query)
        if len(needle) < 2:
            return {"players": [], "teams": []}
        rows, teams = await self.index()
        tokens = needle.split()

        def score(text: str) -> int | None:
            if not all(t in text for t in tokens):
                return None
            if text.startswith(needle):
                return 0
            if any(w.startswith(needle) for w in text.split()):
                return 1
            return 2 if all(any(w.startswith(t) for w in text.split()) for t in tokens) else 3

        found = []
        for r in rows:
            s = score(r["key"])
            if s is not None:
                found.append((s, -r["minutes"], r))
        found.sort(key=lambda x: (x[0], x[1]))
        team_hits = []
        for t in teams:
            s = score(fold(t["name"])) if score(fold(t["name"])) is not None else score(fold(t["short"]))
            if s is not None:
                team_hits.append((s, t["name"], t))
        team_hits.sort(key=lambda x: (x[0], x[1]))
        return {"players": [{k: v for k, v in r.items() if k != "key"} for _s, _m, r in found[:limit]], "teams": [t for _s, _n, t in team_hits[:5]]}
