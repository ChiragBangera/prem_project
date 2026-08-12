from __future__ import annotations

from typing import Any

from .analytics import player as player_engine
from .analytics import team as team_engine
from .analytics import league as league_engine
from .analytics import match as match_engine
from .stat_data import UnderstatData


LEAGUES = ("EPL", "La_liga", "Serie_A", "Ligue_1")


class AnalyticsService:
    """Fetches the right Understat data and runs the pure analytics engines over it."""

    def __init__(self, client: UnderstatData | None = None):
        self.client = client or UnderstatData()

    async def analyze_player(
        self,
        player_id: int | None = None,
        player_name: str | None = None,
        league_name: str = "EPL",
        season: int = 2025,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        if player_id is None:
            matches = await self.client.search_players(player_name)
            if not matches:
                raise ValueError(f"Player '{player_name}' was not found via Understat search.")
            player_id = int(matches[0]["id"])

        league_players = await self.client.get_league_player_stats(league_name, season)
        target = next((p for p in league_players if int(p["id"]) == player_id), None)
        if target is None:
            raise ValueError(f"Player id {player_id} is not in {league_name} {season} per the league player stats table.")

        teammates = [
            p for p in league_players
            if p.get("team_title") == target.get("team_title") and int(p.get("id", 0)) != player_id
        ]
        return player_engine.player_report(target, league_players, teammates)

    async def analyze_team(
        self,
        team_name: str,
        league_name: str = "EPL",
        season: int = 2025,
        with_shots: bool = False,
    ) -> dict:
        table = await self.client.get_league_table(league_name, season)
        team_row = next((r for r in table[1:] if str(r[0]).lower() == team_name.lower()), None)
        if team_row is None:
            raise ValueError(f"Team '{team_name}' is not in the {league_name} {season} league table.")

        history = await self.client.get_team_history(team_name, season, league_name)
        shots = None
        if with_shots:
            results = await self.client.get_team_results(team_name, season)
            match_ids = [int(m["id"]) for m in results if m.get("id")]
            import asyncio
            all_shots = await asyncio.gather(*(self.client.get_match_shots(mid) for mid in match_ids[:10]))
            shots = []
            for batch in all_shots:
                for side in ("h", "a"):
                    shots.extend(batch.get(side, []))

        return team_engine.team_report(team_row, team_history=history, team_shots=shots)

    async def analyze_league(self, league_name: str = "EPL", season: int = 2025) -> dict:
        table = await self.client.get_league_table(league_name, season)
        return league_engine.league_report(table)

    async def analyze_match(self, match_id: int) -> dict:
        shots = await self.client.get_match_shots(match_id)
        home_shots = shots.get("h", [])
        away_shots = shots.get("a", [])
        meta = {
            "h": (home_shots[0].get("h_team") if home_shots else "Home"),
            "a": (away_shots[0].get("a_team") if away_shots else "Away"),
        }
        return match_engine.match_report(meta, shots)

    async def discover_players(
        self,
        league_name: str = "EPL",
        season: int = 2025,
        position_group: str | None = None,
        minimum_minutes: float = 900,
        order_by: str = "npxG",
        limit: int = 20,
    ) -> dict:
        league_players = await self.client.get_league_player_stats(league_name, season)
        filtered = [p for p in league_players if _minutes(p) >= minimum_minutes]
        from .analytics.percentiles import position_group as to_group
        if position_group:
            filtered = [p for p in filtered if to_group(p.get("position")) == position_group.upper()]
        filtered.sort(key=lambda p: _float(p, order_by), reverse=True)
        return {
            "league_name": league_name,
            "season": season,
            "position_group": position_group,
            "minimum_minutes": minimum_minutes,
            "order_by": order_by,
            "limit": limit,
            "players": [
                {
                    "id": p.get("id"),
                    "name": p.get("player_name"),
                    "team": p.get("team_title"),
                    "position": p.get("position"),
                    "position_group": to_group(p.get("position")),
                    "minutes": int(_minutes(p)),
                    "npxG": _float(p, "npxG"),
                    "xA": _float(p, "xA"),
                    "xGChain": _float(p, "xGChain"),
                    "xGBuildup": _float(p, "xGBuildup"),
                    "goals": _float(p, "goals"),
                    "assists": _float(p, "assists"),
                }
                for p in filtered[:limit]
            ],
        }


def _float(row: dict, key: str) -> float:
    try:
        return round(float(row.get(key, 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _minutes(row: dict) -> float:
    try:
        return float(row.get("time", 0))
    except (TypeError, ValueError):
        return 0.0
