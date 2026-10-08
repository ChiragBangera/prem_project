"""How much the background updater may fetch from each source in a day, and how much it has used.

The sources are public websites read without an agreement, so the updater behaves like a patient reader, not a crawler: a new install
with five leagues and two seasons to fill gets there over days, a little at a time, instead of in one long burst. Pages a person opens
are fetched at once and are not held back by this; they are counted all the same, so the Data page tells the whole story.

Counts are kept per local calendar day in the store (shared with the separate event-fetcher process), and days older than a week are
dropped as new ones are written.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from collections.abc import Callable
from typing import Any

PREFIX = "budget:"
DEFAULT_LIMITS = {"understat": 300, "whoscored": 40}   # Understat match pages, WhoScored matches (about 15 s of browsing each)
CEILINGS = {"understat": 5000, "whoscored": 400}
KEEP_DAYS = 7


class Budget:
    def __init__(self, store: Any, limits: Callable[[], dict] | None = None, *, clock: Callable[[], float] = time.time):
        self.store = store
        self._limits = limits or (lambda: {})
        self._clock = clock

    def day(self) -> str:
        return date.fromtimestamp(self._clock()).isoformat()

    def _key(self, source: str, day: str | None = None) -> str:
        return f"{PREFIX}{source}:{day or self.day()}"

    def limit(self, source: str) -> int:
        value = (self._limits() or {}).get(source, DEFAULT_LIMITS[source])
        return max(0, min(int(value), CEILINGS[source]))

    def used(self, source: str) -> int:
        return int((self.store.kv_get(self._key(source)) or {}).get("n", 0))

    def left(self, source: str) -> int:
        return max(0, self.limit(source) - self.used(source))

    def spend(self, source: str, n: int = 1) -> int:
        if n <= 0:
            return self.used(source)
        total = self.used(source) + n
        self.store.kv_set(self._key(source), {"n": total, "at": self._clock()})
        self._forget_old(source)
        return total

    def _forget_old(self, source: str) -> None:
        oldest = (date.fromtimestamp(self._clock()) - timedelta(days=KEEP_DAYS)).isoformat()
        for key in self.store.kv_prefix(f"{PREFIX}{source}:"):
            if key.rsplit(":", 1)[-1] < oldest:
                self.store.kv_delete(key)

    def summary(self) -> dict:
        return {source: {"used": self.used(source), "limit": self.limit(source), "left": self.left(source)} for source in DEFAULT_LIMITS} | {"day": self.day()}
