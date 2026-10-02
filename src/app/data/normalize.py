"""Turn raw Understat payloads into typed models.

Understat serves numbers as strings, uses dicts keyed by id where a list would
do, and occasionally omits fields. This module absorbs all of that in one place:
unparseable rows are skipped (and counted in ``LeagueSeason.warnings``) instead
of crashing a whole page.
"""

from __future__ import annotations

import html as _html
import math
from typing import Any, Iterable

from .models import (
    CareerSeason,
    Fixture,
    LeagueSeason,
    MatchPage,
    PlayerPage,
    PlayerSeason,
    RosterEntry,
    Shot,
    SplitRow,
    Team,
    TeamMatch,
    TeamPage,
)


# ---------------------------------------------------------------------- primitives


def num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(result) or math.isinf(result) else result


def integer(value: Any, default: int = 0) -> int:
    return int(round(num(value, default)))


def maybe_num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) or math.isinf(result) else result


def text(value: Any, default: str = "") -> str:
    """A string field with HTML entities decoded: Understat occasionally sends names like ``N&#039;Golo``."""
    if value is None:
        return default
    out = str(value)
    return (_html.unescape(out) if "&" in out else out).strip()


def rows(value: Any) -> list[dict]:
    """Understat sometimes sends ``{id: row}`` and sometimes ``[row]``."""
    if isinstance(value, dict):
        return [v for v in value.values() if isinstance(v, dict)]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _split_teams(title: Any) -> list[str]:
    parts = [p.strip() for p in text(title).split(",") if p.strip()]
    return parts or ["Unknown"]


# ---------------------------------------------------------------------- league


def normalize_league(raw: dict, league: str, season: int) -> LeagueSeason:
    warnings: list[str] = []
    if not isinstance(raw, dict):
        raise ValueError("League payload is not an object.")

    fixtures = _fixtures(raw.get("dates"), warnings)
    teams = _teams(raw.get("teams"), fixtures, warnings)
    players = _players(raw.get("players"), league, season, warnings)
    for fixture in fixtures:  # ensure short names exist even for teams with no history yet
        for name, short in ((fixture.home, fixture.home_short), (fixture.away, fixture.away_short)):
            if name in teams and not teams[name].short:
                teams[name].short = short
    return LeagueSeason(league, season, teams, players, fixtures, warnings)


def _fixtures(raw: Any, warnings: list[str]) -> list[Fixture]:
    fixtures: list[Fixture] = []
    for item in rows(raw):
        try:
            home, away = item["h"], item["a"]
            played = bool(item.get("isResult"))
            goals, xg = item.get("goals") or {}, item.get("xG") or {}
            fixtures.append(
                Fixture(
                    id=integer(item.get("id")),
                    dt=str(item.get("datetime") or "")[:19],
                    home=text(home["title"]),
                    away=text(away["title"]),
                    home_short=text(home.get("short_title")),
                    away_short=text(away.get("short_title")),
                    played=played,
                    hg=integer(goals.get("h")) if played else None,
                    ag=integer(goals.get("a")) if played else None,
                    hxg=maybe_num(xg.get("h")) if played else None,
                    axg=maybe_num(xg.get("a")) if played else None,
                )
            )
        except (KeyError, TypeError):
            warnings.append("Skipped an unreadable fixture row.")
    fixtures.sort(key=lambda f: (f.dt, f.id))
    counts: dict[str, int] = {}
    for fixture in fixtures:
        counts[fixture.home] = counts.get(fixture.home, 0) + 1
        counts[fixture.away] = counts.get(fixture.away, 0) + 1
        fixture.round = max(counts[fixture.home], counts[fixture.away])
    return fixtures


def _teams(raw: Any, fixtures: list[Fixture], warnings: list[str]) -> dict[str, Team]:
    by_key: dict[tuple[str, str], Fixture] = {}
    for fixture in fixtures:
        for team, opponent in ((fixture.home, fixture.away), (fixture.away, fixture.home)):
            by_key[(team, fixture.dt)] = fixture
            by_key.setdefault((team, fixture.date), fixture)  # date-only fallback

    shorts: dict[str, str] = {}
    for fixture in fixtures:
        shorts.setdefault(fixture.home, fixture.home_short)
        shorts.setdefault(fixture.away, fixture.away_short)

    teams: dict[str, Team] = {}
    for entry in rows(raw):
        name = text(entry.get("title"))
        if not name:
            warnings.append("Skipped a team without a title.")
            continue
        history: list[TeamMatch] = []
        for row in rows(entry.get("history")):
            match = _team_match(row)
            if match is None:
                warnings.append(f"Skipped an unreadable match row for {name}.")
                continue
            fixture = by_key.get((name, match.dt)) or by_key.get((name, match.date))
            if fixture is not None:
                match.opponent = fixture.away if fixture.home == name else fixture.home
                match.match_id = fixture.id
            history.append(match)
        history.sort(key=lambda m: (m.dt, m.venue))
        for index, match in enumerate(history, start=1):
            match.matchweek = index
        teams[name] = Team(id=integer(entry.get("id")), name=name, short=shorts.get(name, ""), history=history)
    return teams


