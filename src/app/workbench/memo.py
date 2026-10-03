"""Results worth remembering: built once, kept until what they were built from changes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Any

MAX_ENTRIES = 96       # when the memo grows past this, the oldest third is dropped
DROP_ENTRIES = 32


class Memo:
    """A versioned, lock-per-key memo for the expensive views.

    ``await memo(key, version, compute)`` returns the value stored under ``key`` if it was built for this exact ``version`` (a token that changes
    whenever any input does); otherwise it builds it once, even when several requests ask at the same moment, and remembers it.
    """

    def __init__(self, today: Callable[[], date]) -> None:
        self._today = today
        self._day: date | None = None
        self._values: dict[tuple, tuple[Any, Any]] = {}
        self._locks: dict[tuple, asyncio.Lock] = {}

    async def __call__(self, key: tuple, version: Any, compute: Callable[[], Any], *, threaded: bool = True):
        day = self._today()
        if day != self._day:      # views that read the date (next fixtures, ages, the current season) are rebuilt once a day
            self._values.clear()
            self._day = day
        hit = self._values.get(key)
        if hit is not None and hit[0] == version:
            return hit[1]
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            hit = self._values.get(key)
            if hit is not None and hit[0] == version:
                return hit[1]
            value = await asyncio.to_thread(compute) if threaded else compute()
            self._values[key] = (version, value)
            if len(self._values) > MAX_ENTRIES:
                for stale in list(self._values)[:DROP_ENTRIES]:
                    self._values.pop(stale, None)
            return value
