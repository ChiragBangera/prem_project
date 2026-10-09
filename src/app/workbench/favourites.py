"""Your favourite teams. Their matches are followed: on matchday their event data is read at half time as well as at full time, and the
match lists mark them. They live in the store's settings table, like the shortlist, so restarts, updates, clearing the cache and a new
demo world all keep them; only deleting the database file itself loses them."""

from __future__ import annotations

import time

from app.errors import BadRequest
from app.leagues import LEAGUES
from app.workbench.part import Part

KEY = "favourite_teams"


class Favourites(Part):
    def teams(self) -> list[dict]:
        return self.store.kv_get(KEY, [])

    def follows(self, league: str, team: str) -> bool:
        return any(t["league"] == league and t["team"] == team for t in self.teams())

    def set(self, league: str, team: str, favourite: bool) -> list[dict]:
        """Add a team to the favourites (``favourite`` true) or take it off. Adding twice keeps one entry, and when it was first added."""
        team = team.strip()
        if league not in LEAGUES:
            raise BadRequest(f"Unknown league '{league}'.", hint=f"Choose one of: {', '.join(LEAGUES)}.")
        if not team or len(team) > 80:
            raise BadRequest("A favourite team needs its name.")
        current = self.teams()
        existing = next((t for t in current if t["league"] == league and t["team"] == team), None)
        items = [t for t in current if t is not existing]
        if favourite:
            items.append(existing or {"league": league, "team": team, "added": int(time.time())})
        self.store.kv_set(KEY, items)
        self.wb.auto.wake()   # a match of this team may be at half time right now
        return items
