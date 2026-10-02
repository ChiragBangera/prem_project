"""Every stored match page of a league season, read from this computer, never from the network.

Understat's league page lists fixtures and per-player *totals*. The match pages hold what the totals hide: each shot with
its position, type and situation, who scored and who assisted, who started, and for how many minutes in which position. A
``MatchBook`` loads the pages that are stored for a season and says how complete that set is, so everything built from it
can be honest about coverage (a statistic built from 60% of the matches is left blank rather than shown as if it were whole).
"""

from __future__ import annotations

import threading

from .models import Fixture, LeagueSeason, MatchPage
from .repository import Repository


class MatchBook:
    def __init__(self, repo: Repository):
        self.repo = repo
        self._lock = threading.Lock()
        self._memo: dict[tuple[str, int], tuple[tuple, dict[int, MatchPage]]] = {}

    def _version(self, ls: LeagueSeason) -> tuple:
        stamps = []
        for f in ls.fixtures:
            if f.played:
                status = self.repo.match_status(f.id)
                if status is not None:
                    stamps.append((f.id, status[0]))
        return (len(stamps), max((t for _i, t in stamps), default=0.0))

    def pages(self, ls: LeagueSeason) -> dict[int, MatchPage]:
        """Fixture id -> the stored match page, for the played fixtures that have one. Blocking: call it from a worker thread."""
        key = (ls.league, ls.season)
        version = self._version(ls)
        with self._lock:
            hit = self._memo.get(key)
            if hit is not None and hit[0] == version:
                return hit[1]
        pages: dict[int, MatchPage] = {}
        for fixture in ls.fixtures:
            if fixture.played:
                page = self.repo.cached_match(fixture.id)
                if page is not None:
                    pages[fixture.id] = page
        with self._lock:
            self._memo[key] = (version, pages)
        return pages

    def coverage(self, ls: LeagueSeason, pages: dict[int, MatchPage] | None = None) -> tuple[int, int]:
        """``(played fixtures with a page, played fixtures)``."""
        pages = self.pages(ls) if pages is None else pages
        return len(pages), sum(1 for f in ls.fixtures if f.played)

    def complete(self, ls: LeagueSeason, pages: dict[int, MatchPage] | None = None, *, threshold: float = 0.98) -> bool:
        """Whether enough of the season's matches are stored for season-long aggregates to be trusted."""
        have, total = self.coverage(ls, pages)
        return total > 0 and have / total >= threshold

    def fixtures_with_pages(self, ls: LeagueSeason) -> list[tuple[Fixture, MatchPage]]:
        pages = self.pages(ls)
        return [(f, pages[f.id]) for f in ls.fixtures if f.id in pages]
