"""Runtime settings, read once from the environment.

    PREM_DATA_DIR     where the local cache lives (default: <repo>/.prem-data)
    PREM_DEMO=1       serve the synthetic demo world instead of Understat
    PREM_OFFLINE=1    never touch the network; serve whatever is cached
    PREM_AUTO=0       do not update data in the background (default: on, except in demo and offline modes)
    PREM_AUTO_EVENTS  1/0: whether the background updater may also run the event-data fetcher (default: on when its dependencies are installed)
    PREM_DEMO_EVENTS  0 to skip the synthetic event data the demo world otherwise generates in the background (default: on)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

HOUR = 3600
DAY = 24 * HOUR


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def default_data_dir() -> Path:
    override = os.getenv("PREM_DATA_DIR")
    if override:
        return Path(override).expanduser()
    repo_root = Path(__file__).resolve().parents[2]
    if (repo_root / "pyproject.toml").exists():
        return repo_root / ".prem-data"
    return Path.home() / ".prem-lab"


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    demo: bool = False
    offline: bool = False
    request_timeout: float = 25.0
    max_concurrency: int = 4
    min_interval: float = 0.25  # seconds between request starts (be polite)
    retries: int = 3

    # Freshness windows for data that can still change.
    ttl_league_live: int = 3 * HOUR
    ttl_player_live: int = 24 * HOUR
    ttl_match_open: int = 6 * HOUR
    ttl_team_live: int = 12 * HOUR
    ttl_dob_hit: int = 365 * DAY
    ttl_dob_miss: int = 14 * DAY
    ttl_roster_live: int = 24 * HOUR  # squads change in transfer windows; finished seasons never refresh

    # Background updates: while the app runs, the updater sleeps until the fixture list says something can have changed (a match's half
    # time or full time, a result still to come), and fetches only that.
    auto: bool = False
    auto_events: bool | None = None  # None: on when the optional event-data dependencies and a browser are available
    auto_longest_sleep: float = 6 * 3600.0   # the updater never sleeps longer than this, whatever the fixture list says
    auto_first_delay: float = 10.0
    page_pace: float = 1.5            # seconds between two Understat match pages fetched in the background (one at a time)
    demo_events: bool = False        # in demo mode, fill the event store with synthetic matches in the background (see sync/demofeed.py)

    @property
    def db_path(self) -> Path:
        return self.data_dir / ("demo.sqlite" if self.demo else "prem.sqlite")

    @classmethod
    def from_env(cls) -> Settings:
        demo, offline = _flag("PREM_DEMO"), _flag("PREM_OFFLINE")
        auto_events = os.getenv("PREM_AUTO_EVENTS")
        return cls(
            demo=demo, offline=offline,
            demo_events=demo and os.getenv("PREM_DEMO_EVENTS", "1").strip().lower() not in {"0", "false", "no", "off"},
            auto=os.getenv("PREM_AUTO", "1").strip().lower() not in {"0", "false", "no", "off"} and not demo and not offline,
            auto_events=None if auto_events is None else auto_events.strip().lower() in {"1", "true", "yes", "on"},
        )
