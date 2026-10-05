"""Bronze layer for WhoScored: the match document exactly as the website served it, kept in the local store.

Why keep the raw document? The first version of the event pipeline summed a match into a handful of counters and threw the
rest away. A new chart, a new definition or a pitch map then meant fetching the match again (15 seconds each, hours for a
season). Here every match is stored once, untouched and compressed (~100 KB), and everything else (the compact event arrays
in :mod:`app.events.silver`, the counters in :mod:`app.events.counters`) is *derived* from it, offline, as often as needed.

Rules of this layer:

* a document is stored only if it looks like a real finished match (events, both teams); anything else is rejected, never
  half-stored;
* it is idempotent: storing the same match again changes nothing;
* it never goes to the network. Fetching lives in :mod:`app.events.fetch`; :func:`import_soccerdata_cache` here adopts
  matches ``soccerdata`` already wrote to its own cache folder, so what was fetched before the app kept raw data is not lost.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from collections.abc import Callable, Iterable

from app.data.store import Store

RAW_KIND = "ws_raw"
SOURCE = "whoscored"

#: soccerdata's league names (and the folder names it caches under) -> this app's league codes
SOCCERDATA_LEAGUES = {
    "ENG-Premier League": "EPL", "ESP-La Liga": "La_liga", "GER-Bundesliga": "Bundesliga", "ITA-Serie A": "Serie_A", "FRA-Ligue 1": "Ligue_1",
}
LEAGUE_TO_SOCCERDATA = {code: name for name, code in SOCCERDATA_LEAGUES.items()}


def raw_key(league: str, season: int, game_id: int | str) -> str:
    return f"{league}:{season}:{int(game_id)}"


def season_code(season: int) -> str:
    """soccerdata's name for a season: 2025 -> '2526'."""
    return f"{season % 100:02d}{(season + 1) % 100:02d}"


def season_from_code(code: str) -> int | None:
    if len(code) == 4 and code.isdigit():
        return 2000 + int(code[:2])
    return None


def looks_like_match(doc) -> bool:
    """A finished-match document: events, and both teams with players."""
    if not isinstance(doc, dict):
        return False
    events = doc.get("events")
    if not isinstance(events, list) or len(events) < 50:
        return False
    return all(isinstance(doc.get(side), dict) and doc[side].get("players") for side in ("home", "away"))


class RawStore:
    """Read and write raw WhoScored matches. A thin, typed wrapper over the payload store."""

    def __init__(self, store: Store):
        self.store = store

    def has(self, league: str, season: int, game_id: int | str) -> bool:
        return self.store.meta(RAW_KIND, raw_key(league, season, game_id)) is not None

    def get(self, league: str, season: int, game_id: int | str) -> dict | None:
        record = self.store.get(RAW_KIND, raw_key(league, season, game_id))
        return record.body if record else None

    def put(self, league: str, season: int, game_id: int | str, doc: dict, *, fetched_at: float | None = None) -> bool:
        """Store a match. False (and nothing stored) when the document is not a usable match."""
        if not looks_like_match(doc):
            return False
        self.store.put(RAW_KIND, raw_key(league, season, game_id), doc, source=SOURCE, complete=True, fetched_at=fetched_at)
        return True

    def ids(self, league: str, season: int) -> list[int]:
        prefix = f"{league}:{season}:"
        return sorted(int(k[len(prefix):]) for k, _t in self.store.keys_prefix(RAW_KIND, prefix) if k[len(prefix):].isdigit())

    def seasons(self) -> list[tuple[str, int, int]]:
        """Every league-season with raw matches, as (league, season, matches)."""
        counts: dict[tuple[str, int], int] = {}
        for key, _t, _c in self.store.keys(RAW_KIND):
            league, _, rest = key.partition(":")
            season, _, _game = rest.partition(":")
            if season.isdigit():
                counts[(league, int(season))] = counts.get((league, int(season)), 0) + 1
        return sorted((league, season, n) for (league, season), n in counts.items())

    def stamp(self, league: str, season: int) -> tuple[int, float]:
        """Changes whenever a match is added to the league-season: derived results use it to know they are out of date."""
        found = [t for _k, t in self.store.keys_prefix(RAW_KIND, f"{league}:{season}:")]
        return (len(found), max(found, default=0.0))


# ------------------------------------------------------------------ adopting what soccerdata already cached


def cached_files(data_dir: Path) -> Iterable[tuple[str, int, int, Path]]:
    """``(league, season, game_id, path)`` for every match page in soccerdata's cache under ``<data dir>/soccerdata``."""
    root = data_dir / "soccerdata" / "data" / "WhoScored" / "events"
    if not root.is_dir():
        return
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        name, _, code = folder.name.rpartition("_")
        league, season = SOCCERDATA_LEAGUES.get(name), season_from_code(code)
        if league is None or season is None:
            continue
        for path in sorted(folder.glob("*.json")):
            if path.stem.isdigit():
                yield league, season, int(path.stem), path


def read_match_file(path: Path) -> dict | None:
    """One cached match page, or None if it is empty, unreadable or not a match (soccerdata writes ``null`` for a page with no data)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if looks_like_match(doc) else None


def import_soccerdata_cache(
    store: Store, data_dir: Path, *, only: Iterable[tuple[str, int]] | None = None, log: Callable[[str], None] | None = None,
    stop: Callable[[], bool] | None = None,
) -> dict:
    """Store every cached match page that is not stored yet. Returns ``{"imported", "already", "rejected", "files"}``."""
    raw = RawStore(store)
    wanted = set(only) if only is not None else None
    have: dict[tuple[str, int], set[int]] = {}
    out = {"imported": 0, "already": 0, "rejected": 0, "files": 0}
    for league, season, game_id, path in cached_files(data_dir):
        if wanted is not None and (league, season) not in wanted:
            continue
        if stop is not None and stop():
            break
        out["files"] += 1
        known = have.get((league, season))
        if known is None:
            known = have[(league, season)] = set(raw.ids(league, season))
        if game_id in known:
            out["already"] += 1
            continue
        doc = read_match_file(path)
        if doc is None or not raw.put(league, season, game_id, doc, fetched_at=path.stat().st_mtime):
            out["rejected"] += 1
            continue
        known.add(game_id)
        out["imported"] += 1
        if log and out["imported"] % 50 == 0:
            log(f"  imported {out['imported']} matches...")
    return out


def reclaimable_bytes(store: Store, data_dir: Path) -> int:
    """Bytes of soccerdata match pages whose raw copy is already in the store, so deleting them loses nothing."""
    raw = RawStore(store)
    have: dict[tuple[str, int], set[int]] = {}
    total = 0
    for league, season, game_id, path in cached_files(data_dir):
        known = have.get((league, season))
        if known is None:
            known = have[(league, season)] = set(raw.ids(league, season))
        if game_id in known:
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def reclaim(store: Store, data_dir: Path) -> dict:
    """Delete soccerdata's copy of every match whose raw document is safely in the store. Returns ``{"deleted", "bytes"}``."""
    raw = RawStore(store)
    have: dict[tuple[str, int], set[int]] = {}
    deleted = freed = 0
    for league, season, game_id, path in list(cached_files(data_dir)):
        known = have.get((league, season))
        if known is None:
            known = have[(league, season)] = set(raw.ids(league, season))
        if game_id not in known:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            continue
        deleted += 1
        freed += size
    return {"deleted": deleted, "bytes": freed, "at": time.time()}
