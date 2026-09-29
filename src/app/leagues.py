"""League metadata and season arithmetic.

Understat identifies a season by its start year (``2025`` is 2025/26) and a
league by a slug (``EPL``, ``La_liga`` ...). Everything user-facing goes through
this module so labels, table zones and "current season" logic live in one place.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class League:
    code: str  # Understat slug
    name: str
    short: str
    country: str
    ucl_places: int
    relegation_places: int


LEAGUES: dict[str, League] = {
    "EPL": League("EPL", "Premier League", "EPL", "England", 4, 3),
    "La_liga": League("La_liga", "La Liga", "LaLiga", "Spain", 4, 3),
    "Bundesliga": League("Bundesliga", "Bundesliga", "BuLi", "Germany", 4, 3),
    "Serie_A": League("Serie_A", "Serie A", "Serie A", "Italy", 4, 3),
    "Ligue_1": League("Ligue_1", "Ligue 1", "Ligue 1", "France", 3, 3),
}

DEFAULT_LEAGUE = "EPL"
FIRST_SEASON = 2014  # earliest season Understat publishes

_ALIASES = {
    "epl": "EPL",
    "prem": "EPL",
    "premierleague": "EPL",
    "laliga": "La_liga",
    "bundesliga": "Bundesliga",
    "seriea": "Serie_A",
    "ligue1": "Ligue_1",
}


def normalize_league(value: str | None) -> str:
    """Map user input ("epl", "La Liga", "serie_a") onto an Understat slug."""
    if not value:
        return DEFAULT_LEAGUE
    if value in LEAGUES:
        return value
    key = re.sub(r"[^a-z0-9]", "", value.lower())
    if key in _ALIASES:
        return _ALIASES[key]
    for code in LEAGUES:
        if re.sub(r"[^a-z0-9]", "", code.lower()) == key:
            return code
    raise ValueError(f"Unknown league '{value}'. Choose one of: {', '.join(LEAGUES)}.")


def current_season(today: date | None = None) -> int:
    """Start year of the season in progress (seasons roll over on 1 July)."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def season_label(season: int) -> str:
    return f"{season}/{str(season + 1)[-2:]}"


def season_of_date(day: str) -> int:
    """Season a YYYY-MM-DD date belongs to."""
    year, month = int(day[:4]), int(day[5:7])
    return year if month >= 7 else year - 1


def available_seasons(today: date | None = None) -> list[int]:
    """Seasons Understat can serve, newest first."""
    return list(range(current_season(today), FIRST_SEASON - 1, -1))


def fold(text: str | None) -> str:
    """Lower-case, accent-free, punctuation-free key for name matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text.replace("ø", "o").replace("Ø", "O").replace("ß", "ss"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
