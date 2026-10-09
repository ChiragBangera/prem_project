"""When things happen around a match, and so when it is worth looking at a source again.

Every fixture carries its kickoff in UTC, so the app knows ahead of time when each match reaches half time and full time. Instead of
looking every few minutes whether something changed, the updater works out the next moment something *can* have changed and sleeps
until then:

* a league table is read again at a match's 90th minute of play (kickoff + 105 minutes), then every three minutes until Understat lists the result (it does
  once it has the shots, a little after the final whistle), more slowly after three hours, and not at all after two days (a postponed
  match). A table is about 40 KB, so this is cheap;
* while a finished match's xG can still move (about a day and a half), the table is read every six hours;
* with no match in sight it is still read twice a day, so a fixture moved to a new date is noticed.

All times are UTC seconds (``time.time()``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple
from collections.abc import Iterable

from .models import Fixture

MIN = 60.0
HOUR = 3600.0

HALF_TIME = 47 * MIN          # kickoff to the half-time whistle: 45 minutes and a little stoppage
HALF_TIME_END = 62 * MIN      # the break lasts fifteen minutes
HT_READ = 45 * MIN            # the first half-time read: at 45 minutes (stoppage time is decided on the pitch, nobody knows it ahead) ...
HT_READ_LAST = 64 * MIN       # ... then again every HT_RETRY while the page still says first half, until it says HT or the second half starts
HT_RETRY = 3 * MIN
HT_READS_MAX = 7              # 45, 48 ... 63 minutes: the most half-time reads one match can take
FULL_TIME = 112 * MIN         # kickoff to the final whistle, usually: two halves, the break and stoppage time (the phase shown by the clock)
FT_READ = 105 * MIN           # the 90th minute of play (45 + the 15-minute break + 45): the first full-time read, of WhoScored and Understat ...
FT_RETRY = 3 * MIN            # ... then every three minutes until WhoScored's page says FT ...
FT_FAST_UNTIL = 150 * MIN     # ... until this long after kickoff (extra time, a long stoppage), then
FT_RETRY_SLOW = 10 * MIN      # every ten minutes
UNDERSTAT_FIRST = FT_READ     # Understat's table is first looked at at the 90th minute of play ...
RESULT_POLL = 3 * MIN         # ... then this often until it lists the result ...
RESULT_FAST_FOR = 3 * HOUR    # ... for this long, then
RESULT_POLL_MID = 20 * MIN    # this often until
RESULT_SLOW_AFTER = 6 * HOUR  # six hours after kickoff, then
RESULT_POLL_SLOW = 2 * HOUR   # this often, until
RESULT_GIVE_UP = 48 * HOUR    # this long after kickoff (it was postponed or abandoned; the quiet check notices a new date)
SETTLE = 36 * HOUR            # Understat revises a match's shots for about this long after kickoff
SETTLE_POLL = 6 * HOUR        # how often the table is read while a recent match settles
QUIET = 12 * HOUR             # with nothing in sight the table is still read this often


def kickoff(fixture: Fixture) -> float | None:
    try:
        return datetime.fromisoformat(fixture.dt).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


class Due(NamedTuple):
    """The moment a source should be read again, and why (``why`` is one of the keys of :data:`WHY`)."""

    at: float
    why: str
    fixture: Fixture | None = None


WHY = {
    "full_time": "the result (90th minute)",
    "result": "waiting for the result",
    "settle": "xG still settling",
    "quiet": "the twice-daily check for moved fixtures",
}


def league_due(fixtures: Iterable[Fixture], fetched_at: float, *, complete: bool = False) -> Due | None:
    """When a league table read at ``fetched_at`` is worth reading again. None for a finished season (it never changes)."""
    if complete:
        return None
    best = Due(fetched_at + QUIET, "quiet")
    for fixture in fixtures:
        k = kickoff(fixture)
        if k is None:
            continue
        if fixture.played:
            candidate = Due(fetched_at + SETTLE_POLL, "settle", fixture) if fetched_at - k < SETTLE else None
        else:
            first = k + UNDERSTAT_FIRST
            if first > fetched_at:
                candidate = Due(first, "full_time", fixture)                    # first look at 90 minutes
            elif fetched_at - first < RESULT_FAST_FOR:
                candidate = Due(fetched_at + RESULT_POLL, "result", fixture)
            elif fetched_at - k < RESULT_SLOW_AFTER:
                candidate = Due(fetched_at + RESULT_POLL_MID, "result", fixture)
            elif fetched_at - k < RESULT_GIVE_UP:
                candidate = Due(fetched_at + RESULT_POLL_SLOW, "result", fixture)
            else:
                candidate = None
        if candidate is not None and candidate.at < best.at:
            best = candidate
    return best


def in_play(fixture: Fixture, now: float, *, before: float = 5 * MIN) -> bool:
    """Kicked off (or about to) and not yet past its full time."""
    k = kickoff(fixture)
    return k is not None and not fixture.played and k - before <= now < k + FULL_TIME


def phase(fixture: Fixture, now: float) -> str:
    """``upcoming``, ``first_half``, ``half_time``, ``second_half``, ``full_time`` (by the clock, waiting for the sources) or ``played``."""
    if fixture.played:
        return "played"
    k = kickoff(fixture)
    if k is None or now < k:
        return "upcoming"
    if now < k + HALF_TIME:
        return "first_half"
    if now < k + HALF_TIME_END:
        return "half_time"
    if now < k + FULL_TIME:
        return "second_half"
    return "full_time"
