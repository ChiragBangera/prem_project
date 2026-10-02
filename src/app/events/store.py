"""Event data in the local store: bronze (raw page), silver (compact events), gold (counters), and what a season adds up to.

Everything about a match is kept under the same key, ``LEAGUE:SEASON:GAMEID``, in three kinds of the payload table:

* ``ws_raw``    the page as WhoScored served it (see :mod:`app.events.raw`), written once and never changed;
* ``ws_silver`` the compact columnar events and lineups (:mod:`app.events.silver`), derived from raw;
* ``ws_gold``   per-player and per-team counters (:mod:`app.events.counters`), derived from silver.

Silver and gold carry the version of the code that made them. When a definition changes the version is bumped and
:meth:`EventStore.ensure_current` rebuilds the changed layers *from the layer below*, offline: nothing is fetched again.

The fetching process (``prem events sync`` or the automatic updater) and the app meet only here, through the store.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Callable

from app.data.store import Store

from . import counters as C
from . import raw as R
from . import silver as SV

STATUS_PREFIX = "events:run:"
DERIVED_MARK = "events:derived"   # kv: the (silver, gold) versions every stored match was last brought to
STALE_AFTER = 600.0               # a "running" status not updated for this long means the run died
KINDS = (R.RAW_KIND, SV.SILVER_KIND, C.GOLD_KIND)


def _key(league: str, season: int, game_id: int | str) -> str:
    return R.raw_key(league, season, game_id)


class EventStore:
    def __init__(self, store: Store):
        self.store = store
        self.raw = R.RawStore(store)
        self._agg: dict[tuple[str, int], tuple[tuple, dict]] = {}
        self._gold_cache: dict[str, dict] = {}
        self._locks: dict[tuple[str, int], threading.Lock] = defaultdict(threading.Lock)

    # ------------------------------------------------------------------ writing a match

    def ingest(self, league: str, season: int, game_id: int, doc: dict, *, fetched_at: float | None = None) -> bool:
        """Store a raw match and derive silver and gold from it at once. False if the document is not a usable match."""
        # the first match into a store that holds none: it, and every match added after it, is derived by this code, so say so
        # (otherwise the next start would take a store that was never out of date for one that needs rebuilding)
        first = self.store.kv_get(DERIVED_MARK) is None and not self.raw.seasons()
        if not self.raw.put(league, season, game_id, doc, fetched_at=fetched_at):
            return False
        self.derive(league, season, game_id, doc)
        if first:
            self.store.kv_set(DERIVED_MARK, self._derived_versions())
        return True

    def derive(self, league: str, season: int, game_id: int, doc: dict | None = None) -> bool:
        """(Re)build silver and gold for one stored match from its raw document."""
        doc = doc if doc is not None else self.raw.get(league, season, game_id)
        if doc is None:
            return False
        silver = SV.parse_match(doc, league=league, season=season, game_id=game_id)
        if silver is None:
            return False
        key = _key(league, season, game_id)
        gold = C.derive_match(SV.Match(silver))
        self.store.put(SV.SILVER_KIND, key, silver, source="derived", complete=True)
        self.store.put(C.GOLD_KIND, key, gold, source="derived", complete=True)
        self._gold_cache.pop(key, None)
        return True

    # ------------------------------------------------------------------ reading a match

    def has_match(self, league: str, season: int, game_id: int | str) -> bool:
        return self.raw.has(league, season, game_id)

    def match_ids(self, league: str, season: int) -> list[int]:
        return self.raw.ids(league, season)

    def seasons(self) -> list[tuple[str, int, int]]:
        """Every league-season with stored matches, as (league, season, matches)."""
        return self.raw.seasons()

    def silver(self, league: str, season: int, game_id: int | str) -> SV.Match | None:
        """The compact match, built from raw first if it is missing or was made by an older parser."""
        key = _key(league, season, game_id)
        record = self.store.get(SV.SILVER_KIND, key)
        if record is None or record.body.get("v") != SV.SILVER_VERSION:
            if not self.derive(league, season, int(game_id)):
                return None
            record = self.store.get(SV.SILVER_KIND, key)
        return SV.Match(record.body) if record else None

    def gold(self, league: str, season: int, game_id: int | str) -> dict | None:
        key = _key(league, season, game_id)
        hit = self._gold_cache.get(key)
        if hit is not None:
            return hit
        record = self.store.get(C.GOLD_KIND, key)
        if record is None or record.body.get("v") != C.GOLD_VERSION:
            if not self.derive(league, season, int(game_id)):
                return None
            record = self.store.get(C.GOLD_KIND, key)
        if record is None:
            return None
        if len(self._gold_cache) > 2500:
            self._gold_cache.clear()
        self._gold_cache[key] = record.body
        return record.body

    # ------------------------------------------------------------------ keeping derived layers current

    def _derived_versions(self) -> list[int]:
        return [SV.SILVER_VERSION, C.GOLD_VERSION]

    def pending_rebuild(self, league: str | None = None, season: int | None = None) -> int:
        """How many stored matches have no silver/gold made by the current code. Cheap when nothing changed (one key read)."""
        wanted = {(l, s) for l, s, _n in self.seasons() if (league is None or l == league) and (season is None or s == season)}
        if not wanted:
            return 0
        marked = self.store.kv_get(DERIVED_MARK) == self._derived_versions()
        missing = 0
        for l, s in wanted:
            have_s = {k for k, _t in self.store.keys_prefix(SV.SILVER_KIND, f"{l}:{s}:")}
            have_g = {k for k, _t in self.store.keys_prefix(C.GOLD_KIND, f"{l}:{s}:")}
            for gid in self.raw.ids(l, s):
                k = _key(l, s, gid)
                if k not in have_s or k not in have_g:
                    missing += 1
        if missing == 0 and not marked:
            return sum(len(self.raw.ids(l, s)) for l, s in wanted)  # same keys, older code: all of them are out of date
        return missing

    def ensure_current(self, league: str | None = None, season: int | None = None, *, progress: Callable[[int, int], None] | None = None,
                       stop: Callable[[], bool] | None = None) -> dict:
        """Bring silver and gold up to the current code for every stored match. Returns ``{"rebuilt", "skipped", "failed", "total"}``."""
        wanted = sorted((l, s) for l, s, _n in self.seasons() if (league is None or l == league) and (season is None or s == season))
        marked = self.store.kv_get(DERIVED_MARK) == self._derived_versions()
        todo: list[tuple[str, int, int]] = []
        skipped = 0
        for l, s in wanted:
            have_s = {k for k, _t in self.store.keys_prefix(SV.SILVER_KIND, f"{l}:{s}:")}
            have_g = {k for k, _t in self.store.keys_prefix(C.GOLD_KIND, f"{l}:{s}:")}
            for gid in self.raw.ids(l, s):
                k = _key(l, s, gid)
                if marked and k in have_s and k in have_g:
                    skipped += 1
                else:
                    todo.append((l, s, gid))
        rebuilt = failed = 0
        for n, (l, s, gid) in enumerate(todo, start=1):
            if stop is not None and stop():
                break
            if self.derive(l, s, gid):
                rebuilt += 1
            else:
                failed += 1
            if progress is not None and (n % 25 == 0 or n == len(todo)):
                progress(n, len(todo))
        if league is None and season is None and not failed and rebuilt + skipped == sum(len(self.raw.ids(l, s)) for l, s in wanted):
            self.store.kv_set(DERIVED_MARK, self._derived_versions())
        self._agg.clear()
        return {"rebuilt": rebuilt, "skipped": skipped, "failed": failed, "total": len(todo) + skipped}

    def version(self, league: str, season: int) -> tuple:
        """Changes whenever a match is added or the code that derives from matches changes: results built on it use it to know they are stale."""
        count, newest = self.raw.stamp(league, season)
        return (count, newest, SV.SILVER_VERSION, C.GOLD_VERSION)

    # ------------------------------------------------------------------ what a season adds up to

    def season(self, league: str, season: int) -> dict:
        """The league-season rolled up, memoised until a match is added.

        ``players``: WhoScored player id -> ``{id, name, matches, starts, teams {club: minutes}, pos {lineup position: matches started},
        c {counter: sum}, log [(game, club, minutes, started)]}``.
        ``teams``: club name -> ``{name, matches, c {for}, a {against}, formations {name: minutes}, managers {name: matches},
        age_sum, log [{game, date, home, opp, gf, ga, c, a}]}``.
        """
        version = self.version(league, season)
        with self._locks[(league, season)]:
            hit = self._agg.get((league, season))
            if hit and hit[0] == version:
                return hit[1]
            agg = self._rollup(league, season)
            self._agg[(league, season)] = (version, agg)
            return agg

    def _rollup(self, league: str, season: int) -> dict:
        players: dict[int, dict] = {}
        teams: dict[str, dict] = {}
        games = 0
        for gid in self.raw.ids(league, season):
            g = self.gold(league, season, gid)
            if not g:
                continue
            games += 1
            names = [t["name"] for t in g["teams"]]
            for r in g["players"]:
                c = r["c"]
                p = players.get(r["id"])
                if p is None:
                    p = players[r["id"]] = {"id": r["id"], "name": r["name"], "matches": 0, "starts": 0, "teams": {}, "pos": {}, "c": defaultdict(float), "log": []}
                club = names[r["tm"]]
                minutes = c.get("min", 0.0)
                p["teams"][club] = round(p["teams"].get(club, 0.0) + minutes, 1)
                if minutes > 0:
                    p["matches"] += 1
                    p["log"].append((gid, club, minutes, bool(r["start"])))
                if r["start"]:
                    p["starts"] += 1
                    p["pos"][r["pos"]] = p["pos"].get(r["pos"], 0) + 1
                for k, v in c.items():
                    p["c"][k] += v
            for idx, t in enumerate(g["teams"]):
                tt = teams.get(t["name"])
                if tt is None:
                    tt = teams[t["name"]] = {"name": t["name"], "matches": 0, "c": defaultdict(float), "a": defaultdict(float), "formations": defaultdict(float),
                                             "managers": defaultdict(int), "age_sum": 0.0, "age_n": 0, "log": []}
                tt["matches"] += 1
                for k, v in t["c"].items():
                    tt["c"][k] += v
                for k, v in g["teams"][1 - idx]["c"].items():
                    tt["a"][k] += v
                for k, v in t["formations"].items():
                    tt["formations"][k] += v
                if t["manager"]:
                    tt["managers"][t["manager"]] += 1
                if t["avg_age"]:
                    tt["age_sum"] += t["avg_age"]
                    tt["age_n"] += 1
                tt["log"].append({"game": gid, "date": g["date"], "home": t["side"] == "h", "opp": g["teams"][1 - idx]["name"], "gf": t["gf"], "ga": t["ga"],
                                  "score": g.get("score"), "formation": t["formation"], "manager": t["manager"], "c": t["c"], "a": g["teams"][1 - idx]["c"]})
        for p in players.values():
            p["c"] = _clean(p["c"])
        for t in teams.values():
            t["c"], t["a"] = _clean(t["c"]), _clean(t["a"])
            t["formations"] = {k: round(v) for k, v in sorted(t["formations"].items(), key=lambda kv: -kv[1])}
            t["managers"] = dict(t["managers"])
            t["log"].sort(key=lambda r: (r["date"], r["game"]))
        return {"league": league, "season": season, "games": games, "players": players, "teams": teams}

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


def _clean(counts: dict) -> dict:
    return {k: (round(v, 2) if isinstance(v, float) and not float(v).is_integer() else int(v)) for k, v in counts.items() if v}
