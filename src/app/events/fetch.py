"""Fetching WhoScored event data through ``soccerdata``. The only part of the app that needs a browser.

It is slow on purpose (a match takes ~15 seconds plus a pause), resumable (matches already stored are skipped, so
stopping and starting again just carries on), and stops by itself when the site starts refusing requests. Nothing
here is imported unless you run ``prem events sync``, and the optional dependency is imported only then.

Personal use only: this reads a public website through its pages, which its terms may not allow. It runs only when
you ask, never in the background of the app, and keeps what it reads on your own computer.
"""

from __future__ import annotations

import math
import os
import shutil
import time
from pathlib import Path
from typing import Callable

from .aggregate import aggregate_match
from .store import EventStore

LEAGUE_CODES = {
    "EPL": "ENG-Premier League", "La_liga": "ESP-La Liga", "Bundesliga": "GER-Bundesliga", "Serie_A": "ITA-Serie A", "Ligue_1": "FRA-Ligue 1",
}
BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
BROWSER_COMMANDS = ("google-chrome", "chromium", "chromium-browser", "brave-browser", "microsoft-edge")
SCHEDULE_REFRESH = 6 * 3600.0  # the season's match list is re-read at most this often when resuming


class FetchUnavailable(Exception):
    """The optional dependency or a browser is missing; the message says what to do."""


def find_browser() -> str | None:
    for path in BROWSERS:
        if Path(path).exists():
            return path
    for name in BROWSER_COMMANDS:
        found = shutil.which(name)
        if found:
            return found
    return None


def make_reader(league: str, season: int, *, data_dir: Path, browser: str | None = None, headless: bool = True):
    """A ``soccerdata`` WhoScored reader whose own cache lives inside the app's data folder."""
    if league not in LEAGUE_CODES:
        raise FetchUnavailable(f"WhoScored event data is only set up for {', '.join(LEAGUE_CODES)}.")
    browser = browser or find_browser()
    if not browser:
        raise FetchUnavailable("No Chrome, Chromium, Brave or Edge found. Install one, or pass --browser with its path.")
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


def sync_season(
    events: EventStore, league: str, season: int, *, data_dir: Path, browser: str | None = None, headless: bool = True,
    limit: int | None = None, pause: float = 3.0, max_failures: int = 5, reader=None, log: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Fetch every finished match of a league-season that is not stored yet. Returns the final status."""
    previous = events.status(league, season) or {}
    events.set_status(league, season, running=True, started=time.time(), done=0, failed=0, last_error=None, stalled=False)
    done = failed = consecutive = 0
    try:
        reader = reader or make_reader(league, season, data_dir=data_dir, browser=browser, headless=headless)
        fresh = time.time() - previous.get("schedule_at", 0.0) < SCHEDULE_REFRESH
        log(f"Reading the {league} {season} match list ({'from cache' if fresh else 'this takes a few minutes'})...")
        schedule = _finished(_records(reader.read_schedule(force_cache=True) if fresh else reader.read_schedule()))
        events.set_status(league, season, schedule_at=time.time())
        todo = [r for r in schedule if not events.has_current_match(league, season, int(r["game_id"]))]  # also re-reads rows stored in an older format
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
                rows = aggregate_match(_records(reader.read_events(match_id=gid, output_fmt="events", force_cache=True)))
                if not rows:
                    raise ValueError("no events returned")
                events.put_match(league, season, gid, rows, home=str(match.get("home_team", "")), away=str(match.get("away_team", "")), date=str(match.get("date", ""))[:10])
                done, consecutive = done + 1, 0
                log(f"  [{i}/{len(todo)}] {label}: {len(rows)} players")
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # one bad match must not stop the run; a wall of them means we are blocked
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
