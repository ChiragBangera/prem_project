from __future__ import annotations

"""StatsBomb open-data source: touches, pressures, carries, recoveries.

StatsBomb's free data is the only license-clean public source of event-level
touch/press/carry data. Coverage is limited to select competitions and seasons
(La Liga 2004/05–2020/21, Champions League 2004–2019, World Cups, women's
leagues) — there is NO current Premier League coverage. The dashboard labels
this source explicitly; it never mixes with Understat data.

Pitch model: 120 x 80. Each team's attacking direction is inferred from the
mean x of their own shots (a team shooting mostly at x > 60 attacks the right
goal). All zone classifications are relative to that direction.

Definitions follow StatsBomb's canonical ones:
- touch: any event by a player (every event IS a ball touch),
- pressure: a Pressure event,
- successful pressure: followed within 5s by the same team's Ball Recovery,
- carry: a Carry event, distance = euclidean between start and end locations,
- ball recovery: a Ball Recovery event.
"""

import asyncio
import json
import math

import aiohttp

BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
TIMEOUT_SECONDS = 30.0

_cache: dict[str, object] = {}


async def _get_json(path: str, session: aiohttp.ClientSession | None = None) -> object:
    key = path
    if key in _cache:
        return _cache[key]
    owns_session = session is None
    if session is None:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        session = aiohttp.ClientSession(timeout=timeout)
    try:
        async with session.get(f"{BASE}/{path}") as response:
            response.raise_for_status()
            payload = json.loads(await response.text())
    finally:
        if owns_session:
            await session.close()
    _cache[key] = payload
    return payload


async def list_competitions() -> list[dict]:
    payload = await _get_json("competitions.json")
    competitions = []
    for entry in payload or []:
        competitions.append(
            {
                "competition_id": entry.get("competition_id"),
                "season_id": entry.get("season_id"),
                "competition_name": entry.get("competition_name"),
                "season_name": entry.get("season_name"),
                "country": entry.get("country_name"),
            }
        )
    return competitions


async def list_matches(competition_id, season_id) -> list[dict]:
    payload = await _get_json(f"matches/{competition_id}/{season_id}.json")
    matches = []
    for entry in payload or []:
        matches.append(
            {
                "match_id": entry.get("match_id"),
                "date": entry.get("match_date"),
                "home": entry.get("home_team", {}).get("home_team_name"),
                "away": entry.get("away_team", {}).get("away_team_name"),
                "home_score": entry.get("home_score"),
                "away_score": entry.get("away_score"),
            }
        )
    return sorted(matches, key=lambda m: m["date"])


async def get_events(match_id) -> list[dict]:
    payload = await _get_json(f"events/{match_id}.json")
    return list(payload or [])


def _attack_direction(events: list[dict]) -> dict[str, float]:
    """Infer each team's attacking direction from the mean x of their shots."""
    shot_x: dict[str, list[float]] = {}
    for event in events:
        if (event.get("type") or {}).get("name") != "Shot":
            continue
        location = event.get("location")
        team = (event.get("team") or {}).get("name")
        if location and team:
            shot_x.setdefault(team, []).append(float(location[0]))
    direction = {}
    for team, xs in shot_x.items():
        direction[team] = 1.0 if (sum(xs) / len(xs)) > 60.0 else -1.0
    return direction


def _in_opposition_box(x: float, y: float, direction: float) -> bool:
    if direction > 0:
        return x >= 102.0 and 18.0 <= y <= 62.0
    return x <= 18.0 and 18.0 <= y <= 62.0


def _in_opposition_half(x: float, direction: float) -> bool:
    return x >= 60.0 if direction > 0 else x <= 60.0


