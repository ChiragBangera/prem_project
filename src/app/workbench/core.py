"""The Workbench: the running app's shared state, and the parts that answer for each page.

``Workbench`` owns what everything shares (the store, the repository, the event store, the enrichment and update machinery, the memo of
expensive results) and its life cycle (start, stop). The logic itself lives in small parts, each in its own module:

* shared logic: :class:`~app.workbench.seasons.Seasons` (which league season a request means), :class:`~app.workbench.ages.Ages` (dates of
  birth and how well their sources agree), :class:`~app.workbench.links.EventLinks` (WhoScored's matches, clubs and players lined up with
  Understat's), :class:`~app.workbench.datasets.Datasets` (the scouting datasets), :class:`~app.workbench.shortlist.Shortlist` and
  :class:`~app.workbench.diagnostics.Diagnostics` (the connection check);
* one page each in :mod:`app.workbench.pages`: briefing, league, scout (and teams), player, team, compare, matches, search, dictionary, data.

The API routes are thin wrappers around the pages (``wb.team.page(...)``), which keeps the HTTP layer trivial and the behaviour testable without a server.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date
from typing import Any

from app import __version__
from app.config import Settings
from app.data.demo import WORLD_VERSION, DemoProvider
from app.data.matchbook import MatchBook
from app.data.matchsync import MatchSync
from app.data.repository import Repository
from app.data.rosters import RosterClient
from app.data.store import Store
from app.data.understat import UnderstatClient
from app.data.wikidata import BirthdateResolver
from app.enrich import Enricher, FavoriteIndex
from app.events.store import DERIVED_MARK, STATUS_PREFIX, EventStore
from app.jobs import JobManager
from app.leagues import DEFAULT_LEAGUE, LEAGUES, available_seasons, current_season, season_label
from app.metrics.catalog import build_catalog
from app.sync.autosync import AutoSync
from app.sync.demofeed import DemoEventFeed
from app.workbench.ages import Ages
from app.workbench.datasets import Datasets
from app.workbench.diagnostics import Diagnostics
from app.workbench.links import EventLinks
from app.workbench.memo import Memo
from app.workbench.pages.briefing import BriefingPage
from app.workbench.pages.compare import ComparePage
from app.workbench.pages.data import DataPage
from app.workbench.pages.dictionary import DictionaryPage
from app.workbench.pages.league import LeaguePage
from app.workbench.pages.matches import MatchesPage
from app.workbench.pages.player import PlayerPage
from app.workbench.pages.scout import ScoutPage
from app.workbench.pages.search import SearchPage
from app.workbench.pages.team import TeamPage
from app.workbench.seasons import Seasons
from app.workbench.shortlist import Shortlist

log = logging.getLogger("prem.workbench")


class Workbench:
    def __init__(self, settings: Settings | None = None, *, provider=None, today: date | None = None):
        self.settings = settings or Settings.from_env()
        self.store = Store(self.settings.db_path)
        if self.settings.demo:
            self._refresh_demo_world()
        if provider is None:
            if self.settings.demo:
                override = os.getenv("PREM_TODAY")
                provider = DemoProvider(today=today or (date.fromisoformat(override) if override else None))
            else:
                provider = UnderstatClient(
                    timeout=self.settings.request_timeout,
                    max_concurrency=self.settings.max_concurrency,
                    min_interval=self.settings.min_interval,
                    retries=self.settings.retries,
                )
        self.provider = provider
        override = os.getenv("PREM_TODAY")
        # a date given by the caller, by PREM_TODAY or by the demo world is fixed; a real run follows the calendar, so a server left
        # running for days moves on to the next matchday (and, in August, the next season) without being restarted
        self._fixed_today: date | None = today or (date.fromisoformat(override) if override else None) or getattr(provider, "today", None)
        self.memo = Memo(lambda: self.today)
        self.repo = Repository(self.store, provider, self.settings)
        self.resolver = BirthdateResolver(self.store, self.settings)
        self.favorites = FavoriteIndex(self.store)
        self.events = EventStore(self.store)
        self.matchbook = MatchBook(self.repo)
        self.matchsync = MatchSync(self.repo)
        self._catalog = build_catalog()
        self.auto = AutoSync(self)
        self.demo_feed: DemoEventFeed | None = None
        self._boot_task: asyncio.Task | None = None
        self.rosters = RosterClient(self.store, self.settings, today=lambda: self.today)
        self.enricher = Enricher(self.repo, self.store, self.resolver, self.favorites, roster_client=self.rosters)
        self.jobs = JobManager(self.repo, on_change=self.repo.invalidate, rosters=self.rosters)

        # shared logic
        self.seasons = Seasons(self)
        self.ages = Ages(self)
        self.links = EventLinks(self)
        self.datasets = Datasets(self)
        self.shortlist = Shortlist(self)
        self.diagnostics = Diagnostics(self)
        # one part per page
        self.briefing = BriefingPage(self)
        self.league = LeaguePage(self)
        self.scout = ScoutPage(self)
        self.player = PlayerPage(self)
        self.team = TeamPage(self)
        self.compare = ComparePage(self)
        self.matches = MatchesPage(self)
        self.search = SearchPage(self)
        self.dictionary = DictionaryPage(self)
        self.data = DataPage(self)

    def _refresh_demo_world(self) -> None:
        """The demo world is made from code, so a copy stored by an older version of it would disagree with this one: start it afresh. Your shortlist stays."""
        if self.store.kv_get("demo:world") == WORLD_VERSION:
            return
        self.store.clear()
        for key in self.store.kv_prefix(STATUS_PREFIX):
            self.store.kv_delete(key)
        self.store.kv_delete(DERIVED_MARK)
        self.store.kv_set("demo:world", WORLD_VERSION)

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        """Begin the work that happens while the app runs: adopt stored event pages, bring derived layers up to date, start the updater."""
        self._boot_task = asyncio.create_task(self._boot())
        self.auto.start()
        if self.settings.demo and self.settings.demo_events:
            self.demo_feed = DemoEventFeed(self)
            self.demo_feed.start()

    async def _boot(self) -> None:
        """First thing after start: put every stored event page into the store and rebuild what older code made. Quick when nothing changed."""
        from app.events import raw as R

        try:
            self.store.kv_set("boot:state", {"stage": "importing", "at": time.time()})
            adopted = await asyncio.to_thread(R.import_soccerdata_cache, self.store, self.settings.data_dir)
            pending = await asyncio.to_thread(self.events.pending_rebuild)
            if pending:
                self.store.kv_set("boot:state", {"stage": "rebuilding", "total": pending, "at": time.time()})
                await asyncio.to_thread(self.events.ensure_current)
            self.store.kv_set("boot:state", {"stage": "done", "adopted": adopted["imported"], "rebuilt": pending, "at": time.time()})
        except Exception as exc:  # a failure here must not stop the app: it is logged and shown on the Data page
            log.exception("start-up work failed")
            self.store.kv_set("boot:state", {"stage": "failed", "error": f"{type(exc).__name__}: {str(exc)[:160]}", "at": time.time()})

    async def close(self) -> None:
        if self.demo_feed is not None:
            await self.demo_feed.close()
        await self.auto.close()
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()
            await asyncio.gather(self._boot_task, return_exceptions=True)
        await self.jobs.close()
        await self.enricher.close()
        await self.rosters.close()
        await self.repo.close()
        self.store.close()

    # ------------------------------------------------------------------ what the app knows about itself

    @property
    def today(self) -> date:
        return self._fixed_today or date.today()

    @today.setter
    def today(self, value: date) -> None:
        self._fixed_today = value

    async def meta(self) -> dict[str, Any]:
        seasons = self.provider.seasons() if hasattr(self.provider, "seasons") else available_seasons(self.today)
        stats = self.store.stats()
        return {
            "app": {"name": "Prem Lab", "version": __version__},
            "mode": {"demo": self.settings.demo, "offline": self.settings.offline, "source": "demo" if self.settings.demo else "understat"},
            "today": self.today.isoformat(),
            "leagues": [{"code": lg.code, "name": lg.name, "short": lg.short, "country": lg.country} for lg in LEAGUES.values()],
            "seasons": [{"season": s, "label": season_label(s)} for s in seasons],
            "current_season": current_season(self.today),
            "defaults": {"league": DEFAULT_LEAGUE, "season": "auto"},
            "cache": {"leagues": self.repo.cached_leagues(), "items": stats["total_items"], "bytes": stats["total_bytes"]},
            "enrichment": self.enricher.status(),
            "jobs": self.jobs.recent(3),
            "auto": self.auto.brief(),
        }

    def catalog(self) -> dict:
        """The metric registry for the browser: every metric, group, column preset and lens."""
        return self._catalog
