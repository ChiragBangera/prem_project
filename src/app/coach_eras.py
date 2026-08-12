from __future__ import annotations

from dataclasses import dataclass


# Understat does not provide manager metadata. These windows are curated and
# should be re-verified whenever a coaching change occurs.
COACH_ERAS_LAST_VERIFIED = "2026-07-17"


@dataclass(frozen=True)
class CoachEra:
    coach_name: str
    team_name: str
    league_name: str
    start_date: str
    end_date: str | None
    aliases: tuple[str, ...]


COACH_ERAS: tuple[CoachEra, ...] = (
    CoachEra(
        coach_name="Erik ten Hag",
        team_name="Manchester United",
        league_name="EPL",
        start_date="2022-07-01",
        end_date="2024-10-28",
        aliases=("ten hag", "erik ten hag"),
    ),
    CoachEra(
        coach_name="Ruud van Nistelrooy",
        team_name="Manchester United",
        league_name="EPL",
        start_date="2024-10-28",
        end_date="2024-11-10",
        aliases=("ruud", "van nistelrooy", "ruud van nistelrooy"),
    ),
    CoachEra(
        coach_name="Ruben Amorim",
        team_name="Manchester United",
        league_name="EPL",
        start_date="2024-11-11",
        end_date="2026-01-05",
        aliases=("amorim", "ruben amorim"),
    ),
    CoachEra(
        coach_name="Darren Fletcher",
        team_name="Manchester United",
        league_name="EPL",
        start_date="2026-01-05",
        end_date="2026-01-13",
        aliases=("darren fletcher", "fletcher"),
    ),
    CoachEra(
        coach_name="Michael Carrick",
        team_name="Manchester United",
        league_name="EPL",
        start_date="2026-01-13",
        end_date=None,
        aliases=("michael carrick", "carrick"),
    ),
    CoachEra(
        coach_name="Mikel Arteta",
        team_name="Arsenal",
        league_name="EPL",
        start_date="2019-12-22",
        end_date=None,
        aliases=("arteta", "mikel arteta"),
    ),
    CoachEra(
        coach_name="Arne Slot",
        team_name="Liverpool",
        league_name="EPL",
        start_date="2024-06-01",
        end_date="2026-05-30",
        aliases=("slot", "arne slot"),
    ),
    CoachEra(
        coach_name="Enzo Maresca",
        team_name="Chelsea",
        league_name="EPL",
        start_date="2024-07-01",
        end_date="2026-01-01",
        aliases=("maresca", "enzo maresca"),
    ),
)


def find_coach_eras(question_lower: str):
    matches: list[CoachEra] = []
    seen: set[str] = set()

    for era in COACH_ERAS:
        for alias in sorted(era.aliases, key=len, reverse=True):
            if alias in question_lower and era.coach_name not in seen:
                matches.append(era)
                seen.add(era.coach_name)
                break

    return matches


def find_coach_era_by_name(coach_name: str | None, team_name: str | None = None):
    if coach_name is None:
        return None
    for era in find_coach_eras(coach_name.lower()):
        if era.coach_name == coach_name and (team_name is None or era.team_name == team_name):
            return era
    return None


def season_from_date(date_string: str) -> int:
    year, month, _ = (int(part) for part in date_string.split("-"))
    return year if month >= 7 else year - 1


def coach_covered_seasons(era: CoachEra, today) -> list[int]:
    end_date = era.end_date or today
    start_season = season_from_date(era.start_date)
    end_season = season_from_date(end_date)
    return list(range(start_season, end_season + 1))


def default_coach_season(eras, today) -> int | None:
    if not eras:
        return None
    shared = None
    for era in eras:
        seasons = set(coach_covered_seasons(era, today))
        shared = seasons if shared is None else shared & seasons
    if shared:
        return max(shared)
    return max(coach_covered_seasons(eras[0], today))


def coach_window_for_season(era: CoachEra, season: int, today):
    season_start = f"{season}-07-01"
    season_end = f"{season + 1}-06-30"
    era_end = era.end_date or today
    start_date = max(era.start_date, season_start)
    end_date = min(era_end, season_end)
    if start_date > end_date:
        return None
    return start_date, end_date
