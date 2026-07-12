from app.utils import Utils
from app.constants import (
    understat_header,
    understat_base_url,
    understat_stats_data_url,
    understat_league_data_url,
    team_data_url,
    understat_player_data_url,
    understat_match_data_url,
    understat_players_search_url,
    understat_player_matches_url,
    understat_league_page_url,
    understat_team_page_url,
    understat_player_page_url,
    understat_player_stat_header,
    understat_team_player_stat_url,
)
import aiohttp


class UnderstatData:
    def __init__(self, session=None):
        self._session = session
        self._own_session = session is None
        self.utils = Utils(understat_header)

    async def _get_data(
        self,
        url: str,
        method: str = "GET",
        payload: dict = None,
        header=None,
        parse_json=True,
    ):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True

        return await self.utils.get_data(
            url=url,
            session=self._session,
            method=method,
            header=header,
            parse_json=parse_json,
            payload=payload,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def _build_team_slug(self, team_name: str):
        return self.utils.normalize_team_name(team_name)

    def _build_team_data_url(self, team_name: str, season):
        team_name = self.utils.url_string_encoder(team_name=self._build_team_slug(team_name))
        return team_data_url.format(team_name, str(season))

    def _build_league_name(self, league_name: str):
        return self.utils.normalize_league_name(league_name)

    def _build_league_data_url(self, league_name: str, season):
        normalized_league = self._build_league_name(league_name)
        return understat_league_data_url.format(normalized_league, str(season))

    def _build_player_data_url(self, player_id):
        return understat_player_data_url.format(player_id)

    def _build_match_data_url(self, match_id):
        return understat_match_data_url.format(match_id)

    def _build_player_search_url(self, query: str):
        return understat_players_search_url.format(self.utils.url_string_encoder(query))

    def _build_player_matches_url(self, player_id):
        return understat_player_matches_url.format(player_id)

    def _build_league_page_url(self, league_name: str, season):
        normalized_league = self._build_league_name(league_name)
        return understat_league_page_url.format(normalized_league, str(season))

    def _build_team_page_url(self, team_name: str, season):
        team_slug = self._build_team_slug(team_name)
        return understat_team_page_url.format(team_slug, str(season))

    def _build_player_page_url(self, player_id):
        return understat_player_page_url.format(player_id)

    def _merge_filters(self, options=None, **kwargs):
        if options:
            return options
        return kwargs or None

    async def _post_player_stats(self, payload: dict, referer: str):
        header = dict(understat_player_stat_header)
        header["Referer"] = referer
        response = await self._get_data(
            url=understat_team_player_stat_url,
            method="POST",
            payload=payload,
            header=header,
        )
        return response.get("players", response)

    async def _post_player_matches(self, player_id):
        header = dict(understat_player_stat_header)
        header["Referer"] = self._build_player_page_url(player_id)
        response = await self._get_data(
            url=self._build_player_matches_url(player_id),
            method="POST",
            header=header,
        )
        return response.get("response", response)

    async def get_stats(self, options=None, **kwargs):
        stats = await self._get_data(url=understat_stats_data_url)
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(stats.get("stat", []), filters)

    async def get_league_data(self, league_name: str, season):
        url = self._build_league_data_url(league_name=league_name, season=season)
        return await self._get_data(url=url)

    async def get_team_data_by_season(self, team_name: str, season: str):
        """Get all the data present in the understat team page for a specific season

        Args:
            team_name (str): Any team name in title casing from EPL, LaLiga, Bundesliga, League 1 and Serie A
            season (str): Add the season eg: 25/26 as "2025"

        Returns:
            (json): returns a json object
        """

        url = self._build_team_data_url(team_name=team_name, season=season)
        return await self._get_data(url=url)

    async def get_team_data_by_year(self, team_name: str, year: str):
        return await self.get_team_data_by_season(team_name=team_name, season=year)

    async def get_player_data(self, player_id):
        url = self._build_player_data_url(player_id)
        return await self._get_data(url=url)

    async def search_players(self, query: str):
        url = self._build_player_search_url(query)
        header = dict(understat_header)
        header["Referer"] = understat_base_url
        response = await self._get_data(url=url, header=header)
        return response.get("response", {}).get("players", [])

    async def get_match_data(self, match_id):
        url = self._build_match_data_url(match_id)
        return await self._get_data(url=url)

    async def get_teams(self, league_name: str, season, options=None, **kwargs):
        league_data = await self.get_league_data(league_name=league_name, season=season)
        teams = list(league_data.get("teams", {}).values())
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(teams, filters)

    async def get_league_players(self, league_name: str, season, options=None, **kwargs):
        league_data = await self.get_league_data(league_name=league_name, season=season)
        players = league_data.get("players", [])
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(players, filters)

    async def get_league_results(self, league_name: str, season, options=None, **kwargs):
        league_data = await self.get_league_data(league_name=league_name, season=season)
        results = [match for match in league_data.get("dates", []) if match.get("isResult")]
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(results, filters)

    async def get_league_fixtures(self, league_name: str, season, options=None, **kwargs):
        league_data = await self.get_league_data(league_name=league_name, season=season)
        fixtures = [match for match in league_data.get("dates", []) if not match.get("isResult")]
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(fixtures, filters)

    async def get_league_table(
        self,
        league_name: str,
        season,
        with_headers: bool = True,
        h_a: str = "overall",
        start_date: str = None,
        end_date: str = None,
    ):
        league_data = await self.get_league_data(league_name=league_name, season=season)
        teams = league_data.get("teams", {})
        table_rows = []
        stat_keys = [
            "wins",
            "draws",
            "loses",
            "scored",
            "missed",
            "pts",
            "xG",
            "npxG",
            "xGA",
            "npxGA",
            "npxGD",
            "deep",
            "deep_allowed",
            "xpts",
        ]

        for _, team_data in teams.items():
            season_stats = team_data.get("history", [])

            if start_date is not None or end_date is not None:
                season_stats = self.utils.filter_by_date(
                    season_stats,
                    season=season,
                    start=start_date,
                    end=end_date,
                )

            if h_a.lower() != "overall":
                h_a_key = h_a[0].lower()
                season_stats = [
                    match for match in season_stats if match.get("h_a") == h_a_key
                ]

            team_row = [team_data.get("title"), len(season_stats)]
            team_row.extend(
                round(sum(match.get(key, 0) for match in season_stats), 2)
                for key in stat_keys
            )

            passes = sum(match.get("ppda", {}).get("att", 0) for match in season_stats)
            defensive_actions = sum(
                match.get("ppda", {}).get("def", 0) for match in season_stats
            )
            opponent_passes = sum(
                match.get("ppda_allowed", {}).get("att", 0) for match in season_stats
            )
            opponent_defensive_actions = sum(
                match.get("ppda_allowed", {}).get("def", 0) for match in season_stats
            )

            ppda = round(
                0 if defensive_actions == 0 else passes / defensive_actions,
                2,
            )
            oppda = round(
                0
                if opponent_defensive_actions == 0
                else opponent_passes / opponent_defensive_actions,
                2,
            )

            team_row.insert(-3, ppda)
            team_row.insert(-3, oppda)
            table_rows.append(team_row)

        table_rows = sorted(
            table_rows,
            key=lambda row: (-row[7], -(row[5] - row[6])),
        )

        if with_headers:
            return [
                [
                    "Team",
                    "M",
                    "W",
                    "D",
                    "L",
                    "G",
                    "GA",
                    "PTS",
                    "xG",
                    "NPxG",
                    "xGA",
                    "NPxGA",
                    "NPxGD",
                    "PPDA",
                    "OPPDA",
                    "DC",
                    "ODC",
                    "xPTS",
                ],
                *table_rows,
            ]

        return table_rows

    async def get_player_shots(self, player_id, options=None, **kwargs):
        player_data = await self.get_player_data(player_id)
        shots = player_data.get("shots", [])
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(shots, filters)

    async def get_player_matches(self, player_id, options=None, **kwargs):
        player_data = await self.get_player_data(player_id)
        matches = player_data.get("matches", [])
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(matches, filters)

    async def get_player_matches_via_ajax(self, player_id):
        response = await self._post_player_matches(player_id)
        return response.get("matches", [])

    async def get_player_last_match(self, player_id):
        response = await self._post_player_matches(player_id)
        return response.get("lastMatch", {})

    async def get_player_stats(self, player_id, positions=None):
        player_data = await self.get_player_data(player_id)
        stats = player_data.get("minMaxPlayerStats", {})
        return self.utils.filter_by_positions(stats, positions)

    async def get_player_grouped_stats(self, player_id):
        player_data = await self.get_player_data(player_id)
        return player_data.get("groups", {})

    async def get_team_stats(self, team_name: str, season):
        team_data = await self.get_team_data_by_season(team_name=team_name, season=season)
        return team_data.get("statistics", {})

    async def get_team_results(self, team_name: str, season, options=None, **kwargs):
        team_data = await self.get_team_data_by_season(team_name=team_name, season=season)
        results = [match for match in team_data.get("dates", []) if match.get("isResult")]
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(results, filters)

    async def get_team_fixtures(self, team_name: str, season, options=None, **kwargs):
        team_data = await self.get_team_data_by_season(team_name=team_name, season=season)
        fixtures = [match for match in team_data.get("dates", []) if not match.get("isResult")]
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(fixtures, filters)

    async def get_team_players(self, team_name: str, season, options=None, **kwargs):
        team_data = await self.get_team_data_by_season(team_name=team_name, season=season)
        players = team_data.get("players", [])
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(players, filters)

    async def get_match_players(self, match_id, options=None, **kwargs):
        match_data = await self.get_match_data(match_id)
        players = match_data.get("rosters", {})
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(players, filters)

    async def get_match_shots(self, match_id, options=None, **kwargs):
        match_data = await self.get_match_data(match_id)
        shots = match_data.get("shots", {})
        filters = self._merge_filters(options=options, **kwargs)
        return self.utils.filter_data(shots, filters)

    async def get_league_player_stats(
        self, league_name: str, season, start_date: str = None, end_date: str = None
    ):
        payload = {
            "league": self._build_league_name(league_name),
            "season": str(season),
            **self.utils.build_datetime_range(
                start_date=start_date,
                end_date=end_date,
            ),
        }

        referer = self._build_league_page_url(league_name=league_name, season=season)
        return await self._post_player_stats(payload=payload, referer=referer)

    async def get_team_player_stats(
        self, team_name: str, season: str, start_date: str = None, end_date: str = None
    ):
        """_summary_

        Args:
            team_name (str):
            season (str): Any team name in title casing from EPL, LaLiga, Bundesliga, League 1 and Serie A
            start_date (str, optional): Add date in yyyy-mm-dd eg: 2026-01-01. Defaults to None.
            end_date (str, optional): Add date in yyyy-mm-dd eg: 2026-01-31. Defaults to None.

        Returns:
            _type_: returns a json object
        """
        payload = {
            "team": self._build_team_slug(team_name),
            "season": str(season),
            **self.utils.build_datetime_range(
                start_date=start_date,
                end_date=end_date,
            ),
        }

        referer = self._build_team_page_url(team_name=team_name, season=season)
        return await self._post_player_stats(
            payload=payload,
            referer=referer,
        )

    async def close(self):
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()


Understat = UnderstatData