def _team_match(row: dict) -> TeamMatch | None:
    dt = str(row.get("date") or "")[:19]
    if len(dt) < 10:
        return None
    ppda, oppda = row.get("ppda") or {}, row.get("ppda_allowed") or {}
    return TeamMatch(
        dt=dt,
        venue=str(row.get("h_a") or "h"),
        xg=num(row.get("xG")),
        xga=num(row.get("xGA")),
        npxg=num(row.get("npxG")),
        npxga=num(row.get("npxGA")),
        deep=num(row.get("deep")),
        deep_allowed=num(row.get("deep_allowed")),
        gf=integer(row.get("scored")),
        ga=integer(row.get("missed")),
        xpts=num(row.get("xpts")),
        pts=integer(row.get("pts")),
        result=str(row.get("result") or "").lower()[:1],
        ppda_att=num(ppda.get("att")),
        ppda_def=num(ppda.get("def")),
        oppda_att=num(oppda.get("att")),
        oppda_def=num(oppda.get("def")),
    )


def _players(raw: Any, league: str, season: int, warnings: list[str]) -> list[PlayerSeason]:
    players: list[PlayerSeason] = []
    for row in rows(raw):
        pid = integer(row.get("id"))
        name = text(row.get("player_name"))
        if not pid or not name:
            warnings.append("Skipped a player row without id/name.")
            continue
        players.append(
            PlayerSeason(
                id=pid,
                name=name,
                teams=_split_teams(row.get("team_title")),
                position=str(row.get("position") or "").strip(),
                games=integer(row.get("games")),
                minutes=integer(row.get("time")),
                goals=integer(row.get("goals")),
                npg=integer(row.get("npg")),
                assists=integer(row.get("assists")),
                shots=integer(row.get("shots")),
                key_passes=integer(row.get("key_passes")),
                yellow=integer(row.get("yellow_cards")),
                red=integer(row.get("red_cards")),
                xg=num(row.get("xG")),
                npxg=num(row.get("npxG")),
                xa=num(row.get("xA")),
                xgchain=num(row.get("xGChain")),
                xgbuildup=num(row.get("xGBuildup")),
                league=league,
                season=season,
            )
        )
    return players


# ---------------------------------------------------------------------- player page


def _shot(row: dict) -> Shot:
    return Shot(
        id=integer(row.get("id")),
        minute=integer(row.get("minute")),
        xg=num(row.get("xG")),
        result=str(row.get("result") or ""),
        x=min(1.0, max(0.0, num(row.get("X")))),
        y=min(1.0, max(0.0, num(row.get("Y")))),
        situation=str(row.get("situation") or ""),
        shot_type=str(row.get("shotType") or ""),
        last_action=str(row.get("lastAction") or ""),
        player=text(row.get("player")),
        player_id=integer(row.get("player_id")) or None,
        venue=str(row.get("h_a") or ""),
        season=integer(row.get("season")),
        match_id=integer(row.get("match_id")) or None,
        home=text(row.get("h_team")),
        away=text(row.get("a_team")),
        date=str(row.get("date") or "")[:10],
        assisted_by=(text(row.get("player_assisted")) or None),
    )


def _career_row(row: dict) -> CareerSeason:
    return CareerSeason(
        season=integer(row.get("season")),
        team=text(row.get("team")),
        position=str(row.get("position") or ""),
        games=integer(row.get("games")),
        minutes=integer(row.get("time")),
        goals=integer(row.get("goals")),
        npg=integer(row.get("npg")),
        assists=integer(row.get("assists")),
        shots=integer(row.get("shots")),
        key_passes=integer(row.get("key_passes")),
        yellow=integer(row.get("yellow_cards")),
        red=integer(row.get("red_cards")),
        xg=num(row.get("xG")),
        npxg=num(row.get("npxG")),
        xa=num(row.get("xA")),
        xgchain=num(row.get("xGChain")),
        xgbuildup=num(row.get("xGBuildup")),
    )


def _split(entries: Iterable[dict], *names: str) -> list[SplitRow]:
    out: list[SplitRow] = []
    for entry in entries:
        name = next((entry[n] for n in names if entry.get(n)), None)
        if not name:
            continue
        out.append(SplitRow(str(name), integer(entry.get("shots")), integer(entry.get("goals")), num(entry.get("xG"))))
    out.sort(key=lambda r: -r.xg)
    return out


