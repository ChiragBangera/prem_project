from __future__ import annotations

"""Multi-season career trajectory for a player within one league.

Honest scope: each season row comes from Understat's per-season league player
stats (totals over that season), so "impact" is always contextualised to the
season and to the team the player actually played for that year. No
cross-league career totals are invented.
"""

from .percentiles import to_float, position_group


def career_trajectory(season_rows: list[dict], player_name: str, league_name: str) -> dict:
    """Build a season-over-season view from per-season league player rows.

    `season_rows`: [{"season": 2021, "player": {league_player_stats row} | None}, ...]
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
        team = player.get("team_title")
        rows.append(
            {
                "season": season,
                "present": True,
                "team": team,
                "position": player.get("position"),
                "position_group": position_group(player.get("position")),
                "games": round(games, 0),
                "minutes": round(minutes, 0),
                "goals": to_float(player.get("goals")),
                "xG": to_float(player.get("xG")),
                "npxG": to_float(player.get("npxG")),
                "assists": to_float(player.get("assists")),
                "xA": to_float(player.get("xA")),
                "xGChain": to_float(player.get("xGChain")),
                "xGBuildup": to_float(player.get("xGBuildup")),
                "goals_per90": _per90(player.get("goals"), minutes),
                "xG_per90": _per90(player.get("xG"), minutes),
                "xA_per90": _per90(player.get("xA"), minutes),
                "xGChain_per90": _per90(player.get("xGChain"), minutes),
                "xGBuildup_per90": _per90(player.get("xGBuildup"), minutes),
            }
        )
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
            "different minute loads."
        ),
        "limitations": [
            "Season totals ignore role changes, injuries, and team quality; per-90 mitigates minutes only.",
            "Missing seasons can mean the player left the league or played zero minutes — Understat has no reason field.",
            "Understat xG is model-derived; cross-season comparisons carry the model's own drift.",
            "Only league matches are included; cup and continental minutes are not in this dataset.",
        ],
    }


def _per90(value, minutes: float) -> float:
    if minutes <= 0:
        return 0.0
    return round(to_float(value) * 90.0 / minutes, 3)
