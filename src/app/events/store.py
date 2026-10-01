"""Event data in the local store: one small record per match, and what a season of them adds up to.

Records live in the same SQLite file as everything else (kind ``events``, key ``LEAGUE:SEASON:GAMEID``), so a
match is fetched once and then read from disk. The fetching process (``prem events sync``) and the app only
meet here, through the store.
"""

from __future__ import annotations

import time
from typing import Iterable

from app.data.store import Store

from .aggregate import COUNTS, MATCH_ROW_VERSION

KIND = "events"
STATUS_PREFIX = "events:run:"
STALE_AFTER = 600.0  # a "running" status not updated for this long means the run died


def _key(league: str, season: int, game_id: int | str) -> str:
    return f"{league}:{season}:{game_id}"


class EventStore:
    def __init__(self, store: Store):
        self.store = store
        self._totals: dict[tuple[str, int], tuple[tuple, dict]] = {}

    # ------------------------------------------------------------------ matches

    def put_match(self, league: str, season: int, game_id: int, rows: list[dict], *, home: str = "", away: str = "", date: str = "") -> None:
        body = {"v": MATCH_ROW_VERSION, "game": int(game_id), "home": home, "away": away, "date": date, "rows": rows}
        self.store.put(KIND, _key(league, season, game_id), body, source="whoscored", complete=True)

    def has_match(self, league: str, season: int, game_id: int | str) -> bool:
        return self.store.meta(KIND, _key(league, season, game_id)) is not None

    def has_current_match(self, league: str, season: int, game_id: int | str) -> bool:
        """Stored in the current row format. An older format is stored but needs re-reading (the definitions changed since)."""
        record = self.store.get(KIND, _key(league, season, game_id))
        return record is not None and record.body.get("v") == MATCH_ROW_VERSION

    def match_ids(self, league: str, season: int) -> list[int]:
        prefix = f"{league}:{season}:"
        return [int(k[len(prefix):]) for k, _t in self.store.keys_prefix(KIND, prefix) if k[len(prefix):].isdigit()]

    def version(self, league: str, season: int) -> tuple[int, float]:
        """Changes whenever a match is added: used to know when cached results built from this are stale."""
        found = [t for _k, t in self.store.keys_prefix(KIND, f"{league}:{season}:")]
        return (len(found), max(found, default=0.0))

    def seasons(self) -> list[tuple[str, int, int]]:
        """Every league-season with stored matches, as (league, season, matches)."""
        counts: dict[tuple[str, int], int] = {}
        for k, _t, _c in self.store.keys(KIND):
            league, _, rest = k.partition(":")
            season, _, _game = rest.partition(":")
            if season.isdigit():
                counts[(league, int(season))] = counts.get((league, int(season)), 0) + 1
        return sorted((l, s, n) for (l, s), n in counts.items())

    # ------------------------------------------------------------------ totals

    def season_totals(self, league: str, season: int) -> dict[int, dict]:
        """Per WhoScored player: summed counts, minutes, matches, and the teams played for (with minutes)."""
        version = self.version(league, season)
        cached = self._totals.get((league, season))
        if cached and cached[0] == version:
            return cached[1]
        totals: dict[int, dict] = {}
        for game_id in self.match_ids(league, season):
            record = self.store.get(KIND, _key(league, season, game_id))
            if record is None or record.body.get("v") != MATCH_ROW_VERSION:
                continue
            for row in record.body.get("rows", []):
                t = totals.get(row["id"])
                if t is None:
                    t = totals[row["id"]] = {"id": row["id"], "name": row.get("name", ""), "teams": {}, "min": 0.0, "matches": 0, "starts": 0, **{k: 0 for k in COUNTS}}
                t["min"] += row.get("min", 0.0)
                t["matches"] += 1 if row.get("min", 0.0) > 0 else 0
                t["starts"] += row.get("start", 0)
                for k in COUNTS:
                    t[k] += row.get(k, 0)
                team = row.get("team") or ""
                t["teams"][team] = round(t["teams"].get(team, 0.0) + row.get("min", 0.0), 1)
        for t in totals.values():
            t["min"] = round(t["min"], 1)
        self._totals[(league, season)] = (version, totals)
        return totals

    # ------------------------------------------------------------------ run status (written by the fetching process)

    def set_status(self, league: str, season: int, **fields) -> dict:
        key = f"{STATUS_PREFIX}{league}:{season}"
        status = {**(self.store.kv_get(key) or {}), **fields, "updated": time.time()}
        self.store.kv_set(key, status)
        return status

    def status(self, league: str, season: int) -> dict | None:
        status = self.store.kv_get(f"{STATUS_PREFIX}{league}:{season}")
        if status and status.get("running") and time.time() - status.get("updated", 0) > STALE_AFTER:
            status = {**status, "running": False, "stalled": True}
        return status