def _by_season(group: Any) -> dict[int, list[dict]]:
    if not isinstance(group, dict):
        return {}
    result: dict[int, list[dict]] = {}
    for key, value in group.items():
        try:
            season = int(key)
        except (TypeError, ValueError):
            continue
        result[season] = rows(value)
    return result


def normalize_player_page(raw: dict, player_id: int) -> PlayerPage:
    if not isinstance(raw, dict):
        raise ValueError("Player payload is not an object.")
    info = raw.get("player")
    if isinstance(info, list):
        info = info[0] if info else {}
    info = info if isinstance(info, dict) else {}

    shots = sorted((_shot(r) for r in rows(raw.get("shots"))), key=lambda s: (s.date, s.minute))
    groups = raw.get("groups") if isinstance(raw.get("groups"), dict) else {}
    career = sorted((_career_row(r) for r in rows(groups.get("season"))), key=lambda c: c.season)

    splits: dict[int, dict[str, list[SplitRow]]] = {}
    for label, group, names in (
        ("situations", "situation", ("situation",)),
        ("zones", "shotZones", ("shotZones", "shotZone")),
        ("types", "shotTypes", ("shotTypes", "shotType")),
        ("positions", "position", ("position",)),
    ):
        for season, entries in _by_season(groups.get(group)).items():
            splits.setdefault(season, {})[label] = _split(entries, *names)

    positions_minutes = {
        season: [
            {"position": e.get("position"), "games": integer(e.get("games")), "minutes": integer(e.get("time"))}
            for e in entries
            if e.get("position")
        ]
        for season, entries in _by_season(groups.get("position")).items()
    }

    name = info.get("player_name") or info.get("name")
    if not name and shots:
        name = shots[-1].player
    favorite = info.get("favorite_position")
    return PlayerPage(
        id=player_id,
        name=text(name) or None,
        favorite_position=text(favorite) or None,
        shots=shots,
        career=career,
        splits=splits,
        positions_minutes=positions_minutes,
    )


# ---------------------------------------------------------------------- match page


def normalize_match_page(raw: dict, match_id: int) -> MatchPage:
    if not isinstance(raw, dict):
        raise ValueError("Match payload is not an object.")
    shots_raw = raw.get("shots") if isinstance(raw.get("shots"), dict) else {}
    rosters_raw = raw.get("rosters") if isinstance(raw.get("rosters"), dict) else {}
    shots = {
        side: sorted((_shot(r) for r in rows(shots_raw.get(side))), key=lambda s: s.minute) for side in ("h", "a")
    }
    rosters: dict[str, list[RosterEntry]] = {}
    for side in ("h", "a"):
        entries = []
        for r in rows(rosters_raw.get(side)):
            entries.append(
                RosterEntry(
                    player_id=integer(r.get("player_id") or r.get("id")),
                    player=text(r.get("player")),
                    position=str(r.get("position") or ""),
                    minutes=integer(r.get("time")),
                    goals=integer(r.get("goals")),
                    own_goals=integer(r.get("own_goals")),
                    shots=integer(r.get("shots")),
                    xg=num(r.get("xG")),
                    key_passes=integer(r.get("key_passes")),
                    assists=integer(r.get("assists")),
                    xa=num(r.get("xA")),
                    xgchain=num(r.get("xGChain")),
                    xgbuildup=num(r.get("xGBuildup")),
                    yellow=integer(r.get("yellow_card")),
                    red=integer(r.get("red_card")),
                    venue=side,
                )
            )
        entries.sort(key=lambda e: (-e.minutes, e.player))
        rosters[side] = entries
    return MatchPage(id=match_id, shots=shots, rosters=rosters)


# ---------------------------------------------------------------------- team page


def _stat_row(name: str, value: dict) -> dict:
    against = value.get("against") if isinstance(value.get("against"), dict) else {}
    return {
        "name": str(value.get("stat") or name),
        "time": integer(value.get("time")) if value.get("time") is not None else None,
        "shots": integer(value.get("shots")),
        "goals": integer(value.get("goals")),
        "xg": round(num(value.get("xG")), 3),
        "against": {
            "shots": integer(against.get("shots")),
            "goals": integer(against.get("goals")),
            "xg": round(num(against.get("xG")), 3),
        },
    }


def normalize_team_page(raw: dict, team: str, season: int) -> TeamPage:
    if not isinstance(raw, dict):
        raise ValueError("Team payload is not an object.")
    statistics = raw.get("statistics") if isinstance(raw.get("statistics"), dict) else {}
    groups: dict[str, list[dict]] = {}
    for group, entries in statistics.items():
        if not isinstance(entries, dict):
            continue
        groups[str(group)] = [_stat_row(str(k), v) for k, v in entries.items() if isinstance(v, dict)]
    return TeamPage(team=team, season=season, groups=groups)
