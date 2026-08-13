from __future__ import annotations

"""StatsBomb service: the touches/pressures/carries source behind the dashboard."""

from .stat_data import statsbomb


class StatsBombService:
    def __init__(self):
        pass

    async def competitions(self) -> dict:
        competitions = await statsbomb.list_competitions()
        return {
            "competitions": competitions,
            "note": (
                "StatsBomb open data is a separate, free source with limited coverage "
                "(La Liga 2004–2021, Champions League 2004–2019, World Cups, women's leagues). "
                "It does NOT cover the current Premier League. These metrics never mix with Understat data."
            ),
        }

    async def matches(self, competition_id: int, season_id: int) -> dict:
        matches = await statsbomb.list_matches(competition_id, season_id)
        if not matches:
            raise ValueError(f"No matches found for competition {competition_id} season {season_id}.")
        return {"competition_id": competition_id, "season_id": season_id, "matches": matches}

    async def analyze_match(self, match_id: int) -> dict:
        events = await statsbomb.get_events(match_id)
        if not events:
            raise ValueError(f"No events found for match {match_id}.")
        aggregates = statsbomb.aggregate_match(match_id, events)
        direction = statsbomb._attack_direction(events)
        team_players = {}
        for team in aggregates["teams"]:
            team_players[team] = statsbomb.player_aggregates(events, team, direction.get(team, 1.0))
        return {
            "match_id": match_id,
            "teams": aggregates["teams"],
            "player_leaderboards": team_players,
            "definitions": {
                "touch": "Every event a player makes is a touch of the ball.",
                "touches_opp_box": "Touches inside the opposition penalty box.",
                "pressure": "A Pressure event: closing down the player on the ball.",
                "successful_pressure": "Pressure followed within 5 seconds by the same team's Ball Recovery.",
                "carry": "A Carry event: moving the ball at feet; distance in metres.",
                "ball_recovery": "Winning back a loose ball.",
                "final_third_entries": "Passes ending in the opposition half from the opposition half.",
            },
            "limitations": [
                "StatsBomb coordinates are pitch-relative; attacking direction is inferred from shot locations per team.",
                "Coverage is limited to StatsBomb's free competitions; no current Premier League data.",
                "Touches in the box include all event types (passes, carries, shots) inside the penalty area.",
                "Successful-pressure definition is the canonical 5-second regain rule, applied approximately.",
            ],
        }
