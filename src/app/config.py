"""Runtime settings, read once from the environment.

    PREM_DATA_DIR     where the local cache lives (default: <repo>/.prem-data)
    PREM_DEMO=1       serve the synthetic demo world instead of Understat
    PREM_OFFLINE=1    never touch the network; serve whatever is cached
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

    @property
    def db_path(self) -> Path:
        return self.data_dir / ("demo.sqlite" if self.demo else "prem.sqlite")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(demo=_flag("PREM_DEMO"), offline=_flag("PREM_OFFLINE"))
