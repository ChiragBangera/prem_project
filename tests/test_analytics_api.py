import unittest

import httpx

from app.api import app
from app.analytics_service import AnalyticsService


class FakeAnalyticsClient:
    """Canned Understat-shaped data for the analytics service (no network)."""

    TABLE = [
        ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA",
         "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
        ["Arsenal", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0,
         9.8, 11.9, 290, 210, 60.1],
        ["Chelsea", 30, 12, 8, 10, 48, 40, 44, 50.0, 47.0, 39.0, 38.0, 9.0,
         11.0, 12.8, 250, 260, 50.8],
    ]

    PLAYERS = [
        {
            "id": "8260", "player_name": "Erling Haaland",
            "team_title": "Manchester City", "position": "F", "goals": "22",
            "xG": "20.1", "npxG": "19.5", "assists": "4", "xA": "4.2",
            "shots": "110", "key_passes": "30", "xGChain": "120",
            "xGBuildup": "60", "time": "2400",
        }
    ]

    async def get_league_table(self, league_name, season, *args, **kwargs):
        return self.TABLE

    async def get_league_player_stats(self, league_name, season, *args, **kwargs):
        return self.PLAYERS

    async def search_players(self, query):
        if query == "Erling Haaland":
            return [{"id": "8260", "player": "Erling Haaland", "team": "Manchester City"}]
        return []

    async def get_team_history(self, team_name, season, league_name="EPL"):
        return []

    async def get_team_results(self, team_name, season):
        return []

    async def get_match_shots(self, match_id):
        return {
            "h": [
                {
                    "minute": 12, "xG": "0.4", "result": "Goal",
                    "h_team": "Arsenal", "a_team": "Chelsea",
                    "situation": "OpenPlay", "shotType": "RightFoot",
                    "lastAction": "Pass", "player": "Saka", "X": 0.8, "Y": 0.3,
                },
            ],
            "a": [
                {
                    "minute": 30, "xG": "0.8", "result": "Shot",
                    "h_team": "Arsenal", "a_team": "Chelsea",
                    "situation": "OpenPlay", "shotType": "LeftFoot",
                    "lastAction": "Run", "player": "Palmer", "X": 0.2, "Y": 0.5,
                },
            ],
        }


class AnalyticsApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        app.state.analytics = AnalyticsService(client=FakeAnalyticsClient())
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    async def test_analyze_league_returns_is_lying_rows(self):
        response = await self.client.post(
            "/api/v1/analyze/league",
            json={"league_name": "EPL", "season": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("is_lying", body)
        self.assertEqual(len(body["is_lying"]["rows"]), 2)
        self.assertIn("biggest_overperformer", body["is_lying"])
        self.assertEqual(body["is_lying"]["rows"][0]["team"], "Arsenal")

    async def test_analyze_player_unknown_name_returns_422(self):
        response = await self.client.post(
            "/api/v1/analyze/player",
            json={"player_name": "Nobody Famous"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_parameters")

    async def test_analyze_player_by_name_returns_report(self):
        response = await self.client.post(
            "/api/v1/analyze/player",
            json={"player_name": "Erling Haaland"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["player"]["name"], "Erling Haaland")
        self.assertIn("radar", body)

    async def test_analyze_team_not_in_table_returns_422(self):
        response = await self.client.post(
            "/api/v1/analyze/team",
            json={"team_name": "NotReal FC"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_parameters")

    async def test_analyze_match_returns_narrative(self):
        response = await self.client.post("/api/v1/analyze/match/1234")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("narrative", body)
        self.assertIn("Arsenal", body["narrative"]["narrative"])
        self.assertIn("xG", body["narrative"])


if __name__ == "__main__":
    unittest.main()
