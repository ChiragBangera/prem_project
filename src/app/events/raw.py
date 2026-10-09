"""Bronze layer for WhoScored: the match document exactly as the website served it, kept in the local store.

Why keep the raw document? The first version of the event pipeline summed a match into a handful of counters and threw the
rest away. A new chart, a new definition or a pitch map then meant fetching the match again (15 seconds each, hours for a
season). Here every match is stored once, untouched and compressed (~100 KB), and everything else (the compact event arrays
in :mod:`app.events.silver`, the counters in :mod:`app.events.counters`) is *derived* from it, offline, as often as needed.

Rules of this layer:

* a document is stored only if it looks like a real match (events, both teams); anything else is rejected, never half-stored;
* a page read before the final whistle (half time, or a match still in play) is kept apart, as *provisional*, under its own kind
  (``ws_live``). Everything that adds up seasons, links matches or cleans the download cache reads ``ws_raw`` only, so a half-played
  match can never be mistaken for a finished one; the page read at full time replaces it;
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
LIVE_KIND = "ws_live"   # pages read before the final whistle: provisional, replaced by the full-time read
SOURCE = "whoscored"
FINAL_STATUS = 6        # WhoScored's statusCode for a finished match (its page then says elapsed "FT")

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


def match_state(doc: dict) -> str:
    """``"final"`` when the page says the match is over, else ``"live"`` (in play, or at half time).

    WhoScored's match centre is a live page: the same address serves the first half, half time and the finished match, and says which
    with ``statusCode`` (6 when finished) and ``elapsed`` ("HT", "FT", or a minute). A page with neither field is older than these
    checks and was only ever read after the match, so it counts as final.
    """
    status, elapsed = doc.get("statusCode"), str(doc.get("elapsed") or "").strip().upper()
    if status is None and not elapsed:
        return "final"
    return "final" if status == FINAL_STATUS or elapsed == "FT" else "live"


class RawStore:
    """Read and write raw WhoScored matches. A thin, typed wrapper over the payload store."""

    def __init__(self, store: Store):
        self.store = store

    def has(self, league: str, season: int, game_id: int | str) -> bool:
        return self.store.meta(RAW_KIND, raw_key(league, season, game_id)) is not None

    def get(self, league: str, season: int, game_id: int | str) -> dict | None:
        record = self.store.get(RAW_KIND, raw_key(league, season, game_id))
        return record.body if record else None

    def put(self, league: str, season: int, game_id: int | str, doc: dict, *, fetched_at: float | None = None) -> str | None:
        """Store a match: ``"final"`` when it is over (kept for good), ``"live"`` when it was read before the final whistle (kept apart as
        provisional), None (and nothing stored) when the document is not a usable match."""
        if not looks_like_match(doc):
            return None
        key = raw_key(league, season, game_id)
        state = match_state(doc)
        if state == "final":
            self.store.put(RAW_KIND, key, doc, source=SOURCE, complete=True, fetched_at=fetched_at)
            self.store.delete(LIVE_KIND, key)
        else:
            self.store.put(LIVE_KIND, key, doc, source=SOURCE, complete=False, fetched_at=fetched_at)
        return state

    def live(self, league: str, season: int, game_id: int | str) -> tuple[dict, float] | None:
        """The provisional page of a match read before the final whistle, and when it was read; None when there is none."""
        record = self.store.get(LIVE_KIND, raw_key(league, season, game_id))
        return (record.body, record.fetched_at) if record else None

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
    """Store every cached finished match page that is not stored yet. Returns ``{"imported", "already", "rejected", "provisional", "files"}``."""
    raw = RawStore(store)
    wanted = set(only) if only is not None else None
    have: dict[tuple[str, int], set[int]] = {}
    out = {"imported": 0, "already": 0, "rejected": 0, "provisional": 0, "files": 0}
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
        if doc is not None and match_state(doc) != "final":
            out["provisional"] += 1   # a page read before the final whistle: the fetcher reads the match again, not the cache
            continue
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