def aggregate_match(match_id, events: list[dict]) -> dict:
    """Team-level touch/press/carry aggregates for a match."""
    direction = _attack_direction(events)
    team_names = sorted(set((e.get("team") or {}).get("name") for e in events if e.get("team")))
    stats = {
        team: {
            "touches": 0, "touches_opp_box": 0, "touches_opp_half": 0,
            "pressures": 0, "successful_pressures": 0,
            "carries": 0, "carry_distance": 0.0,
            "ball_recoveries": 0, "passes_completed": 0, "passes": 0,
            "final_third_entries": 0, "shots": 0, "goals": 0,
        }
        for team in team_names
    }
    recent_pressures: list[tuple[float, str]] = []

    for event in events:
        event_type = (event.get("type") or {}).get("name")
        team = (event.get("team") or {}).get("name")
        possession_team = (event.get("possession_team") or {}).get("name")
        minute = float(event.get("minute") or 0)
        second = float(event.get("second") or 0)
        t = minute * 60 + second
        location = event.get("location")
        stat = stats.get(team)
        if not stat:
            continue
        if event_type == "Pressure":
            stat["pressures"] += 1
            recent_pressures.append((t, team))
        elif event_type == "Ball Recovery":
            stat["ball_recoveries"] += 1
            for t0, presser in recent_pressures:
                if 0 < t - t0 <= 5.0 and presser == team:
                    stat["successful_pressures"] += 1
            recent_pressures = [(t0, presser) for t0, presser in recent_pressures if t - t0 <= 5.0]
        elif event_type == "Carry":
            stat["carries"] += 1
            end_location = (event.get("carry") or {}).get("end_location")
            if location and end_location:
                dx = float(end_location[0]) - float(location[0])
                dy = float(end_location[1]) - float(location[1])
                stat["carry_distance"] += math.sqrt(dx * dx + dy * dy)
        elif event_type == "Pass":
            stat["passes"] += 1
            pass_end = (event.get("pass") or {}).get("end_location")
            if event.get("pass", {}).get("outcome", {}).get("name") != "Incomplete":
                stat["passes_completed"] += 1
            if location and pass_end:
                entry_dir = direction.get(team, 1.0)
                if _in_opposition_half(float(location[0]), entry_dir) and _in_opposition_half(float(pass_end[0]), entry_dir):
                    stat["final_third_entries"] += 1
        elif event_type == "Shot":
            stat["shots"] += 1
            if event.get("shot", {}).get("outcome", {}).get("name") == "Goal":
                stat["goals"] += 1

        if location:
            entry_dir = direction.get(team, 1.0)
            stat["touches"] += 1
            if _in_opposition_box(float(location[0]), float(location[1]), entry_dir):
                stat["touches_opp_box"] += 1
            if _in_opposition_half(float(location[0]), entry_dir):
                stat["touches_opp_half"] += 1

    return {
        "match_id": match_id,
        "teams": {
            team: {key: round(value, 1) if isinstance(value, float) else value for key, value in values.items()}
            for team, values in stats.items()
        },
    }


def player_aggregates(events: list[dict], team_name: str, direction: float) -> list[dict]:
    """Per-player touch/press/carry aggregates for one team in a match."""
    players: dict[str, dict] = {}
    for event in events:
        team = (event.get("team") or {}).get("name")
        if team != team_name:
            continue
        player = (event.get("player") or {}).get("name")
        if not player:
            continue
        entry = players.setdefault(
            player,
            {"player": player, "touches": 0, "touches_opp_box": 0, "pressures": 0,
             "carries": 0, "carry_distance": 0.0, "ball_recoveries": 0,
             "passes_completed": 0, "shots": 0},
        )
        event_type = (event.get("type") or {}).get("name")
        location = event.get("location")
        if location:
            entry["touches"] += 1
            if _in_opposition_box(float(location[0]), float(location[1]), direction):
                entry["touches_opp_box"] += 1
        if event_type == "Pressure":
            entry["pressures"] += 1
        elif event_type == "Carry":
            entry["carries"] += 1
            end_location = (event.get("carry") or {}).get("end_location")
            if location and end_location:
                dx = float(end_location[0]) - float(location[0])
                dy = float(end_location[1]) - float(location[1])
                entry["carry_distance"] += math.sqrt(dx * dx + dy * dy)
        elif event_type == "Ball Recovery":
            entry["ball_recoveries"] += 1
        elif event_type == "Pass" and event.get("pass", {}).get("outcome", {}).get("name") != "Incomplete":
            entry["passes_completed"] += 1
        elif event_type == "Shot":
            entry["shots"] += 1
    result = []
    for entry in players.values():
        entry["carry_distance"] = round(entry["carry_distance"], 1)
        result.append(entry)
    return sorted(result, key=lambda p: -p["touches"])
