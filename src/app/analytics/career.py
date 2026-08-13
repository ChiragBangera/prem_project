from __future__ import annotations

"""Multi-season career trajectory for a player within one league.

Honest scope: each season row comes from Understat's per-season league player
stats (totals over that season), so "impact" is always contextualised to the
season and to the team the player actually played for that year. The optional
player_data groups add the shot profile (situations, zones, shot types) and
starter/sub role split for seasons the player spent in this league. No
cross-league career totals are invented.
"""

from .percentiles import to_float, position_group


def career_trajectory(
    season_rows: list[dict],
    player_name: str,
    league_name: str,
    player_groups: dict | None = None,
) -> dict:
    """Build a season-over-season view from per-season league player rows.

    `season_rows`: [{"season": 2021, "player": {league_player_stats row} | None}, ...]
    `player_groups`: optional Understat player_data "groups" payload keyed by
    group name -> season -> entries, used for shot profile + role split.
    """
    rows = []
    previous_team = None
    team_changes = []
    for entry in season_rows:
        season = entry["season"]
        player = entry.get("player")
        if player is None:
            rows.append(
                {
                    "season": season,
                    "present": False,
                    "note": "Not in this league's season stats (left the league, injured all season, or no minutes).",
                }
            )
            previous_team = None
            continue
        minutes = to_float(player.get("time"))
        games = to_float(player.get("games"))
        shots = to_float(player.get("shots"))
        goals = to_float(player.get("goals"))
        xg = to_float(player.get("xG"))
        npxg = to_float(player.get("npxG"))
        xa = to_float(player.get("xA"))
        team = player.get("team_title")
        row = {
            "season": season,
            "present": True,
            "team": team,
            "position": player.get("position"),
            "position_group": position_group(player.get("position")),
            "games": round(games, 0),
            "minutes": round(minutes, 0),
            "goals": goals,
            "xG": xg,
            "npxG": npxg,
            "npg": to_float(player.get("npg")),
            "assists": to_float(player.get("assists")),
            "xA": xa,
            "shots": shots,
            "key_passes": to_float(player.get("key_passes")),
            "yellow_cards": to_float(player.get("yellow_cards")),
            "red_cards": to_float(player.get("red_cards")),
            "xGChain": to_float(player.get("xGChain")),
            "xGBuildup": to_float(player.get("xGBuildup")),
            "goals_per90": _per90(goals, minutes),
            "xG_per90": _per90(xg, minutes),
            "xA_per90": _per90(xa, minutes),
            "xGChain_per90": _per90(player.get("xGChain"), minutes),
            "xGBuildup_per90": _per90(player.get("xGBuildup"), minutes),
            "shots_per90": _per90(shots, minutes),
            "key_passes_per90": _per90(player.get("key_passes"), minutes),
            "goal_involvement_per90": round(_per90(npxg + xa, minutes), 3),
            "xG_per_shot": _ratio(xg, shots),
            "conversion": _ratio(goals, shots),
        }
        _attach_shot_profile(row, player_groups, season)
        rows.append(row)
        if previous_team is not None and team != previous_team:
            team_changes.append({"season": season, "from": previous_team, "to": team})
        previous_team = team

    present_rows = [row for row in rows if row.get("present")]
    return {
        "player_name": player_name,
        "league_name": league_name,
        "seasons": rows,
        "n_seasons_present": len(present_rows),
        "team_changes": team_changes,
        "interpretation": (
            f"{player_name} appears in {len(present_rows)} of {len(rows)} queried "
            f"{league_name} seasons. xGChain/xGBuildup are season totals — per-90 "
            "columns are the honest way to compare impact across seasons with "
            "different minute loads. Shot profile columns show the player's "
            "chance mix for each in-league season."
        ),
        "limitations": [
            "Season totals ignore role changes, injuries, and team quality; per-90 mitigates minutes only.",
            "Missing seasons can mean the player left the league or played zero minutes — Understat has no reason field.",
            "Understat xG is model-derived; cross-season comparisons carry the model's own drift.",
            "Only league matches are included; cup and continental minutes are not in this dataset.",
            "Shot profiles are shares of the player's own xG — a striker's penalty share inflates totals without improving open-play output.",
        ],
    }


def _attach_shot_profile(row: dict, player_groups: dict | None, season: int) -> None:
    if not player_groups:
        row["shot_profile"] = None
        row["role_split"] = None
        return
    season_key = str(season)

    situations = _season_entries(player_groups.get("situation", {}), season_key)
    zones = _season_entries(player_groups.get("shotZones", {}), season_key)
    types = _season_entries(player_groups.get("shotTypes", {}), season_key)
    positions = _season_entries(player_groups.get("position", {}), season_key)

    total_xg = sum(to_float(entry.get("xG")) for entry in situations) or None
    row["shot_profile"] = {
        "situations": _share_rows(situations, total_xg, "situation"),
        "zones": _share_rows(zones, total_xg, "shotZones"),
        "types": _share_rows(types, total_xg, "shotTypes"),
    }
    role_rows = [
        {
            "role": entry.get("position") or entry.get("positionGroup", "?"),
            "games": to_float(entry.get("games")),
            "minutes": to_float(entry.get("time")),
        }
        for entry in positions
    ]
    row["role_split"] = role_rows or None


def _season_entries(group: dict, season_key: str) -> list[dict]:
    value = group.get(season_key) if isinstance(group, dict) else None
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def _share_rows(entries: list[dict], total_xg: float | None, name_key: str) -> list[dict]:
    if not entries:
        return []
    total = total_xg or sum(to_float(entry.get("xG")) for entry in entries) or 1.0
    rows = []
    for entry in entries:
        xg = to_float(entry.get("xG"))
        rows.append(
            {
                "name": entry.get(name_key) or entry.get("situation") or "?",
                "shots": to_float(entry.get("shots")),
                "goals": to_float(entry.get("goals")),
                "xG": round(xg, 2),
                "xG_share": round(xg / total, 3),
            }
        )
    rows.sort(key=lambda r: -r["xG"])
    return rows


def _per90(value, minutes: float) -> float:
    if minutes <= 0:
        return 0.0
    return round(to_float(value) * 90.0 / minutes, 3)


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)
