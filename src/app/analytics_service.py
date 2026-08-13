from __future__ import annotations

from typing import Any

from .analytics import career as career_engine
from .analytics import player as player_engine
from .analytics import team as team_engine
from .analytics import league as league_engine
from .analytics import match as match_engine
from .analytics._shared import as_list_matches
from .stat_data import UnderstatData


LEAGUES = ("EPL", "La_liga", "Serie_A", "Ligue_1")
DEFAULT_CAREER_SEASONS = 6


def _valid_date_range(start_date: str | None, end_date: str | None) -> tuple[str | None, str | None]:
    start = start_date.strip() if start_date and start_date.strip() else None
    end = end_date.strip() if end_date and end_date.strip() else None
    if start and end and start > end:
        raise ValueError(f"start_date ({start}) must not be after end_date ({end}).")
    return start, end


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
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        start_date, end_date = _valid_date_range(start_date, end_date)
        if player_id is None:
            matches = await self.client.search_players(player_name)
            if not matches:
                raise ValueError(f"Player '{player_name}' was not found via Understat search.")
            player_id = int(matches[0]["id"])

        league_players = await self.client.get_league_player_stats(
            league_name, season, start_date=start_date, end_date=end_date
        )
        target = next((p for p in league_players if int(p["id"]) == player_id), None)
        if target is None:
            window = _window_label(start_date, end_date)
            raise ValueError(
                f"Player id {player_id} is not in {league_name} {season}{window} per the league player stats table."
            )

        teammates = [
            p for p in league_players
            if p.get("team_title") == target.get("team_title") and int(p.get("id", 0)) != player_id
        ]
        report = player_engine.player_report(target, league_players, teammates)
        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        return report

    async def player_career(
        self,
        player_name: str | None = None,
        player_id: int | None = None,
        league_name: str = "EPL",
        seasons: list[int] | None = None,
        season_end: int | None = None,
    ) -> dict:
        if player_id is None and player_name is None:
            raise ValueError("Either player_id or player_name is required.")

        if player_id is None:
            matches = await self.client.search_players(player_name)
            if not matches:
                raise ValueError(f"Player '{player_name}' was not found via Understat search.")
            resolved = matches[0]
            player_id = int(resolved["id"])
            player_name = resolved.get("player") or resolved.get("player_name") or player_name
        else:
            player_name = player_name or f"player {player_id}"

        if seasons:
            target_seasons = sorted(int(s) for s in seasons)
        else:
            end = season_end or 2025
            target_seasons = list(range(end - DEFAULT_CAREER_SEASONS + 1, end + 1))

        import asyncio

        async def fetch_season(season: int):
            players = await self.client.get_league_player_stats(league_name, season)
            return {
                "season": season,
                "player": next((p for p in players if int(p.get("id", 0)) == player_id), None),
            }

        season_rows = await asyncio.gather(*(fetch_season(s) for s in target_seasons))
        return career_engine.career_trajectory(season_rows, player_name, league_name)

    async def compare_players(
        self,
        player_1: str,
        player_2: str,
        league_name: str = "EPL",
        season: int = 2025,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        league_players = await self.client.get_league_player_stats(
            league_name, season, start_date=start_date, end_date=end_date
        )
        first = await self._resolve_player(player_1, league_players, league_name, season)
        second = await self._resolve_player(player_2, league_players, league_name, season)
        first_report = player_engine.player_report(first, league_players)
        second_report = player_engine.player_report(second, league_players)
        return {
            "league_name": league_name,
            "season": season,
            "date_window": {"start_date": start_date, "end_date": end_date},
            "pool_size": len(league_players),
            "players": {
                player_1: first_report,
                player_2: second_report,
            },
            "radar_labels": [entry["label"] for entry in first_report["radar"]["profile"]],
            "limitations": first_report["limitations"],
        }

    async def compare_teams(
        self,
        team_1: str,
        team_2: str,
        league_name: str = "EPL",
        season: int = 2025,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        table = await self.client.get_league_table(
            league_name, season, start_date=start_date, end_date=end_date
        )
        first_row = _find_team_row(table, team_1)
        second_row = _find_team_row(table, team_2)
        if first_row is None or second_row is None:
            raise ValueError(
                f"One of '{team_1}' / '{team_2}' is not in the {league_name} {season} table"
                f"{_window_label(start_date, end_date)}."
            )

        history_1 = _filter_history(
            await self.client.get_team_history(team_1, season, league_name), start_date, end_date
        )
        history_2 = _filter_history(
            await self.client.get_team_history(team_2, season, league_name), start_date, end_date
        )
        meetings = await self._head_to_head(league_name, season, team_1, team_2, start_date, end_date)

        return {
            "league_name": league_name,
            "season": season,
            "date_window": {"start_date": start_date, "end_date": end_date},
            "team_1": {"name": team_1, "report": team_engine.team_report(first_row, team_history=history_1)},
            "team_2": {"name": team_2, "report": team_engine.team_report(second_row, team_history=history_2)},
            "head_to_head": meetings,
        }

    async def _resolve_player(self, name: str, league_players: list[dict], league_name: str, season: int) -> dict:
        matches = [p for p in league_players if (p.get("player_name") or "").lower() == name.lower()]
        if matches:
            return matches[0]
        found = await self.client.search_players(name)
        if not found:
            raise ValueError(f"Player '{name}' was not found via Understat search.")
        player_id = int(found[0]["id"])
        target = next((p for p in league_players if int(p.get("id", 0)) == player_id), None)
        if target is None:
            raise ValueError(f"Player '{name}' is not in the {league_name} {season} league stats table.")
        return target

    async def _head_to_head(
        self,
        league_name: str,
        season: int,
        team_1: str,
        team_2: str,
        start_date: str | None,
        end_date: str | None,
    ) -> list[dict]:
        data = await self.client.get_league_data(league_name, season)
        meetings = []
        for item in as_list_matches(data.get("dates", [])):
            home = (item.get("h") or {}).get("title")
            away = (item.get("a") or {}).get("title")
            if {home, away} != {team_1, team_2}:
                continue
            date = (item.get("datetime") or "")[:10]
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            goals = item.get("goals") or {}
            xg = item.get("xG") or {}
            meetings.append(
                {
                    "match_id": item.get("id"),
                    "date": date,
                    "home": home,
                    "away": away,
                    "home_goals": _to_int(goals.get("h")),
                    "away_goals": _to_int(goals.get("a")),
                    "home_xg": _to_float(xg.get("h")),
                    "away_xg": _to_float(xg.get("a")),
                    "played": bool(item.get("isResult")),
                }
            )
        return sorted(meetings, key=lambda m: m["date"])

    async def analyze_team(
        self,
        team_name: str,
        league_name: str = "EPL",
        season: int = 2025,
        with_shots: bool = False,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        table = await self.client.get_league_table(
            league_name, season, start_date=start_date, end_date=end_date
        )
        team_row = next((r for r in table[1:] if str(r[0]).lower() == team_name.lower()), None)
        if team_row is None:
            raise ValueError(
                f"Team '{team_name}' is not in the {league_name} {season} league table"
                f"{_window_label(start_date, end_date)}."
            )

        history = _filter_history(
            await self.client.get_team_history(team_name, season, league_name), start_date, end_date
        )
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

        report = team_engine.team_report(team_row, team_history=history, team_shots=shots)
        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        return report

    async def analyze_league(
        self,
        league_name: str = "EPL",
        season: int = 2025,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        table = await self.client.get_league_table(
            league_name, season, start_date=start_date, end_date=end_date
        )
        report = league_engine.league_report(table)
        report["date_window"] = {"start_date": start_date, "end_date": end_date}
        return report

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
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        start_date, end_date = _valid_date_range(start_date, end_date)
        league_players = await self.client.get_league_player_stats(
            league_name, season, start_date=start_date, end_date=end_date
        )
        filtered = [p for p in league_players if _minutes(p) >= minimum_minutes]
        from .analytics.percentiles import position_group as to_group
        if position_group:
            filtered = [p for p in filtered if to_group(p.get("position")) == position_group.upper()]
        filtered.sort(key=lambda p: _float(p, order_by), reverse=True)
        return {
            "league_name": league_name,
            "season": season,
            "date_window": {"start_date": start_date, "end_date": end_date},
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


def _find_team_row(table, team_name: str):
    rows = table[1:] if table and table[0] and str(table[0][0]).strip().lower() == "team" else (table or [])
    return next((r for r in rows if str(r[0]).lower() == team_name.lower()), None)


def _filter_history(history, start_date: str | None, end_date: str | None):
    rows = as_list_matches(history)
    if not start_date and not end_date:
        return rows
    filtered = []
    for row in rows:
        current = (row.get("date") or "")[:10]
        if not current:
            filtered.append(row)
            continue
        if start_date and current < start_date:
            continue
        if end_date and current > end_date:
            continue
        filtered.append(row)
    return filtered


def _window_label(start_date, end_date):
    if start_date and end_date:
        return f" between {start_date} and {end_date}"
    if start_date:
        return f" from {start_date}"
    if end_date:
        return f" until {end_date}"
    return ""


def _float(row: dict, key: str) -> float:
    try:
        return round(float(row.get(key, 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _minutes(row: dict) -> float:
    try:
        return float(row.get("time", 0))
    except (TypeError, ValueError):
        return 0.0
