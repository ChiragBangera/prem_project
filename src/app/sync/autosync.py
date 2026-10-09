"""The background updater: while the app runs, keep the local data current without anyone pressing a button.

It does not look every few minutes. After each *cycle* it works out, from the fixture list (every kickoff is known, in UTC), the next
moment something can have changed: a match's full time, a result Understat has not listed yet, a match page that has settled, the end of
the event fetcher's rest. It sleeps until the earliest of them (see :mod:`app.data.matchclock`), and never longer than
``auto_longest_sleep``. What it is waiting for is shown on the Data page. A cycle:

1. **League seasons.** For every league and every tracked season (this one, and as many previous ones as the preferences say), ask the
   repository for the season. It decides, by its freshness policy, whether to touch the network: a finished season never is, a live one
   refreshes around matchdays. A failure keeps what is stored and is retried later with a growing delay.
2. **Match pages.** Fetch only the finished matches whose page is missing or not final yet, politely and within a time budget so a big
   backlog is worked off over several cycles instead of in one long burst.
3. **Squad lists** (exact birthdates), through the existing background enrichment.
4. **Event data.** The slow one. If enabled (and the optional dependencies and a browser exist), start the event fetcher as a separate
   process for the first league season with finished matches still missing, bounded to a few dozen matches per run. A separate process keeps
   a browser crash or a blocked page away from the app, and the store is the only thing the two share.
5. **Housekeeping.** Adopt match pages the download cache holds but the store lacks, and rebuild derived layers made by older code.

Everything is idempotent and resumable: stopping the app at any point loses nothing, and the next cycle carries on from what the store holds.
What it did, what failed and when it will look again is kept in the store and shown on the Data page.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import logging
import os
import sys
import time
from collections import deque
from datetime import date, datetime, time as dtime, timedelta
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from app.data import matchclock
from app.errors import AppError
from app.events import ledger
from app.events import raw as R
from app.events.fetch import find_browser
from app.sync.budget import CEILINGS, DEFAULT_LIMITS, SETTABLE, Budget
from app.leagues import LEAGUES, current_season, season_label

if TYPE_CHECKING:  # pragma: no cover
    from app.workbench import Workbench

log = logging.getLogger("prem.autosync")

STATE_KEY = "autosync:state"
PREFS_KEY = "autosync:prefs"
FAIL_PREFIX = "autosync:fail:"
EVENT_RUN_PREFIX = "autosync:events:"
CYCLE_BUDGET = 300.0           # seconds of fetching per cycle before it yields
BACKLOG_INTERVAL = 90.0        # look again this soon while there is still a backlog
RETRY_AFTER = 15 * 60.0        # a cycle with problems is tried again after this (doubling, up to two hours)
MIN_SLEEP = 60.0               # never wake up sooner than this after a cycle (a due moment already past is handled by the cycle just run)
BACKOFF_BASE, BACKOFF_MAX = 300.0, 6 * 3600.0
EVENT_BATCH = 20               # matches per event-fetcher run (about ten minutes of reading at the polite pace)
EVENT_REST = 20 * 60.0         # seconds the event fetcher rests between two runs
EVENT_LAST_END = "autosync:events:last_end"
EVENT_RETRY_KEY = "autosync:events:retry"   # matches a person asked to have read again, oldest first
STOP_GRACE = 60.0              # seconds a run that was asked to stop gets to reach the end of its match, before it is ended
EVENT_RECHECK = 3 * 3600.0     # a season the fetcher found nothing more to do for is not run again sooner than this
STOP_WAIT = 5.0                # seconds the event fetcher gets to stop cleanly when the app stops, before it is killed
FT_RETRY = 10 * 60.0           # a match WhoScored does not call finished yet at its full time is read again this much later ...
FT_GIVE_UP = 4 * 3600.0        # ... until this long after kickoff; after that catching up takes care of it
NOT_FOUND_TRIES = 3            # a fixture WhoScored's match list does not have is looked for this many times
CLEARANCE = 15 * 60.0          # catching up does not start a run when a matchday read is due within this (a run takes about ten minutes)
FOLLOWED_KEY = "autosync:followed"   # live matches someone opened: {"LEAGUE:SEASON:FIXTURE": followed until}

def _days(left: int, per_day: int) -> int | None:
    """About how many days ``left`` takes at ``per_day`` (None when nothing is left or nothing is allowed)."""
    if left <= 0 or per_day <= 0:
        return None
    return -(-left // per_day)


def next_midnight(now: float) -> float:
    """The start of the next local calendar day (when the daily limits start again)."""
    return datetime.combine(date.fromtimestamp(now) + timedelta(days=1), dtime()).timestamp()


def pretty(code: str, season: int) -> str:
    """"La Liga 2026/27": how a league season is named in anything a person reads (keys in the store stay ``La_liga:2026``)."""
    league = LEAGUES.get(code)
    return f"{league.name if league else code} {season_label(season)}"


DEFAULT_PREFS: dict[str, Any] = {
    "enabled": True,
    "seasons_back": 1,                         # previous seasons whose league data and match pages are kept complete
    "events": {"enabled": None, "leagues": list(LEAGUES), "seasons_back": 0},   # enabled None: on once event data has been used before
    "limits": {s: DEFAULT_LIMITS[s] for s in SETTABLE},   # most pages or matches fetched in the background per day, per source
}


class AutoSync:
    def __init__(self, wb: Workbench, *, clock: Callable[[], float] = time.time, spawn: Callable[..., Any] | None = None):
        self.wb = wb
        self.settings = wb.settings
        self._clock = clock
        self._spawn = spawn or asyncio.create_subprocess_exec
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._stop = False
        self._proc: Any = None
        self._proc_label: str | None = None
        self._proc_kind: str | None = None
        self._reapers: set[asyncio.Task] = set()      # tasks that wait for the fetcher to end; kept so they are not collected mid-wait
        self._log: deque[dict] = deque(maxlen=40)
        self.running = False
        self.next_at: float | None = None
        self.next_reason: str | None = None
        self.budget = Budget(wb.store, lambda: {**self.prefs()["limits"], "matchday": self.matchday_allowance()}, clock=clock)

    # ------------------------------------------------------------------ preferences

    @property
    def store(self):
        return self.wb.store

    def prefs(self) -> dict:
        saved = self.store.kv_get(PREFS_KEY) or {}
        events = {**DEFAULT_PREFS["events"], **(saved.get("events") or {})}
        limits = {**DEFAULT_PREFS["limits"], **(saved.get("limits") or {})}
        return {**DEFAULT_PREFS, **{k: v for k, v in saved.items() if k not in ("events", "limits")}, "events": events, "limits": limits}

    def set_prefs(self, patch: dict) -> dict:
        current = self.prefs()
        merged = {**current, **{k: v for k, v in patch.items() if k in ("enabled", "seasons_back") and v is not None}}
        if isinstance(patch.get("events"), dict):
            events = {**current["events"], **{k: v for k, v in patch["events"].items() if k in ("enabled", "leagues", "seasons_back")}}
            events["leagues"] = [lg for lg in events["leagues"] if lg in LEAGUES] or list(LEAGUES)
            events["seasons_back"] = max(0, min(int(events.get("seasons_back") or 0), 3))
            merged["events"] = events
        if isinstance(patch.get("limits"), dict):
            limits = dict(current["limits"])
            for source, value in patch["limits"].items():
                if source in SETTABLE and value is not None:
                    limits[source] = max(0, min(int(value), CEILINGS[source]))
            merged["limits"] = limits
        merged["seasons_back"] = max(0, min(int(merged["seasons_back"]), 4))
        self.store.kv_set(PREFS_KEY, merged)
        self.wake()
        return merged

    # ------------------------------------------------------------------ what the event fetcher needs

    @staticmethod
    def events_capability() -> dict:
        """Whether the optional event-data dependencies and a browser are present, and if not, what to do."""
        if importlib.util.find_spec("soccerdata") is None:
            return {"available": False, "reason": "The optional event-data package is not installed.", "hint": "Install it with `uv sync --extra events` in the Prem Lab folder, then start Prem Lab again."}
        browser = find_browser()
        if browser is None:
            return {"available": False, "reason": "No Chrome, Chromium or Brave was found.", "hint": "Install Google Chrome or Brave and it is found automatically (Microsoft Edge does not work for this), or set PREM_BROWSER to the path of one that is installed somewhere unusual."}
        return {"available": True, "reason": None, "browser": browser}

    def events_enabled(self) -> bool:
        pref = self.prefs()["events"]["enabled"]
        if pref is not None:
            return bool(pref)
        if self.settings.auto_events is not None:
            return self.settings.auto_events
        return bool(self.wb.events.seasons())  # on by default only once event data has been used here before

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        if self._task is None and self.settings.auto:
            self._task = asyncio.create_task(self._loop())

    async def close(self) -> None:
        self._stop = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), STOP_WAIT)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()          # it ignored the request: a stopped app must not leave a browser fetching in the background
            except ProcessLookupError:
                pass

    def wake(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        await asyncio.sleep(self.settings.auto_first_delay)
        failures = 0
        while not self._stop:
            now = self._clock()
            at, reason = now + self.settings.auto_longest_sleep, "switched off"
            try:
                if self.prefs()["enabled"]:
                    result = await self.run_once()
                    failures = 0 if not result["errors"] else min(failures + 1, 5)
                    at, reason = self.next_wake()
                    now = self._clock()
                    if result["backlog"] and not result["errors"]:
                        at, reason = min((at, reason), (now + BACKLOG_INTERVAL, "carrying on with what is still to fetch"))
                    elif failures:
                        at, reason = max((at, reason), (now + min(RETRY_AFTER * 2 ** (failures - 1), 2 * 3600), "trying again after a problem"))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - the updater must never take the app down
                log.exception("auto-update cycle failed")
                self._note("error", f"cycle failed: {type(exc).__name__}: {str(exc)[:120]}")
                failures = min(failures + 1, 5)
                at, reason = self._clock() + min(RETRY_AFTER * 2 ** failures, 2 * 3600), "trying again after a problem"
            delay = max(MIN_SLEEP, at - self._clock())
            self.next_at, self.next_reason = self._clock() + delay, reason
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=delay)

    # ------------------------------------------------------------------ when to look again

    def next_wake(self) -> tuple[float, str]:
        """The next moment worth a cycle, and why: the earliest of every league table's due moment (a match's full time, a result still
        to come, xG settling, the twice-daily check), a match page that has settled, a league in its back-off window, and the event
        fetcher's next run. Read from the store only."""
        now = self._clock()
        found: list[tuple[float, str]] = [(now + self.settings.auto_longest_sleep, "routine check")]
        pages_held = self.budget.left("understat") <= 0
        for code, season in self.tracked():
            label = pretty(code, season)
            fail = self.store.kv_get(FAIL_PREFIX + f"{code}:{season}")
            if fail and fail.get("next_try", 0) > now:
                found.append((fail["next_try"], f"{label}: trying again after a problem"))
                continue
            due = self.wb.repo.league_due(code, season)
            if due is not None:
                found.append((due.at, self._why(due, code)))
            ls = self.wb.repo.cached_league(code, season)
            page_due = self.wb.matchsync.next_due(ls) if ls is not None else None
            if page_due is not None:
                found.append((next_midnight(now), "today's match-page limit is used up") if pages_held and page_due <= now
                             else (page_due, f"{label}: a match page has settled"))
        found.extend(self._events_wake(now))
        return min(found, key=lambda t: t[0])

    @staticmethod
    def _why(due: matchclock.Due, code: str) -> str:
        league = LEAGUES[code].name if code in LEAGUES else code
        f = due.fixture
        if due.why == "full_time" and f is not None:
            return f"full time of {f.home} v {f.away} ({league})"
        if due.why == "result" and f is not None:
            return f"the result of {f.home} v {f.away} ({league})"
        return f"{league}: {matchclock.WHY[due.why]}"

    # ------------------------------------------------------------------ one cycle

    def _note(self, level: str, message: str) -> None:
        self._log.append({"t": self._clock(), "level": level, "msg": message})

    def _in_backoff(self, key: str) -> bool:
        fail = self.store.kv_get(FAIL_PREFIX + key)
        return bool(fail) and fail.get("next_try", 0) > self._clock()

    def _fail(self, key: str, error: str) -> None:
        previous = self.store.kv_get(FAIL_PREFIX + key) or {"n": 0}
        n = previous["n"] + 1
        self.store.kv_set(FAIL_PREFIX + key, {"n": n, "error": error[:200], "at": self._clock(), "next_try": self._clock() + min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (n - 1))})

    def _ok(self, key: str) -> None:
        if self.store.kv_get(FAIL_PREFIX + key) is not None:
            self.store.kv_delete(FAIL_PREFIX + key)

    def tracked(self) -> list[tuple[str, int]]:
        """League seasons kept current, newest first: every league's current season, then the earlier ones the preferences ask for."""
        now = current_season(self.wb.today)
        back = self.prefs()["seasons_back"]
        return [(code, now - k) for k in range(back + 1) for code in LEAGUES]

    async def run_once(self) -> dict:
        """One cycle. Returns what was done, what failed and whether a backlog remains."""
        async with self._lock:
            self.running = True
            started = self._clock()
            deadline = time.monotonic() + CYCLE_BUDGET
            result: dict[str, Any] = {"started": started, "leagues": {}, "events": {}, "errors": [], "backlog": 0, "rebuilt": 0, "adopted": 0}
            try:
                if self.settings.offline or self.settings.demo:
                    return {**result, "finished": self._clock(), "skipped": "offline or demo mode"}
                await self._housekeeping(result)
                for code, season in self.tracked():
                    if self._stop or time.monotonic() > deadline:
                        result["backlog"] += 1
                        continue
                    await self._league_season(code, season, result, deadline)
                await self._events(result)
                result["finished"] = self._clock()
                self._note("info", f"cycle done: {sum(v.get('fetched', 0) for v in result['leagues'].values())} match pages fetched, {len(result['errors'])} problems")
                return result
            finally:
                self.running = False
                self.store.kv_set(STATE_KEY, {"last": {**result, "finished": result.get("finished", self._clock())}, "log": list(self._log)})

    async def _housekeeping(self, result: dict) -> None:
        """Adopt match pages the download cache holds but the store lacks, and rebuild derived layers made by older code."""
        try:
            adopted = await asyncio.to_thread(R.import_soccerdata_cache, self.store, self.settings.data_dir)
            result["adopted"] = adopted["imported"]
            if adopted["imported"]:
                self._note("info", f"adopted {adopted['imported']} event pages from the download cache")
            if await asyncio.to_thread(self.wb.events.pending_rebuild):
                rebuilt = await asyncio.to_thread(self.wb.events.ensure_current)
                result["rebuilt"] = rebuilt["rebuilt"]
                self._note("info", f"rebuilt derived event data for {rebuilt['rebuilt']} matches")
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("housekeeping failed")
            result["errors"].append(f"housekeeping: {type(exc).__name__}")

    async def _league_season(self, code: str, season: int, result: dict, deadline: float) -> None:
        key = f"{code}:{season}"
        entry = result["leagues"].setdefault(key, {})
        if self._in_backoff(key):
            entry["state"] = "waiting"
            return
        try:
            fetched = await self.wb.repo.league(code, season)
        except AppError as exc:
            if exc.status == 404:
                entry["state"] = "not available"  # the season does not exist yet (or never did): nothing to retry
                return
            self._fail(key, exc.message)
            entry["state"] = "failed"
            result["errors"].append(f"{pretty(code, season)}: {exc.message[:100]}")
            self._note("warn", f"{pretty(code, season)}: {exc.message[:100]}")
            return
        entry["state"] = "stale" if fetched.meta.stale else "ok"
        self._ok(key)
        ls = fetched.data
        try:
            allowed = self.budget.left("understat")
            if allowed <= 0 and self.wb.matchsync.pending(ls):
                entry.update({"fetched": 0, "failed": 0, "remaining": len(self.wb.matchsync.pending(ls)), "held": "today's limit reached"})
                return
            run = await self.wb.matchsync.run(ls, limit=allowed, stop=lambda: self._stop or time.monotonic() > deadline, pace=self.settings.page_pace)
            self.budget.spend("understat", run["fetched"] + run["failed"])
            entry.update({"fetched": run["fetched"], "failed": run["failed"], "remaining": run["remaining"]})
            if run["remaining"]:
                result["backlog"] += run["remaining"]
            if run["failed"]:
                result["errors"].append(f"{pretty(code, season)}: {run['failed']} match pages failed ({self.wb.matchsync.last_error or 'unknown'})")
            if run["fetched"]:
                self._note("info", f"{pretty(code, season)}: fetched {run['fetched']} match pages")
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("match pages for %s failed unexpectedly", pretty(code, season))
            result["errors"].append(f"{pretty(code, season)}: {type(exc).__name__}")
        if not self.settings.demo:
            self.wb.enricher.schedule_rosters([(code, season)])

    # ------------------------------------------------------------------ the event fetcher (a separate process)

    def _proc_alive(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _events(self, result: dict) -> None:
        cap = self.events_capability()
        enabled = self.events_enabled()
        result["events"] = {"enabled": enabled, "available": cap["available"], "reason": cap.get("reason"), "running": self._proc_label if self._proc_alive() else None, "started": None}
        if not enabled or not cap["available"]:
            return
        if ledger.control(self.store).get("paused"):
            result["events"]["held"] = "paused"
            return
        now = self._clock()
        due, later = self.matchday(now)
        if self._proc_alive():
            if due and self._proc_kind == "backfill":   # a match has finished: the catching-up run ends at its next match, then it is read
                ledger.set_control(self.store, stop_at=now)
                self._end_run_soon()
                result["events"]["held"] = "making way for a match that has finished"
            return
        if due:
            left = self.budget.left("matchday")
            if left <= 0:
                result["events"]["matchday_held"] = "today's matchday reads are used up"
            else:
                (code, season), targets = next(iter(due.items()))
                await self._start_events(code, season, None, result, targets=targets[:left])
                return
        retry = self.store.kv_get(EVENT_RETRY_KEY) or []
        if retry:                                    # a person asked for these: no rest, no limit
            first = retry[0]
            self.store.kv_set(EVENT_RETRY_KEY, retry[1:])
            await self._start_events(first["league"], first["season"], None, result, games=[first["game"]])
            return
        if due or any(at - now < CLEARANCE for at, _why in later):
            result["events"]["held"] = "matches are being played: catching up waits"
            return
        if self._clock() - float(self.store.kv_get(EVENT_LAST_END) or 0) < EVENT_REST:
            result["events"]["held"] = "resting between runs"
            return
        allowed = self.budget.left("whoscored")
        if allowed <= 0:
            result["events"]["held"] = "today's limit reached"
            return
        for code, season, played, not_before in self._backfill():
            if not_before <= self._clock():
                await self._start_events(code, season, played, result, limit=min(EVENT_BATCH, allowed))
                return

    # ------------------------------------------------------------------ matchday reads

    def _event_fixtures(self):
        """``(league, season, fixtures)`` for this season of every event league whose fixture list is stored."""
        season = current_season(self.wb.today)
        for code in self.prefs()["events"]["leagues"]:
            ls = self.wb.repo.cached_league(code, season)
            if ls is not None:
                yield code, season, ls.fixtures

    def matchday_allowance(self) -> int:
        """How many matchday reads today allows: two for every match of the event leagues played today (half time and full time), and a
        few to spare for a match read again. Worked out from the fixture list, so a busy Saturday gets more than a quiet Tuesday."""
        today = date.fromtimestamp(self._clock())
        n = sum(1 for _code, _season, fixtures in self._event_fixtures() for f in fixtures
                if (k := matchclock.kickoff(f)) is not None and date.fromtimestamp(k) == today)
        return 2 * n + 10

    def follow(self, league: str, season: int, fixture: int, until: float) -> bool:
        """Someone opened this match while it is being played: read it at half time too, until ``until`` (the end of its matchday window).
        Kept in the store, so a restart in the middle of the match keeps following it. True when it was not followed before."""
        now = self._clock()
        followed = {k: v for k, v in (self.store.kv_get(FOLLOWED_KEY) or {}).items() if v > now}
        key = f"{league}:{season}:{int(fixture)}"
        new = key not in followed
        followed[key] = max(until, followed.get(key, 0.0))
        self.store.kv_set(FOLLOWED_KEY, followed)
        if new:
            self.wake()
        return new

    def followed(self, league: str, season: int, fixture) -> str | None:
        """Why this fixture is followed (``favourite`` or ``opened``), or None."""
        if self.wb.favourites.follows(league, fixture.home) or self.wb.favourites.follows(league, fixture.away):
            return "favourite"
        until = (self.store.kv_get(FOLLOWED_KEY) or {}).get(f"{league}:{season}:{fixture.id}", 0.0)
        return "opened" if until > self._clock() else None

    def matchday(self, now: float) -> tuple[dict[tuple[str, int], list[dict]], list[tuple[float, str]]]:
        """The matchday reads due now, by league season (half-time reads first), and when the next ones fall due (with why).

        Every match of the event leagues is read once WhoScored can call it finished: at its full time (kickoff + 112 minutes), and again
        every ten minutes while its page still says it is in play, for up to four hours after kickoff. A followed match (a favourite team's,
        or one someone opened while it is being played) is also read during the half-time break."""
        due: dict[tuple[str, int], list[dict]] = {}
        later: list[tuple[float, str]] = []
        for code, season, fixtures in self._event_fixtures():
            for f in fixtures:
                k = matchclock.kickoff(f)
                if k is None or now >= k + FT_GIVE_UP or k > now + 2 * 86400:
                    continue
                note = ledger.matchday(self.store, code, season, f.id) or {}
                if note.get("state") == "final" or int(note.get("not_found", 0)) >= NOT_FOUND_TRIES:
                    continue
                target = {"fixture": f.id, "kickoff": f.dt, "home": f.home, "away": f.away}
                if note.get("moment") not in ("ht", "ft") and now < k + matchclock.HALF_TIME_END and self.followed(code, season, f):
                    if now < k + matchclock.HALF_TIME:
                        later.append((k + matchclock.HALF_TIME, f"half-time event data of {f.home} v {f.away}"))
                    else:
                        due.setdefault((code, season), []).insert(0, {**target, "moment": "ht"})
                    continue
                full_time = k + matchclock.FULL_TIME
                if now < full_time:
                    later.append((full_time, f"full-time event data of {f.home} v {f.away}"))
                    continue
                if note.get("moment") == "ft" and now - float(note.get("at", 0)) < FT_RETRY:
                    later.append((float(note["at"]) + FT_RETRY, f"full-time event data of {f.home} v {f.away}, again"))
                    continue
                due.setdefault((code, season), []).append({**target, "moment": "ft"})
        first = sorted(due.items(), key=lambda item: not any(t["moment"] == "ht" for t in item[1]))   # the break is short: half time goes first
        return dict(first), later

    def _backfill(self) -> list[tuple[str, int, int, float]]:
        """League seasons with finished matches whose event data is still missing, in the order they are fetched:
        ``(league, season, finished matches, not before)``. ``not before`` is in the future for a season the fetcher looked at a moment ago
        and found nothing more it could read (it waits for another match to finish, or ``EVENT_RECHECK``)."""
        prefs = self.prefs()["events"]
        now = current_season(self.wb.today)
        out = []
        for back in range(prefs["seasons_back"] + 1):
            for code in prefs["leagues"]:
                season = now - back
                key = f"events:{code}:{season}"
                if self._in_backoff(key):
                    continue
                if self.store.meta("league", f"{code}:{season}") is None:
                    continue
                played = self.wb.repo.cached_league(code, season)
                if played is None:
                    continue
                stored = len(self.wb.events.match_ids(code, season))
                parked = sum(1 for e in ledger.failures(self.store, code, season).values() if ledger.waiting_for_person(e))
                if stored + parked >= played.n_played:
                    continue
                last = self.store.kv_get(EVENT_RUN_PREFIX + f"{code}:{season}") or {}
                same = bool(last) and last.get("played") == played.n_played
                out.append((code, season, played.n_played, last.get("at", 0) + EVENT_RECHECK if same else 0.0))
        return out

    def _events_wake(self, now: float) -> list[tuple[float, str]]:
        """When the event fetcher next has something to do (nothing when it is off, unavailable, paused or already running: its end wakes
        the updater by itself)."""
        if not self.events_enabled() or ledger.control(self.store).get("paused"):
            return []
        due, later = self.matchday(now)
        if self._proc_alive():   # its end wakes the updater by itself; a match finishing meanwhile still does
            return later if self._proc_kind == "backfill" else []
        if due:
            return [(now, "reading matches that have finished") if self.budget.left("matchday") > 0 else (next_midnight(now), "today's matchday reads are used up")]
        if later and not self.events_capability()["available"]:
            later = []
        if self.store.kv_get(EVENT_RETRY_KEY):
            return [(now, "reading again the matches you asked for")]
        waiting = [not_before for *_rest, not_before in self._backfill()]
        if not waiting or not self.events_capability()["available"]:
            return later
        at = max(now, min(waiting), float(self.store.kv_get(EVENT_LAST_END) or 0) + EVENT_REST)
        if self.budget.left("whoscored") <= 0:
            return [*later, (next_midnight(now), "today's event-data limit is used up")]
        if any(t - at < CLEARANCE for t, _why in later):
            return later   # held for a matchday read: that read wakes the updater, and its end wakes it again
        return [*later, (at, "catching up on event data")]

    async def _start_events(self, code: str, season: int, played: int | None, result: dict, *, limit: int = EVENT_BATCH, games: list[int] | None = None,
                            targets: list[dict] | None = None) -> None:
        label = pretty(code, season)
        cmd = [sys.executable, "-m", "app.cli", "events", "sync", "--league", code, "--seasons", str(season), "--data-dir", str(self.settings.data_dir)]
        if targets:
            cmd += ["--targets", json.dumps(targets)]
        else:
            cmd += ["--game", ",".join(str(g) for g in games)] if games else ["--limit", str(limit), "--budget"]
        logs = self.settings.data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        handle = None
        try:
            handle = await asyncio.to_thread(open, logs / f"events-{code}-{season}.log", "ab")  # the fetcher writes to it until it ends; _reap closes it
            self._proc = await self._spawn(*cmd, stdout=handle, stderr=handle, env={**os.environ, "PREM_DATA_DIR": str(self.settings.data_dir)})
        except Exception as exc:
            log.exception("could not start the event fetcher for %s", label)
            if handle is not None:
                handle.close()
            self._fail(f"events:{code}:{season}", f"{type(exc).__name__}: {exc}")
            result["errors"].append(f"could not start the event fetcher: {type(exc).__name__}")
            return
        self._proc_label = label
        self._proc_kind = "matchday" if targets else "retry" if games else "backfill"
        result["events"]["started"] = label
        if targets:
            names = ", ".join(f"{t['home']} v {t['away']}" for t in targets[:3]) + (f" and {len(targets) - 3} more" if len(targets) > 3 else "")
            moments = {t["moment"] for t in targets}
            self._note("info", f"reading {names} ({label}) at {'half time and full time' if len(moments) > 1 else 'half time' if 'ht' in moments else 'full time'}")
        elif games:
            self._note("info", f"reading {len(games)} match{'es' if len(games) > 1 else ''} of {label} again, as asked")
        else:
            self.store.kv_set(EVENT_RUN_PREFIX + f"{code}:{season}", {"played": played, "at": self._clock()})
            self._note("info", f"started the event fetcher for {label} ({(played or 0) - len(self.wb.events.match_ids(code, season))} matches missing, at most {limit} this run)")
        reaper = asyncio.create_task(self._reap(self._proc, handle, f"{code}:{season}"))
        self._reapers.add(reaper)
        reaper.add_done_callback(self._reapers.discard)

    @staticmethod
    def _named(key: str) -> str:
        """``La_liga:2026`` -> "La Liga 2026/27" (anything else is left as it is)."""
        code, _, season = key.partition(":")
        return pretty(code, int(season)) if season.isdigit() else key

    async def _reap(self, proc, handle, key: str) -> None:
        try:
            code = await proc.wait()
        finally:
            handle.close()
            self.store.kv_set(EVENT_LAST_END, self._clock())
        if code != 0:
            self._fail(f"events:{key}", f"the fetcher exited with status {code}")
            self._note("warn", f"event fetcher for {self._named(key)} exited with status {code}")
        else:
            self._ok(f"events:{key}")
            self._note("info", f"event fetcher for {self._named(key)} finished")
        self.wake()  # look again at once: there may be more to fetch

    # ------------------------------------------------------------------ what a person can tell the event fetcher

    def pause_events(self, paused: bool) -> dict:
        """Pause (the run in progress ends at its next match, no new one starts until resumed) or resume."""
        control = ledger.set_control(self.store, paused=bool(paused))
        if paused:
            self._end_run_soon()
        self.wake()
        return control

    def stop_events(self) -> dict:
        """End the run in progress at its next match; the next one starts as usual (after the rest)."""
        control = ledger.set_control(self.store, stop_at=self._clock())
        self._end_run_soon()
        return control

    def _end_run_soon(self) -> None:
        """The fetcher stops by itself at its next match; if it has not after a minute (a page that hangs), end it."""
        proc = self._proc if self._proc_alive() else None
        if proc is None:
            return

        async def insist() -> None:
            try:
                await asyncio.wait_for(proc.wait(), STOP_GRACE)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.terminate()

        task = asyncio.create_task(insist())
        self._reapers.add(task)
        task.add_done_callback(self._reapers.discard)

    def retry_event_match(self, league: str, season: int, game: int) -> list[dict]:
        """Read this match again as soon as the fetcher is free, whatever its record says."""
        ledger.set_skip(self.store, league, season, game, False)
        queue = [q for q in (self.store.kv_get(EVENT_RETRY_KEY) or []) if not (q["league"] == league and q["season"] == season and q["game"] == game)]
        queue.append({"league": league, "season": season, "game": int(game)})
        self.store.kv_set(EVENT_RETRY_KEY, queue)
        self.wake()
        return queue

    def skip_event_match(self, league: str, season: int, game: int, skip: bool) -> dict | None:
        return ledger.set_skip(self.store, league, season, game, skip)

    def plan(self) -> list[dict]:
        """For every league season the updater keeps: what is still to fetch from each source, and about how many days that takes at today's limits.
        Read from the store only (never the network)."""
        prefs = self.prefs()
        events_on = self.events_enabled()
        now = current_season(self.wb.today)
        limits = {s: self.budget.limit(s) for s in DEFAULT_LIMITS}
        out = []
        for code, season in self.tracked():
            ls = self.wb.repo.cached_league(code, season)
            if ls is None:
                continue
            pages = len(self.wb.matchsync.pending(ls))
            row = {"league": code, "season": season, "label": pretty(code, season), "pages_left": pages, "pages_days": _days(pages, limits["understat"])}
            if events_on and code in prefs["events"]["leagues"] and season >= now - prefs["events"]["seasons_back"]:
                book = ledger.failures(self.store, code, season)
                stored = len(self.wb.events.match_ids(code, season))
                parked = sum(1 for e in book.values() if ledger.waiting_for_person(e))
                left = max(0, ls.n_played - stored - parked)
                row.update({"events_stored": stored, "events_played": ls.n_played, "events_left": left, "events_parked": parked, "events_days": _days(left, limits["whoscored"])})
            out.append(row)
        return out

    # ------------------------------------------------------------------ for the Data page

    def brief(self) -> dict:
        """A few fields for the top bar's status pill (cheap: no capability probing)."""
        last = (self.store.kv_get(STATE_KEY) or {}).get("last") or {}
        return {
            "enabled": bool(self.settings.auto and self.prefs()["enabled"]), "running": self.running, "next_at": self.next_at, "next_reason": self.next_reason,
            "finished": last.get("finished"), "errors": len(last.get("errors") or []), "backlog": last.get("backlog", 0),
            "events_running": self._proc_label if self._proc_alive() else None,
        }

    def state(self) -> dict:
        saved = self.store.kv_get(STATE_KEY) or {}
        cap = self.events_capability()
        return {
            "auto": self.settings.auto, "prefs": self.prefs(), "running": self.running, "next_at": self.next_at, "next_reason": self.next_reason,
            "last": saved.get("last"), "log": list(self._log) or saved.get("log", []),
            "events": {"capability": cap, "enabled": self.events_enabled(), "process": self._proc_label if self._proc_alive() else None,
                       "process_kind": self._proc_kind if self._proc_alive() else None,
                       "control": ledger.control(self.store), "retry": self.store.kv_get(EVENT_RETRY_KEY) or [],
                       "rest_until": float(self.store.kv_get(EVENT_LAST_END) or 0) + EVENT_REST},
            "budget": self.budget.summary(), "plan": self.plan(),
            "failures": {k[len(FAIL_PREFIX):]: v for k, v in self.store.kv_prefix(FAIL_PREFIX).items() if v},
            "tracked": [{"league": c, "season": s} for c, s in self.tracked()],
        }
