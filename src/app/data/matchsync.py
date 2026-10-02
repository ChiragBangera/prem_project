"""Bulk-fetching every finished match page of a league season, politely and resumably.

A match page is small (a few KB) and, once Understat has settled its numbers, never changes. Having *all* of them for a
season is what makes scorers on the Matches page, exact minutes at each position, and shot-level aggregates (headers,
set pieces, shot distance) possible for every player, with no further requests. The work is idempotent and resumable:

* a match already stored and final is never fetched again;
* a match stored but not yet final (fetched hours after the whistle) is looked at again after ``ttl_match_open``;
* one failing page never stops the others; it is retried on the next pass, and the error is kept for the Data page;
* offline mode and demo data never go to the network from here.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Callable

from app.errors import AppError

from .models import Fixture, LeagueSeason
from .repository import Repository

SETTLE_HOURS = 36  # Understat revises a match's shots for a day or so; older than this and the page is final


def _kickoff(fixture: Fixture) -> float | None:
    try:
        return datetime.fromisoformat(fixture.dt).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


class MatchSync:
    def __init__(self, repo: Repository, *, concurrency: int = 4, clock: Callable[[], float] = time.time):
        self.repo = repo
        self._sem = asyncio.Semaphore(concurrency)
        self._clock = clock
        self.last_error: str | None = None

    def is_final(self, fixture: Fixture) -> bool:
        kickoff = _kickoff(fixture)
        return kickoff is not None and self._clock() - kickoff >= SETTLE_HOURS * 3600

    def needs_fetch(self, fixture: Fixture) -> bool:
        if not fixture.played:
            return False
        status = self.repo.match_status(fixture.id)
        if status is None:
            return True
        fetched_at, complete = status
        if complete:
            return False
        # stored early (or empty): look again once it can have settled, or after the open-match window
        return self.is_final(fixture) or self._clock() - fetched_at >= self.repo.settings.ttl_match_open

    def pending(self, ls: LeagueSeason) -> list[Fixture]:
        """Finished fixtures whose page is missing or not final yet, oldest first (so a stopped run leaves no gaps in the past)."""
        return sorted((f for f in ls.fixtures if self.needs_fetch(f)), key=lambda f: (f.dt, f.id))

    def coverage(self, ls: LeagueSeason) -> tuple[int, int]:
        """``(played fixtures with a stored page, played fixtures)``."""
        played = [f for f in ls.fixtures if f.played]
        return sum(1 for f in played if self.repo.match_status(f.id) is not None), len(played)

    async def _one(self, fixture: Fixture) -> bool:
        async with self._sem:
            try:
                await self.repo.match(fixture.id, final=self.is_final(fixture), expect_shots=bool((fixture.hxg or 0) + (fixture.axg or 0) > 0), refresh=True)
                return True
            except AppError as exc:
                self.last_error = f"match {fixture.id} ({fixture.home} v {fixture.away}): {exc.message}"[:200]
                return False
            except Exception as exc:  # pragma: no cover - defensive: one bad page must not stop the rest
                self.last_error = f"match {fixture.id}: {type(exc).__name__}"
                return False

    async def run(self, ls: LeagueSeason, *, limit: int | None = None, stop: Callable[[], bool] | None = None,
                  progress: Callable[[int, int], None] | None = None) -> dict:
        """Fetch the pending pages of one league season. Returns ``{"fetched", "failed", "remaining"}``."""
        if self.repo.settings.offline:
            return {"fetched": 0, "failed": 0, "remaining": len(self.pending(ls))}
        todo = self.pending(ls)
        batch = todo[:limit] if limit is not None else todo
        fetched = failed = 0
        for start in range(0, len(batch), 16):
            if stop is not None and stop():
                break
            chunk = batch[start:start + 16]
            results = await asyncio.gather(*(self._one(f) for f in chunk))
            fetched += sum(results)
            failed += len(results) - sum(results)
            if progress is not None:
                progress(start + len(chunk), len(batch))
        return {"fetched": fetched, "failed": failed, "remaining": len(todo) - fetched}
