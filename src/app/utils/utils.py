import json
from datetime import datetime
from urllib.parse import quote

import aiohttp


class Utils:
    LEAGUE_NAME_MAPPER = {
        "epl": "EPL",
        "la_liga": "La_liga",
        "bundesliga": "Bundesliga",
        "serie_a": "Serie_A",
        "ligue_1": "Ligue_1",
        "rfpl": "RFPL",
    }

    def __init__(self, header):
        self.header = header

    async def get_data(
        self,
        url: str,
        method: str = "GET",
        session: aiohttp.ClientSession = None,
        payload: dict = None,
        header=None,
        parse_json=True,
    ):
        """General purpose networking method

        Args:
            url (str): site url
            method (str, optional): Defaults to "GET".
            session (aiohttp.ClientSession, optional): aiohttp session. Defaults to None.
            payload (dict, optional): Add dict payload if any. Defaults to None.
            header (_type_, optional): Defaults to None.

        Returns:
            _type_: _description_
        """
        main_session = session if session else aiohttp.ClientSession()
        active_header = header if header else self.header

        try:
            async with main_session.request(
                url=url, method=method, data=payload, headers=active_header
            ) as response:
                response.raise_for_status()
                if parse_json:
                    return await self.response_parser(response=response)
                else:
                    return await response.text()

        finally:
            if session is None:
                await main_session.close()

    async def response_parser(self, response):
        """Converts the text reponse into json object

        Args:
            response (_type_): _description_

        Returns:
            _type_: _description_
        """
        data = await response.text()
        try:
            return json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError("Understat response was not valid JSON") from exc

    def url_string_encoder(self, team_name: str):
        """Encodes the team name

        Args:
            team_name (str): _description_

        Returns:
            _type_: _description_
        """
        return quote(team_name)

    def normalize_team_name(self, team_name: str):
        return team_name.replace(" ", "_")

    def normalize_league_name(self, league_name: str):
        normalized_name = league_name.strip().lower().replace(" ", "_")
        return self.LEAGUE_NAME_MAPPER.get(normalized_name, league_name)

    def filter_data(self, data, options=None):
        if not options:
            return data

        if isinstance(data, dict):
            if not all(hasattr(value, "get") for value in data.values()):
                return data

            return {
                key: value
                for key, value in data.items()
                if all(
                    value.get(option_key) == option_value
                    for option_key, option_value in options.items()
                )
            }

        return [
            item
            for item in data
            if all(
                item.get(option_key) == option_value
                for option_key, option_value in options.items()
            )
        ]

    def filter_by_positions(self, data, positions=None):
        relevant_stats = []

        for position, stats in data.items():
            if not positions or position in positions:
                position_stats = dict(stats)
                position_stats["position"] = position
                relevant_stats.append(position_stats)

        return relevant_stats

    def filter_by_date(self, data, season, start=None, end=None):
        try:
            start_date = (
                datetime.strptime(start, "%Y-%m-%d")
                if start is not None
                else datetime(int(season), 1, 1)
            )
            end_date = (
                datetime.strptime(end, "%Y-%m-%d")
                if end is not None
                else datetime(int(season) + 1, 12, 31)
            )
        except ValueError as exc:
            raise ValueError("Invalid date format. Please use YYYY-MM-DD.") from exc

        filtered = []
        for item in data:
            match_date = item.get("date", "").split(" ")[0]
            if not match_date:
                continue

            parsed_match_date = datetime.strptime(match_date, "%Y-%m-%d")
            if start_date <= parsed_match_date <= end_date:
                filtered.append(item)

        return filtered

    def build_datetime_range(self, start_date=None, end_date=None):
        def _validate(date_value):
            if not date_value:
                return ""
            datetime.strptime(date_value, "%Y-%m-%d")
            return date_value

        start_value = _validate(start_date)
        end_value = _validate(end_date)

        return {
            "date_start": f"{start_value} 00:00:00" if start_value else "",
            "date_end": f"{end_value} 23:59:59" if end_value else "",
        }
