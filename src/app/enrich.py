"""Background enrichment: exact birthdates (club squad lists), the ages squad lists leave out (Wikidata) and favourite positions
(Understat player pages).

All are slow, network-bound and optional, so they must never block a page. A
page renders immediately with what is known; enrichment fills the rest in the
background, and the UI polls ``status()`` to refresh when it lands.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

from app.data.repository import Repository
from app.data.rosters import RosterClient
from app.data.store import Store
from app.data.wikidata import BirthdateResolver
from app.errors import AppError

log = logging.getLogger("prem.enrich")


@dataclass
class Progress:
    kind: str
    total: int = 0
    done: int = 0
    failed: int = 0
    running: bool = False
    last_error: str | None = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "total": self.total, "done": self.done, "failed": self.failed,
                "running": self.running, "last_error": self.last_error}


class FavoriteIndex:
    """player id -> Understat favourite-position code, persisted as tiny store rows."""

    def __init__(self, store: Store):
        self.store = store
        self._cache: dict[int, str | None] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        for key, _fetched, _complete in self.store.keys("fav"):
            record = self.store.get("fav", key)
            if record is not None:
                self._cache[int(key)] = record.body.get("pos")
        self._loaded = True

    def get(self, pid: int) -> str | None:
        self._load()
        return self._cache.get(pid)

    def known(self, pid: int) -> bool:
        self._load()
        return pid in self._cache

    def put(self, pid: int, pos: str | None) -> None:
        self._load()
        self._cache[pid] = pos
        self.store.put("fav", str(pid), {"pos": pos}, source="understat", complete=True)

    def __len__(self) -> int:
        self._load()
        return len(self._cache)


class Enricher:
    def __init__(self, repo: Repository, store: Store, resolver: BirthdateResolver, favorites: FavoriteIndex, *, batch: int = 4,
                 roster_client: RosterClient | None = None):
        self.repo = repo
        self.resolver = resolver
        self.favorites = favorites
        self.roster_client = roster_client
        self.epoch = 0  # bumped whenever new information lands, so derived caches know to rebuild
        self.ages = Progress("ages")
        self.roles = Progress("roles")
        self.rosters = Progress("rosters")
        self._tasks: dict[str, asyncio.Task] = {}
        self._batch = batch

    # ------------------------------------------------------------------ scheduling

    def schedule_ages(self, people: Iterable[tuple[str, str | None]]) -> int:
        pending = [(n, t) for n, t in people if n and not self.resolver.known(n)]
        if not pending or "ages" in self._tasks and not self._tasks["ages"].done():
            return len(pending)
        self.ages = Progress("ages", total=len(pending), running=True)
        self._tasks["ages"] = asyncio.create_task(self._run_ages(pending))
        return len(pending)

    def schedule_rosters(self, targets: Iterable[tuple[str, int]]) -> int:
        """Fetch, in the background, the squad lists (exact birthdates) that these league-seasons lack. Returns how many are waiting."""
        if self.roster_client is None:
            return 0
        pending = [t for t in dict.fromkeys(targets) if self.roster_client.needs_fetch(*t)]
        if not pending or "rosters" in self._tasks and not self._tasks["rosters"].done():
            return len(pending)
        self.rosters = Progress("rosters", total=len(pending), running=True)
        self._tasks["rosters"] = asyncio.create_task(self._run_rosters(pending))
        return len(pending)

    def squads_pending(self, targets: Iterable[tuple[str, int]]) -> bool:
        """True while squad lists for these league-seasons are being fetched or are about to be. Wikidata is only asked about the
        players the squad lists leave out, so it waits for them."""
        if self.roster_client is None:
            return False
        return self.rosters.running or any(self.roster_client.needs_fetch(*t) for t in targets)

    def schedule_roles(self, player_ids: Iterable[int], limit: int = 240) -> int:
        pending = [pid for pid in dict.fromkeys(player_ids) if not self.favorites.known(pid)][:limit]
        if not pending or "roles" in self._tasks and not self._tasks["roles"].done():
            return len(pending)
        self.roles = Progress("roles", total=len(pending), running=True)
        self._tasks["roles"] = asyncio.create_task(self._run_roles(pending))
        return len(pending)

    # ------------------------------------------------------------------ workers

    async def _run_ages(self, people: list[tuple[str, str | None]]) -> None:
        try:
            for start in range(0, len(people), 40):
                chunk = people[start : start + 40]
                await self.resolver.resolve(chunk)
                self.ages.done += len(chunk)
                self.epoch += 1
        except Exception as exc:  # never let a background job crash the app
            self.ages.last_error = str(exc)[:200]
            log.warning("age enrichment failed: %s", exc)
        finally:
            self.ages.running = False

    async def _run_rosters(self, targets: list[tuple[str, int]]) -> None:
        client = self.roster_client
        try:
            for league, season in targets:
                before = client.version(league, season)
                try:
                    await client.ensure(league, season)
                except Exception as exc:  # never let a background job crash the app
                    self.rosters.failed += 1
                    client.last_error = f"{league} {season}: {str(exc)[:160]}"
                    client.cool_down()
                    log.warning("squad lists for %s %s failed: %s", league, season, exc)
                self.rosters.done += 1
                self.rosters.last_error = client.last_error
                if client.version(league, season) != before:
                    self.epoch += 1  # new birthdates: anything built from the old ones is stale
        finally:
            self.rosters.running = False

    async def _run_roles(self, ids: list[int]) -> None:
        sem = asyncio.Semaphore(self._batch)

        async def one(pid: int) -> None:
            async with sem:
                try:
                    fetched = await self.repo.player(pid)
                    self.favorites.put(pid, fetched.data.favorite_position)
                    self.roles.done += 1
                except AppError as exc:
                    self.roles.failed += 1
                    self.roles.last_error = exc.message[:200]
                except Exception as exc:
                    self.roles.failed += 1
                    self.roles.last_error = str(exc)[:200]
                if (self.roles.done + self.roles.failed) % 20 == 0:
                    self.epoch += 1

        try:
            await asyncio.gather(*(one(pid) for pid in ids))
        finally:
            self.roles.running = False
            self.epoch += 1

    # ------------------------------------------------------------------ status

    def status(self) -> dict:
        return {"ages": self.ages.to_dict(), "roles": self.roles.to_dict(), "rosters": self.rosters.to_dict(),
                "favorites_known": len(self.favorites), "epoch": self.epoch}

    @property
    def busy(self) -> bool:
        return self.ages.running or self.roles.running or self.rosters.running

    async def close(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
