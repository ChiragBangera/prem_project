from __future__ import annotations

from datetime import date

from app.coach_eras import (
    default_coach_season,
    coach_window_for_season,
    find_coach_era_by_name,
)
from app.planner import PlannedQuestion


class Fetcher:
    """Fetches the Understat data bundle for a planned question."""

    def __init__(self, client, today: str | None = None):
        self.client = client
        self._today_iso = today

    @property
    def today(self) -> str:
        return self._today_iso or date.today().isoformat()

    async def fetch(self, plan: PlannedQuestion) -> dict:
        data: dict = {}
        for endpoint in plan.endpoints:
            if endpoint == "coach_era":
                data[endpoint] = await self._fetch_coach_era_data(plan)
            elif endpoint == "league_table":
                data[endpoint] = await self.client.get_league_table(
                    plan.league_name or "EPL",
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "league_fixtures":
                data[endpoint] = await self.client.get_league_fixtures(plan.league_name or "EPL", plan.season or 2025)
            elif endpoint == "league_results":
                data[endpoint] = await self.client.get_league_results(plan.league_name or "EPL", plan.season or 2025)
            elif endpoint == "league_player_stats":
                data[endpoint] = await self.client.get_league_player_stats(
                    plan.league_name or "EPL",
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "league_data":
                seasons = [plan.season, *plan.comparison_seasons]
                data[endpoint] = {
                    current_season: await self.client.get_league_data(
                        plan.league_name or "EPL",
                        current_season or 2025,
                    )
                    for current_season in seasons
                    if current_season is not None
                }
            elif endpoint == "team_stats":
                data[endpoint] = await self.client.get_team_stats(plan.team_name, plan.season or 2025)
            elif endpoint == "team_players":
                data[endpoint] = await self.client.get_team_players(plan.team_name, plan.season or 2025)
            elif endpoint == "team_results":
                data[endpoint] = await self.client.get_team_results(plan.team_name, plan.season or 2025)
            elif endpoint == "team_fixtures":
                data[endpoint] = await self.client.get_team_fixtures(plan.team_name, plan.season or 2025)
            elif endpoint == "team_player_stats":
                data[endpoint] = await self.client.get_team_player_stats(
                    plan.team_name,
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_data":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_data(plan.player_id)
            elif endpoint == "player_matches":
                if plan.player_id is None:
                    continue
                matches = await self.client.get_player_matches(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    matches,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_grouped_stats":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_grouped_stats(plan.player_id)
            elif endpoint == "player_shots":
                if plan.player_id is None:
                    continue
                shots = await self.client.get_player_shots(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    shots,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_matches_via_ajax":
                if plan.player_id is None:
                    continue
                matches = await self.client.get_player_matches_via_ajax(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    matches,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_last_match":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_last_match(plan.player_id)
            elif endpoint == "stats":
                data[endpoint] = await self.client.get_stats()

        if plan.intent == "player_compare" and plan.comparison_player_id is not None:
            comparison_data = await self.client.get_player_data(plan.comparison_player_id)
            comparison_matches = await self.client.get_player_matches(plan.comparison_player_id)
            data["comparison_player_data"] = comparison_data
            data["comparison_player_matches"] = self._filter_player_rows(
                comparison_matches,
                season=plan.season,
                start_date=plan.start_date,
                end_date=plan.end_date,
            )
        if plan.intent == "team_compare" and plan.comparison_team_name is not None:
            comparison_results = await self.client.get_team_results(plan.comparison_team_name, plan.season or 2025)
            data["comparison_team_results"] = comparison_results
        return data

    async def _fetch_team_window_bundle(self, team_name: str, league_name: str, season: int, start_date: str, end_date: str):
        league_table = await self.client.get_league_table(
            league_name,
            season,
            start_date=start_date,
            end_date=end_date,
        )
        team_results = await self.client.get_team_results(team_name, season)
        filtered_results = self._filter_rows_by_date(team_results, start_date=start_date, end_date=end_date)
        team_player_stats = await self.client.get_team_player_stats(
            team_name,
            season,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "league_table": league_table,
            "team_results": filtered_results,
            "team_player_stats": team_player_stats,
        }

    async def _fetch_coach_era_data(self, plan: PlannedQuestion):
        primary_era = find_coach_era_by_name(plan.coach_name, plan.team_name)
        if primary_era is None:
            return {}

        if plan.intent == "coach_compare":
            comparison_era = find_coach_era_by_name(plan.comparison_coach_name, plan.comparison_team_name or plan.team_name)
            if comparison_era is None:
                return {}
            season = plan.season or default_coach_season([primary_era, comparison_era], self.today)
            primary_window = coach_window_for_season(primary_era, season, self.today)
            comparison_window = coach_window_for_season(comparison_era, season, self.today)
            return {
                "season": season,
                "primary": await self._fetch_team_window_bundle(
                    team_name=primary_era.team_name,
                    league_name=primary_era.league_name,
                    season=season,
                    start_date=primary_window[0],
                    end_date=primary_window[1],
                ) if primary_window else None,
                "comparison": await self._fetch_team_window_bundle(
                    team_name=comparison_era.team_name,
                    league_name=comparison_era.league_name,
                    season=season,
                    start_date=comparison_window[0],
                    end_date=comparison_window[1],
                ) if comparison_window else None,
                "primary_window": primary_window,
                "comparison_window": comparison_window,
            }

        seasons = [plan.season] if plan.season is not None else self._coach_covered_seasons(primary_era)
        season_payloads = {}
        for season in seasons:
            window = coach_window_for_season(primary_era, season, self.today)
            if not window:
                continue
            season_payloads[season] = await self._fetch_team_window_bundle(
                team_name=primary_era.team_name,
                league_name=primary_era.league_name,
                season=season,
                start_date=window[0],
                end_date=window[1],
            )
            season_payloads[season]["window"] = window
        return {
            "coach_name": primary_era.coach_name,
            "team_name": primary_era.team_name,
            "seasons": season_payloads,
        }

    def _coach_covered_seasons(self, era):
        from app.coach_eras import coach_covered_seasons
        return coach_covered_seasons(era, self.today)

    def _filter_rows_by_date(self, rows, start_date=None, end_date=None):
        if not start_date and not end_date:
            return rows

        filtered = []
        for row in rows:
            row_date = self._row_date_value(row)
            if not row_date:
                filtered.append(row)
                continue

            current = row_date[:10]
            if start_date and current < start_date:
                continue
            if end_date and current > end_date:
                continue
            filtered.append(row)

        return filtered

    def _filter_player_rows(self, rows, season=None, start_date=None, end_date=None):
        filtered = rows
        if season is not None:
            filtered = [
                row for row in filtered
                if str(row.get("season", season)) == str(season)
            ]

        return self._filter_rows_by_date(
            filtered,
            start_date=start_date,
            end_date=end_date,
        )

    def _row_date_value(self, row):
        value = row.get("date") or row.get("datetime") or ""
        return value[:19]
