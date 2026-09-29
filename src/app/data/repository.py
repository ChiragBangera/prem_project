"""Typed, cached access to football data.

Everything above this layer (analytics, insights, API) asks the repository for
``LeagueSeason`` / ``PlayerPage`` / ``MatchPage`` objects and never talks to the
network or the cache directly. The repository:

* serves fresh cache hits instantly, from memory when possible;
* fetches misses and expired entries through the provider, once (concurrent
  requests for the same thing share a single upstream call);
* falls back to stale data - clearly flagged - when a refresh fails or is slow,
  instead of failing the whole page;
* never expires payloads that can no longer change (finished seasons, played
  matches);
* refuses the network entirely in offline mode.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Generic, Protocol, TypeVar

from app.config import Settings
from app.errors import AppError, DataUnavailable, NotFound, UpstreamError
from app.leagues import current_season

from .models import LeagueSeason, MatchPage, PlayerPage, TeamPage
from .normalize import (
    normalize_league,
    normalize_match_page,
    normalize_player_page,
    normalize_team_page,
)
from .store import Record, Store

T = TypeVar("T")
FOREVER = float("inf")
REFRESH_WAIT = 8.0  # how long a request waits on a refresh before serving stale data


class Provider(Protocol):
    source: str

    async def league(self, league: str, season: int) -> dict: ...
    async def team(self, team: str, season: int) -> dict: ...
    async def player(self, player_id: int) -> dict: ...
    async def match(self, match_id: int) -> dict: ...
    async def search_players(self, query: str) -> list[dict]: ...
    async def close(self) -> None: ...


@dataclass(slots=True)
class Meta:
    source: str  # understat | demo
    fetched_at: float | None
    stale: bool = False
    error: str | None = None
    complete: bool = False

    def to_dict(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        return {
            "source": self.source,
            "fetched_at": _iso(self.fetched_at),
            "age_seconds": None if self.fetched_at is None else max(0, round(now - self.fetched_at)),
            "stale": self.stale,
            "error": self.error,
            "complete": self.complete,
        }


@dataclass(slots=True)
class Fetched(Generic[T]):
    data: T
    meta: Meta


def _iso(stamp: float | None) -> str | None:
    if stamp is None:
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class _Entry:
    fetched_at: float
    complete: bool
    source: str
    value: Any


class Repository:
    def __init__(
        self,
        store: Store,
        provider: Provider,
        settings: Settings,
        *,
        clock: Callable[[], float] = time.time,
        memory_budget: int = 400,
    ):
        self.store = store
        self.provider = provider
        self.settings = settings
        self._clock = clock
        self._mem: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._weights: dict[tuple[str, str], int] = {}
        self._budget = memory_budget
        self._inflight: dict[tuple[str, str], asyncio.Task] = {}

    # ------------------------------------------------------------------ public API

    async def league(
        self, league: str, season: int, *, refresh: bool = False, force: bool = False
    ) -> Fetched[LeagueSeason]:
        return await self._load(
            "league",
            f"{league}:{season}",
            fetch=lambda: self.provider.league(league, season),
            parse=lambda raw: normalize_league(raw, league, season),
            is_complete=lambda ls: self._league_complete(ls),
            ttl=lambda ls, complete: self._league_ttl(ls, complete),
            refresh=refresh,
            force=force,
            weight=10,
        )

    async def player(
        self, player_id: int, *, refresh: bool = False, force: bool = False
    ) -> Fetched[PlayerPage]:
        return await self._load(
            "player",
            str(int(player_id)),
            fetch=lambda: self.provider.player(int(player_id)),
            parse=lambda raw: normalize_player_page(raw, int(player_id)),
            is_complete=lambda page: False,
            ttl=lambda page, complete: self._player_ttl(page),
            refresh=refresh,
            force=force,
            weight=1,
        )

    async def match(
        self, match_id: int, *, final: bool = True, refresh: bool = False, force: bool = False
    ) -> Fetched[MatchPage]:
        return await self._load(
            "match",
            str(int(match_id)),
            fetch=lambda: self.provider.match(int(match_id)),
            parse=lambda raw: normalize_match_page(raw, int(match_id)),
            is_complete=lambda page: final,
            ttl=lambda page, complete: FOREVER if complete else self.settings.ttl_match_open,
            refresh=refresh,
            force=force,
            weight=1,
        )

    async def team_page(
        self, team: str, season: int, *, refresh: bool = False, force: bool = False
    ) -> Fetched[TeamPage]:
        return await self._load(
            "team",
            f"{team}:{season}",
            fetch=lambda: self.provider.team(team, season),
            parse=lambda raw: normalize_team_page(raw, team, season),
            is_complete=lambda page: season < current_season(),
            ttl=lambda page, complete: FOREVER if complete else self.settings.ttl_team_live,
            refresh=refresh,
            force=force,
            weight=2,
        )

    async def search_remote(self, query: str) -> list[dict]:
        if self.settings.offline:
            return []
        try:
            return await self.provider.search_players(query)
        except AppError:
            return []

    # ------------------------------------------------------------------ inspection

    def cached_leagues(self) -> list[dict]:
        """League-seasons present in the local cache (used for search and the Data page)."""
        out = []
        for key, fetched_at, complete in self.store.keys("league"):
            league, _, season = key.partition(":")
            out.append({"league": league, "season": int(season), "fetched_at": fetched_at, "complete": complete})
        return out

    def version(self, kind: str, key: str) -> float:
        """Monotonic-ish token: changes whenever the cached payload is replaced."""
        entry = self._mem.get((kind, key))
        if entry is not None:
            return entry.fetched_at
        meta = self.store.meta(kind, key)
        return meta[0] if meta else 0.0

    def invalidate(self, kind: str | None = None) -> None:
        if kind is None:
            self._mem.clear()
            self._weights.clear()
            return
        for key in [k for k in self._mem if k[0] == kind]:
            self._mem.pop(key, None)
            self._weights.pop(key, None)

    async def close(self) -> None:
        pending = [t for t in self._inflight.values() if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await self.provider.close()

    # ------------------------------------------------------------------ freshness policy

    def _league_complete(self, ls: LeagueSeason) -> bool:
        return bool(ls.fixtures) and not ls.upcoming

    def _league_ttl(self, ls: LeagueSeason, complete: bool) -> float:
        if complete:
            return FOREVER
        now = self._clock()
        soonest = None
        for fixture in ls.fixtures:
            try:
                kickoff = datetime.fromisoformat(fixture.dt).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
            gap = abs(kickoff - now)
            soonest = gap if soonest is None else min(soonest, gap)
        # Around matchdays xG lands within hours: refresh often. Quiet weeks can be lazy.
        if soonest is not None and soonest < 48 * 3600:
            return 2 * 3600
        return float(self.settings.ttl_league_live * 4)

    def _player_ttl(self, page: PlayerPage) -> float:
        if page.shots and page.shots[-1].season >= current_season():
            return float(self.settings.ttl_player_live)
        return float(self.settings.ttl_player_live * 30)

    # ------------------------------------------------------------------ core loader

    async def _load(
        self,
        kind: str,
        key: str,
        *,
        fetch: Callable[[], Awaitable[dict]],
        parse: Callable[[dict], T],
        is_complete: Callable[[T], bool],
        ttl: Callable[[T, bool], float],
        refresh: bool,
        force: bool = False,
        weight: int,
    ) -> Fetched[T]:
        entry = self._recall(kind, key)
        if entry is None:
            record = await asyncio.to_thread(self.store.get, kind, key)
            if record is not None:
                entry = await self._entry_from_record(record, parse, is_complete)
                if entry is not None:
                    self._remember(kind, key, entry, weight)

        if entry is not None and not refresh and self._is_fresh(entry, ttl):
            return Fetched(entry.value, Meta(entry.source, entry.fetched_at, complete=entry.complete))
        if entry is not None and refresh and entry.complete and not force:
            return Fetched(entry.value, Meta(entry.source, entry.fetched_at, complete=True))

        if self.settings.offline:
            if entry is not None:
                return Fetched(
                    entry.value,
                    Meta(entry.source, entry.fetched_at, stale=True, error="Offline mode: serving cached data."),
                )
            raise DataUnavailable(
                f"No cached {kind} data for {key} and offline mode is on.",
                hint="Turn offline mode off, or run `prem sync` while online.",
            )

        task = self._inflight.get((kind, key))
        if task is None:
            task = asyncio.create_task(self._fetch_and_store(kind, key, fetch, parse, is_complete, weight))
            self._inflight[(kind, key)] = task
            task.add_done_callback(lambda t, k=(kind, key): self._finish(k, t))

        try:
            if entry is not None:
                new_entry = await asyncio.wait_for(asyncio.shield(task), timeout=REFRESH_WAIT)
            else:
                new_entry = await asyncio.shield(task)
        except (asyncio.TimeoutError, AppError, ValueError) as exc:
            if entry is not None:
                reason = "Refresh is taking too long; showing cached data." if isinstance(exc, asyncio.TimeoutError) else str(exc)
                return Fetched(entry.value, Meta(entry.source, entry.fetched_at, stale=True, error=reason))
            if isinstance(exc, AppError):
                raise self._translate(exc, kind, key)
            raise UpstreamError(f"Could not read the {kind} data for {key}: {exc}") from exc
        return Fetched(new_entry.value, Meta(new_entry.source, new_entry.fetched_at, complete=new_entry.complete))

    def _finish(self, key: tuple[str, str], task: asyncio.Task) -> None:
        self._inflight.pop(key, None)
        if not task.cancelled():
            task.exception()  # mark retrieved; waiters already saw it

    async def _fetch_and_store(self, kind, key, fetch, parse, is_complete, weight) -> _Entry:
        raw = await fetch()
        value = parse(raw)
        complete = bool(is_complete(value))
        source = getattr(self.provider, "source", "understat")
        stamp = await asyncio.to_thread(
            self.store.put, kind, key, raw, source=source, complete=complete, fetched_at=self._clock()
        )
        entry = _Entry(stamp, complete, source, value)
        self._remember(kind, key, entry, weight)
        return entry

    async def _entry_from_record(self, record: Record, parse, is_complete) -> _Entry | None:
        try:
            value = await asyncio.to_thread(parse, record.body)
        except (ValueError, TypeError, KeyError):
            return None  # unreadable cache row: treat as a miss
        return _Entry(record.fetched_at, record.complete or bool(is_complete(value)), record.source, value)

    def _is_fresh(self, entry: _Entry, ttl: Callable[[Any, bool], float]) -> bool:
        limit = ttl(entry.value, entry.complete)
        return limit == FOREVER or (self._clock() - entry.fetched_at) < limit

    def _translate(self, exc: AppError, kind: str, key: str) -> AppError:
        if isinstance(exc, UpstreamError) and exc.upstream_status == 404:
            return NotFound(f"Understat has no {kind} '{key}'.", hint=exc.hint)
        return exc

    # ------------------------------------------------------------------ memory cache

    def _recall(self, kind: str, key: str) -> _Entry | None:
        entry = self._mem.get((kind, key))
        if entry is not None:
            self._mem.move_to_end((kind, key))
        return entry

    def _remember(self, kind: str, key: str, entry: _Entry, weight: int) -> None:
        self._mem[(kind, key)] = entry
        self._mem.move_to_end((kind, key))
        self._weights[(kind, key)] = weight
        while sum(self._weights[k] for k in self._mem) > self._budget and len(self._mem) > 1:
            oldest, _ = next(iter(self._mem.items()))
            self._mem.pop(oldest)
            self._weights.pop(oldest, None)
