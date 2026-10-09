"""Fetching WhoScored event data through ``soccerdata``. The only part of the app that needs a browser.

It is slow on purpose (a match takes ~15 seconds plus a pause), resumable (matches already stored are skipped, so
stopping and starting again just carries on), and stops by itself when the site starts refusing requests. Nothing
here is imported unless you run ``prem events sync``, and the optional dependency is imported only then.

Personal use only: this reads a public website through its pages, which its terms may not allow. It runs when you ask
(``prem events sync``) or, if you switch event data on in the Data page, as a separate process started by the background updater
(:mod:`app.sync.autosync`); either way what it reads stays on your own computer.
"""

from __future__ import annotations

import math
import os
import random
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable

from app.data.people import plays_for

from . import ledger as L
from . import raw as R
from .store import EventStore

LEAGUE_CODES = R.LEAGUE_TO_SOCCERDATA
# Chrome, Chromium and Brave only. Microsoft Edge is left out on purpose: the tool that reads WhoScored (soccerdata, through SeleniumBase's
# undetected mode) only drives these three, and ignores an Edge it is handed (it then looks for a Chrome of its own).
BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
BROWSER_COMMANDS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave-browser", "brave")
# Windows keeps none of these on the PATH. Each installer puts its browser under Program Files, Program Files (x86) or the user's own
# AppData\Local, and registers the program's name (the "App Paths" key) wherever it went.
WINDOWS_BROWSERS = (
    ("chrome.exe", "Google/Chrome/Application/chrome.exe"),
    ("brave.exe", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    (None, "Chromium/Application/chrome.exe"),
)
WINDOWS_ROOTS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
WINDOWS_COMMANDS = ("chrome", "brave", "chromium")
SCHEDULE_REFRESH = 6 * 3600.0  # the season's match list is re-read at most this often when resuming


class FetchUnavailable(Exception):
    """The optional dependency or a browser is missing; the message says what to do."""


def _app_path(exe: str) -> str | None:
    """Where Windows says a program is installed (its "App Paths" registry entry), or None."""
    if sys.platform != "win32":
        return None
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as key:
                return str(winreg.QueryValueEx(key, "")[0]).strip('"')
        except OSError:
            continue
    return None


def _windows_candidates() -> list[str]:
    roots = [Path(os.environ[name]) for name in WINDOWS_ROOTS if os.environ.get(name)]
    found: list[str] = []
    for exe, relative in WINDOWS_BROWSERS:
        found.extend(str(root / relative) for root in roots)
        registered = _app_path(exe) if exe else None
        if registered:
            found.append(registered)
    return found


def _is_edge(path: str) -> bool:
    return "edge" in Path(path).name.lower()                         # msedge.exe, microsoft-edge, Microsoft Edge


def find_browser(platform: str | None = None) -> str | None:
    """The browser the event fetcher drives: the one PREM_BROWSER names, else Chrome, Brave or Chromium, wherever the system keeps it."""
    windows = (platform or sys.platform) == "win32"
    override = os.environ.get("PREM_BROWSER")
    if override and not _is_edge(override):
        if Path(override).is_file():
            return override
        found = shutil.which(override)
        if found:
            return found
    for path in _windows_candidates() if windows else BROWSERS:
        if Path(path).is_file():
            return path
    for name in WINDOWS_COMMANDS if windows else BROWSER_COMMANDS:
        found = shutil.which(name)
        if found:
            return found
    return None


def make_reader(league: str, season: int, *, data_dir: Path, browser: str | None = None, headless: bool = True):
    """A ``soccerdata`` WhoScored reader whose own cache lives inside the app's data folder."""
    if league not in LEAGUE_CODES:
        raise FetchUnavailable(f"WhoScored event data is only set up for {', '.join(LEAGUE_CODES)}.")
    browser = browser or find_browser()
    if browser and _is_edge(browser):
        raise FetchUnavailable("Microsoft Edge cannot be used for event data: the tool that reads WhoScored only drives Chrome, Chromium and Brave. Install one of them, or pass --browser with its path.")
    if not browser:
        raise FetchUnavailable("No Chrome, Chromium or Brave found. Install one, or pass --browser (or set PREM_BROWSER) with its path. Microsoft Edge does not work for this.")
    os.environ.setdefault("SOCCERDATA_DIR", str(data_dir / "soccerdata"))  # must be set before soccerdata is imported
    try:
        import logging

        import soccerdata

        logging.getLogger("root").setLevel(logging.WARNING)  # soccerdata logs a line per request at INFO level
    except ImportError as exc:
        raise FetchUnavailable('The optional "soccerdata" package is not installed. Run: uv run --extra events prem events sync ...') from exc
    return soccerdata.WhoScored(leagues=LEAGUE_CODES[league], seasons=str(season), headless=headless, path_to_browser=browser)


def _records(frame) -> list[dict]:
    return frame.reset_index().to_dict("records")


def _known(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _finished(rows: list[dict]) -> list[dict]:
    """The matches WhoScored's match list calls finished. A score alone is not enough: the list shows the score while a match is in play,
    so where it says the match's status (6 is full time), that decides."""
    def done(r: dict) -> bool:
        if _known(r.get("status")):
            return int(r["status"]) == R.FINAL_STATUS
        return _known(r.get("home_score")) and _known(r.get("away_score"))

    return [r for r in rows if done(r)]


def _read_page(reader, row: dict, *, live: bool = False) -> dict | None:
    """Read one match through the browser and return its page.

    soccerdata keeps every page it reads and, by default, hands back that copy next time. A copy read before the final whistle would then
    come back forever, so when the copy on disk is not a finished match (or ``live`` says the match is being followed right now) the page
    is read from the site again."""
    path = _page_path(reader, row)
    cached = R.read_match_file(path) if path.is_file() else None
    stale = path.is_file() and (cached is None or R.match_state(cached) != "final")
    # force_cache: for the current season soccerdata otherwise re-downloads the whole match list on every call (minutes each time)
    reader.read_events(match_id=int(row["game_id"]), output_fmt=None, force_cache=True, live=live or stale)
    return R.read_match_file(path)


def _when(value) -> float | None:
    """A kickoff as WhoScored's match list or Understat's fixture gives it ("2026-10-10 14:00:00", a pandas Timestamp; both UTC)."""
    try:
        return datetime.fromisoformat(str(value)[:19].replace("T", " ")).replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


KICKOFF_SLACK = 3 * 3600.0   # the two sources may disagree on a kickoff by this much (a late change one of them has not picked up)


def _find(rows: list[dict], target: dict) -> dict | None:
    """The WhoScored match that is this Understat fixture: kicked off at about the same time, with the same clubs (by name, or the only match
    at that time). None when it cannot be told for sure."""
    kickoff = _when(target["kickoff"])
    if kickoff is None:
        return None
    near = [r for r in rows if (k := _when(r.get("date"))) is not None and abs(k - kickoff) <= KICKOFF_SLACK]
    named = [r for r in near if plays_for([str(r.get("home_team"))], [target["home"]]) and plays_for([str(r.get("away_team"))], [target["away"]])]
    if len(named) == 1:
        return named[0]
    return near[0] if not named and len(near) == 1 else None


def read_targets(
    events: EventStore, league: str, season: int, targets: list[dict], *, data_dir: Path, browser: str | None = None, headless: bool = True,
    pause: float = 10.0, reader=None, log: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep,
    stop: Callable[[], str | None] | None = None, on_fetched: Callable[[], None] | None = None, clock: Callable[[], float] = time.time,
) -> dict:
    """Read a few matches of a league season *now*, at half time or full time, whatever state they are in.

    ``targets`` are Understat fixtures (``{"fixture", "kickoff", "home", "away", "moment"}``, moment ``ht`` or ``ft``). Each is found in
    WhoScored's match list by kickoff and clubs, read from the site (never from the download cache: it may hold an earlier read) and stored:
    as finished when the page says full time, as provisional otherwise. What each read found is noted under the fixture (see
    :func:`app.events.ledger.note_matchday`). Returns ``{"read", "final", "live", "not_found", "failed"}``."""
    out = {"read": 0, "final": 0, "live": 0, "not_found": 0, "failed": 0}
    reader = reader or make_reader(league, season, data_dir=data_dir, browser=browser, headless=headless)
    rows = _records(reader.read_schedule(force_cache=True))
    found = {t["fixture"]: _find(rows, t) for t in targets}
    if any(row is None for row in found.values()):   # a fixture moved since the match list was read: read the list again, once
        log("A match is not in the stored match list; reading the list again (this takes a few minutes)...")
        rows = _records(reader.read_schedule())
        events.set_status(league, season, schedule_at=time.time())
        found = {t["fixture"]: _find(rows, t) for t in targets}
    for i, target in enumerate(targets, start=1):
        label = f"{target['home']} v {target['away']}"
        reason = stop() if stop is not None else None
        if reason is not None:
            log(f"Stopping before {label}: {reason}.")
            break
        row = found[target["fixture"]]
        if row is None:
            out["not_found"] += 1
            tries = int((L.matchday(events.store, league, season, target["fixture"]) or {}).get("not_found", 0)) + 1
            L.note_matchday(events.store, league, season, target["fixture"], state="not found", not_found=tries, at=clock(), moment=target["moment"])
            log(f"  {label}: not found in WhoScored's match list")
            continue
        gid = int(row["game_id"])
        try:
            doc = _read_page(reader, row, live=True)
            state = events.ingest(league, season, gid, doc, fetched_at=clock()) if doc is not None else None
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad page must not stop the others; the updater tries again in a few minutes
            doc, state = None, None
            log(f"  {label}: FAILED ({str(exc)[:100]})")
        if on_fetched is not None:
            on_fetched()
        out["read"] += 1
        if doc is None or state is None:
            out["failed"] += 1
            L.note_matchday(events.store, league, season, target["fixture"], game=gid, state="failed", at=clock(), moment=target["moment"])
        else:
            out[state] += 1
            L.note_matchday(events.store, league, season, target["fixture"], game=gid, state=state, at=clock(), moment=target["moment"],
                            elapsed=str(doc.get("elapsed") or ""), score=str(doc.get("score") or ""))
            if state == "final":
                L.forget(events.store, league, season, gid)
            minute = doc.get("elapsed") or "in play"
            log(f"  {label}: full time, stored" if state == "final" else f"  {label}: read at {minute}, kept as provisional")
        if i < len(targets):
            sleep(pause * (1.0 + random.random()))
    return out


def _page_path(reader, row: dict) -> Path:
    """Where soccerdata keeps the page it just read for a match."""
    return Path(reader.data_dir) / "events" / f"{row['league']}_{row['season']}" / f"{int(row['game_id'])}.json"


def sync_season(
    events: EventStore, league: str, season: int, *, data_dir: Path, browser: str | None = None, headless: bool = True,
    limit: int | None = None, pause: float = 10.0, max_failures: int = 5, reader=None, log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep, only: set[int] | None = None, stop: Callable[[], str | None] | None = None,
    allowance: Callable[[], int] | None = None, on_fetched: Callable[[], None] | None = None, clock: Callable[[], float] = time.time,
    cached_under: float = 2.0,
) -> dict:
    """Fetch every finished match of a league-season that is not stored yet. Returns the final status.

    Each match is read once through the browser, stored raw in the app's own store (see :mod:`app.events.raw`) and derived from there, so
    a stopped run loses nothing and a later run only fetches what is still missing.

    Politeness: between two matches it waits ``pause`` to twice ``pause`` seconds (at random, so the visits do not tick like a machine).
    A match that failed before is skipped until it is due again (see :mod:`app.events.ledger`), unless it is in ``only``, which also limits
    the run to those matches (a person asked for them). ``stop`` is asked before every match and ends the run when it gives a reason
    (paused, stopped); ``allowance`` says how many more matches today's budget allows, and ``on_fetched`` is told of each one read from the site.
    """
    previous = events.status(league, season) or {}
    events.set_status(league, season, running=True, started=time.time(), done=0, failed=0, last_error=None, stalled=False, stopped=None)
    done = failed = consecutive = 0
    try:
        adopted = R.import_soccerdata_cache(events.store, data_dir, only=[(league, season)])  # pages a stopped run downloaded but never stored
        if adopted["imported"]:
            log(f"Adopted {adopted['imported']} match pages left in the download cache.")
            for gid in events.match_ids(league, season):
                events.derive(league, season, gid)
        reader = reader or make_reader(league, season, data_dir=data_dir, browser=browser, headless=headless)
        fresh = time.time() - previous.get("schedule_at", 0.0) < SCHEDULE_REFRESH
        log(f"Reading the {league} {season} match list ({'from cache' if fresh else 'this takes a few minutes'})...")
        schedule = _finished(_records(reader.read_schedule(force_cache=True) if fresh else reader.read_schedule()))
        events.set_status(league, season, schedule_at=time.time())
        missing = [r for r in schedule if not events.has_match(league, season, int(r["game_id"]))]
        stored = len(schedule) - len(missing)
        book = L.failures(events.store, league, season)
        now = clock()
        if only is not None:
            todo = [r for r in missing if int(r["game_id"]) in only]
            waiting = 0
        else:
            todo = [r for r in missing if L.due(book.get(int(r["game_id"])), now)]
            waiting = len(missing) - len(todo)
        if limit is not None:
            todo = todo[:limit]
        events.set_status(league, season, total=len(todo), finished_matches=len(schedule))
        log(f"{len(schedule)} finished matches, {stored} already stored, {len(todo)} to fetch"
            + (f", {waiting} failed before and waiting to be tried again." if waiting else "."))
        for i, match in enumerate(todo, start=1):
            reason = stop() if stop is not None else None
            if reason is None and allowance is not None and allowance() <= 0:
                reason = "today's limit reached"
            if reason is not None:
                log(f"Stopping before match {i} of {len(todo)}: {reason}. Everything fetched so far is saved.")
                events.set_status(league, season, stopped=reason)
                break
            gid = int(match["game_id"])
            label = f"{match.get('home_team', '?')} v {match.get('away_team', '?')}"
            started = time.monotonic()
            try:
                doc = _read_page(reader, match)
                state = events.ingest(league, season, gid, doc, fetched_at=time.time()) if doc is not None else None
                if doc is None or state is None:
                    raise ValueError("no events returned")
                consecutive = 0
                if state == "final":
                    done += 1
                    L.forget(events.store, league, season, gid)
                    log(f"  [{i}/{len(todo)}] {label}: stored")
                else:   # WhoScored's list called it finished but its page does not yet: kept as provisional, read again later
                    log(f"  [{i}/{len(todo)}] {label}: not finished yet ({doc.get('elapsed') or 'in play'}), kept as provisional")
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad match must not stop the run (it is counted and logged below); a wall of them means we are blocked
                failed, consecutive = failed + 1, consecutive + 1
                events.set_status(league, season, last_error=f"{label}: {str(exc)[:160]}")
                L.note_failure(events.store, league, season, gid, label=label, date=str(match.get("date") or "")[:10] or None, error=str(exc), now=clock())
                log(f"  [{i}/{len(todo)}] {label}: FAILED ({str(exc)[:100]})")
                if consecutive >= max_failures:
                    log(f"Stopping: {max_failures} matches in a row failed. WhoScored may be blocking requests; try again later, or add --visible.")
                    break
            events.set_status(league, season, done=done, failed=failed)
            if time.monotonic() - started > cached_under:  # the pause is for the website's sake: a match read back from the local cache needs none
                if on_fetched is not None:
                    on_fetched()
                if i < len(todo):
                    sleep(pause * (1.0 + random.random()))
    except KeyboardInterrupt:
        log("Stopped. Everything fetched so far is saved; run the same command again to carry on.")
    finally:
        status = events.set_status(league, season, running=False, done=done, failed=failed, finished=time.time())
    return status
