"""The event fetcher's memory of matches it could not read, and the switches a person uses to steer it.

**Failed matches.** A match that fails is not tried again on every run (a page WhoScored cannot serve would otherwise cost a browser
visit each time, for ever). It is retried by itself a few times, half a day apart; after that it waits for a person, who can ask for it
again ("Retry now") or tell the fetcher to leave it alone ("Skip"). A match that is stored is forgotten here.

**Control.** ``paused`` stops new runs and the current one at the next match, and lasts until it is lifted (restarts included).
``stop_at`` ends the run in progress at the next match without pausing anything after it. The fetcher runs in its own process and
reads these from the store between matches, so stopping is clean on every system (a hard kill on Windows could lose the match in hand).
"""

from __future__ import annotations

from typing import Any

FAILED_PREFIX = "events:failed:"
CONTROL_KEY = "events:control"
MAX_ATTEMPTS = 3                 # automatic tries before a match waits for a person
RETRY_AFTER = 12 * 3600.0        # seconds between automatic tries


def _key(league: str, season: int) -> str:
    return f"{FAILED_PREFIX}{league}:{season}"


def failures(store: Any, league: str, season: int) -> dict[int, dict]:
    return {int(k): v for k, v in (store.kv_get(_key(league, season)) or {}).items()}


def note_failure(store: Any, league: str, season: int, game: int, *, label: str, date: str | None, error: str, now: float) -> dict:
    book = store.kv_get(_key(league, season)) or {}
    entry = book.get(str(game)) or {"attempts": 0, "skip": False}
    entry.update(label=label, date=date, error=error[:200], at=now, attempts=int(entry.get("attempts", 0)) + 1)
    book[str(game)] = entry
    store.kv_set(_key(league, season), book)
    return entry


def forget(store: Any, league: str, season: int, game: int) -> None:
    book = store.kv_get(_key(league, season)) or {}
    if book.pop(str(game), None) is not None:
        store.kv_set(_key(league, season), book) if book else store.kv_delete(_key(league, season))


def set_skip(store: Any, league: str, season: int, game: int, skip: bool) -> dict | None:
    book = store.kv_get(_key(league, season)) or {}
    entry = book.get(str(game))
    if entry is None:
        return None
    entry["skip"] = bool(skip)
    if not skip:
        entry["attempts"] = 0            # un-skipping is a fresh start
    store.kv_set(_key(league, season), book)
    return entry


def due(entry: dict | None, now: float) -> bool:
    """Whether the fetcher may try this match again by itself."""
    if entry is None:
        return True
    if entry.get("skip"):
        return False
    return int(entry.get("attempts", 0)) < MAX_ATTEMPTS and now - float(entry.get("at", 0.0)) >= RETRY_AFTER


def waiting_for_person(entry: dict) -> bool:
    return bool(entry.get("skip")) or int(entry.get("attempts", 0)) >= MAX_ATTEMPTS


def control(store: Any) -> dict:
    return {"paused": False, "stop_at": 0.0, **(store.kv_get(CONTROL_KEY) or {})}


def set_control(store: Any, **fields) -> dict:
    merged = {**control(store), **fields}
    store.kv_set(CONTROL_KEY, merged)
    return merged


def stop_reason(store: Any, run_started: float) -> str | None:
    """Why the run that started at ``run_started`` must end now, or None."""
    c = control(store)
    if c.get("paused"):
        return "paused"
    if float(c.get("stop_at") or 0) >= run_started:
        return "stopped"
    return None
