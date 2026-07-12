from __future__ import annotations

from dataclasses import dataclass


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
        end_date=None,
        aliases=("slot", "arne slot"),
    ),
    CoachEra(
        coach_name="Enzo Maresca",
        team_name="Chelsea",
        league_name="EPL",
        start_date="2024-07-01",
        end_date=None,
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
