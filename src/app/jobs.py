"""Sync jobs: fetch a chosen set of league-seasons into the local cache, with progress."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from app.data.repository import Repository
from app.data.rosters import RosterClient
from app.errors import AppError
from app.leagues import LEAGUES


@dataclass
class Job:
    id: str
    label: str
    total: int
    done: int = 0
    failed: int = 0
    state: str = "running"  # running | finished | failed | cancelled
    started: float = field(default_factory=time.time)
    finished: float | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "total": self.total, "done": self.done, "failed": self.failed,
            "state": self.state, "started": self.started, "finished": self.finished, "log": self.log[-12:],
            "elapsed": round((self.finished or time.time()) - self.started, 1),
        }


class JobManager:
    def __init__(self, repo: Repository, on_change=None, rosters: RosterClient | None = None):
        self.repo = repo
        self.rosters = rosters
        self.jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._on_change = on_change

    def start_sync(self, leagues: list[str], seasons: list[int], *, force: bool = False) -> Job:
        unknown = [l for l in leagues if l not in LEAGUES]
        if unknown:
            raise ValueError(f"Unknown league(s): {', '.join(unknown)}.")
        targets = [(l, s) for l in leagues for s in sorted(seasons, reverse=True)]
        job = Job(uuid.uuid4().hex[:8], f"Sync {len(leagues)} league(s) × {len(seasons)} season(s)", len(targets))
        self.jobs[job.id] = job
        self._tasks[job.id] = asyncio.create_task(self._run(job, targets, force))
        return job

    async def _run(self, job: Job, targets: list[tuple[str, int]], force: bool) -> None:
        for league, season in targets:
            try:
                fetched = await self.repo.league(league, season, refresh=True, force=force)
                job.done += 1
                verb = "cached" if fetched.meta.complete and not force else "fetched"
                job.log.append(f"{league} {season}: {verb} ({fetched.data.n_played} matches played)")
                await self._squads(job, league, season)
            except AppError as exc:
                job.failed += 1
                job.log.append(f"{league} {season}: {exc.message}")
            except Exception as exc:  # pragma: no cover - defensive
                job.failed += 1
                job.log.append(f"{league} {season}: unexpected error {type(exc).__name__}")
            if self._on_change:
                self._on_change()
        job.state = "finished" if job.failed < job.total else "failed"
        job.finished = time.time()

    async def _squads(self, job: Job, league: str, season: int) -> None:
        """Squad lists (exact birthdates) for the same league season. Best effort: ages fall back to Wikidata, so a failure is only logged."""
        if self.rosters is None or not self.rosters.needs_fetch(league, season):
            return
        try:
            body = await self.rosters.ensure(league, season)
        except Exception as exc:  # pragma: no cover - defensive
            job.log.append(f"{league} {season}: squad lists failed ({type(exc).__name__})")
            return
        if body is None:
            job.log.append(f"{league} {season}: squad lists unavailable, ages will come from Wikidata")
            return
        players = sum(len(t["players"]) for t in body["teams"])
        note = ", sparse: the feed has little for this season" if body.get("sparse") else f", {len(body['pending'])} clubs to retry" if body.get("pending") else ""
        job.log.append(f"{league} {season}: squad lists for {len(body['teams'])} clubs, {players} players{note}")

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def recent(self, limit: int = 5) -> list[dict]:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: -j.started)[:limit]]

    async def close(self) -> None:
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
