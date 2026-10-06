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
import shutil
import sys
import time
from pathlib import Path
from collections.abc import Callable

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


def _finished(rows: list[dict]) -> list[dict]:
    def scored(v):
        return v is not None and not (isinstance(v, float) and math.isnan(v))

    return [r for r in rows if scored(r.get("home_score")) and scored(r.get("away_score"))]


def _page_path(reader, row: dict) -> Path:
    """Where soccerdata keeps the page it just read for a match."""
    return Path(reader.data_dir) / "events" / f"{row['league']}_{row['season']}" / f"{int(row['game_id'])}.json"


def sync_season(
    events: EventStore, league: str, season: int, *, data_dir: Path, browser: str | None = None, headless: bool = True,
    limit: int | None = None, pause: float = 3.0, max_failures: int = 5, reader=None, log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Fetch every finished match of a league-season that is not stored yet. Returns the final status.

    Each match is read once through the browser, stored raw in the app's own store (see :mod:`app.events.raw`) and derived from there, so
    a stopped run loses nothing and a later run only fetches what is still missing.
    """
    previous = events.status(league, season) or {}
    events.set_status(league, season, running=True, started=time.time(), done=0, failed=0, last_error=None, stalled=False)
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
        todo = [r for r in schedule if not events.has_match(league, season, int(r["game_id"]))]
        stored = len(schedule) - len(todo)
        if limit is not None:
            todo = todo[:limit]
        events.set_status(league, season, total=len(todo), finished_matches=len(schedule))
        log(f"{len(schedule)} finished matches, {stored} already stored, {len(todo)} to fetch.")
        for i, match in enumerate(todo, start=1):
            gid = int(match["game_id"])
            label = f"{match.get('home_team', '?')} v {match.get('away_team', '?')}"
            started = time.monotonic()
            try:
                # force_cache: for the current season soccerdata otherwise re-downloads the whole match list on every call (minutes each time);
                # a finished match never changes, and we only ask for finished ones
                reader.read_events(match_id=gid, output_fmt=None, force_cache=True)
                doc = R.read_match_file(_page_path(reader, match))
                if doc is None or not events.ingest(league, season, gid, doc, fetched_at=time.time()):
                    raise ValueError("no events returned")
                done, consecutive = done + 1, 0
                log(f"  [{i}/{len(todo)}] {label}: stored")
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 - one bad match must not stop the run (it is counted and logged below); a wall of them means we are blocked
                failed, consecutive = failed + 1, consecutive + 1
                events.set_status(league, season, last_error=f"{label}: {str(exc)[:160]}")
                log(f"  [{i}/{len(todo)}] {label}: FAILED ({str(exc)[:100]})")
                if consecutive >= max_failures:
                    log(f"Stopping: {max_failures} matches in a row failed. WhoScored may be blocking requests; try again later, or add --visible.")
                    break
            events.set_status(league, season, done=done, failed=failed)
            if time.monotonic() - started > 2.0:  # the pause is for the website's sake: a match read back from the local cache needs none
                sleep(pause)
    except KeyboardInterrupt:
        log("Stopped. Everything fetched so far is saved; run the same command again to carry on.")
    finally:
        status = events.set_status(league, season, running=False, done=done, failed=failed, finished=time.time())
    return status
