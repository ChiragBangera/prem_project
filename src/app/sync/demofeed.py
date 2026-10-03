"""In demo mode there is no Understat or WhoScored to fetch from, and the background updater is off. This does the two jobs the updater would,
a few matches at a time, so every feature can be seen with ``prem serve --demo``:

* the match pages (scorers, set-piece and shot-location metrics): the demo world's own, stored the way a fetched page is;
* the event data (maps, passing and defending metrics, possession, the style profile): synthetic WhoScored-shaped matches.

While it runs the Data page shows the progress and the pages show partial coverage honestly, current seasons first. It resumes where it
stopped: a match already stored is never generated again.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from app.data.demo.events import game_id, synthesize_match
from app.leagues import LEAGUES, current_season

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench import Workbench

log = logging.getLogger("prem.demofeed")


class DemoEventFeed:
    BATCH = 20

    def __init__(self, wb: "Workbench", *, limit: int | None = None, seasons_back: int = 1):
        self.wb = wb
        self.limit = limit              # at most this many matches per league season (tests use a few)
        self.seasons_back = seasons_back
        self._task: asyncio.Task | None = None
        self._stop = False

    def targets(self) -> list[tuple[str, int]]:
        """Every league's current season first (the pages people open first, and the short ones), then the seasons before it."""
        now = current_season(self.wb.today)
        return [(code, now - back) for back in range(self.seasons_back + 1) for code in LEAGUES]

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        self._stop = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def wait(self) -> None:
        """Until every target has been filled (for tests)."""
        if self._task is not None:
            await asyncio.shield(self._task)

    async def _run(self) -> None:
        try:
            for code, season in self.targets():
                if self._stop:
                    return
                await self._season(code, season)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - the demo feed must never take the app down
            log.exception("demo event feed failed")

    async def _season(self, code: str, season: int) -> None:
        events = self.wb.events
        fetched = await self.wb.seasons.load(code, season)
        await self.wb.matchsync.run(fetched.data, limit=self.limit, stop=lambda: self._stop)
        data = await asyncio.to_thread(self.wb.provider.season_data, code, season)
        played = sorted(data.matches.values(), key=lambda m: (m.dt, m.id))
        if self.limit is not None:
            played = played[: self.limit]
        todo = [m for m in played if not events.has_match(code, season, game_id(m))]
        if not todo:
            return
        events.set_status(code, season, running=True, started=time.time(), done=0, failed=0, last_error=None, stalled=False, total=len(todo), finished_matches=len(played))
        done = 0
        for i in range(0, len(todo), self.BATCH):
            if self._stop:
                break
            chunk = todo[i: i + self.BATCH]

            def work() -> None:
                for match in chunk:
                    events.ingest(code, season, game_id(match), synthesize_match(data, match))

            await asyncio.to_thread(work)
            done += len(chunk)
            events.set_status(code, season, done=done)
            await asyncio.sleep(0.02)  # let requests through between batches
        events.set_status(code, season, running=False, done=done, finished=time.time())
