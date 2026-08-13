import unittest

import httpx

from app.api import app
from app.analytics_service import AnalyticsService


LEAGUE_PLAYERS = [
    {
        "id": "1", "player_name": "Player One", "team_title": "Team A", "position": "F",
        "games": "30", "time": "2400", "goals": "20", "xG": "18.2", "npxG": "17.0",
        "assists": "5", "xA": "4.4", "shots": "90", "key_passes": "30",
        "xGChain": "80", "xGBuildup": "30",
    },
    {
        "id": "2", "player_name": "Player Two", "team_title": "Team B", "position": "F",
        "games": "28", "time": "2200", "goals": "15", "xG": "16.1", "npxG": "14.2",
        "assists": "7", "xA": "6.1", "shots": "75", "key_passes": "40",
        "xGChain": "75", "xGBuildup": "25",
    },
    {
        "id": "3", "player_name": "Keeper Kev", "team_title": "Team A", "position": "GK",
        "games": "30", "time": "2700", "goals": "0", "xG": "0", "npxG": "0",
        "assists": "0", "xA": "0", "shots": "0", "key_passes": "0",
        "xGChain": "5", "xGBuildup": "8",
    },
]

TABLE = [
    ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA",
     "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
    ["Team A", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0,
     9.8, 11.9, 290, 210, 60.1],
    ["Team B", 30, 12, 8, 10, 48, 40, 44, 50.0, 47.0, 39.0, 38.0, 9.0,
     11.0, 12.8, 250, 260, 50.8],
]


class FakeCompareClient:
    def __init__(self):
        self.league_player_stats_calls = []
        self.league_table_calls = []

    async def get_league_player_stats(self, league_name, season, start_date=None, end_date=None):
        self.league_player_stats_calls.append((league_name, season, start_date, end_date))
        return LEAGUE_PLAYERS

    async def get_league_table(self, league_name, season, start_date=None, end_date=None):
        self.league_table_calls.append((league_name, season, start_date, end_date))
        return TABLE

    async def search_players(self, query):
        name = query.lower()
        if "one" in name:
            return [{"id": "1", "player": "Player One", "team": "Team A"}]
        if "two" in name:
            return [{"id": "2", "player": "Player Two", "team": "Team B"}]
        if "keeper" in name or "kev" in name:
            return [{"id": "3", "player": "Keeper Kev", "team": "Team A"}]
        return []

    async def get_team_history(self, team_name, season, league_name="EPL"):
        return []

    async def get_league_data(self, league_name, season):
        return {
            "dates": [
                {"id": "101", "isResult": True, "datetime": "2025-01-10 15:00:00",
                 "h": {"title": "Team A"}, "a": {"title": "Team B"},
                 "goals": {"h": "2", "a": "1"}, "xG": {"h": "1.8", "a": "0.9"}},
                {"id": "102", "isResult": False, "datetime": "2026-05-20 15:00:00",
                 "h": {"title": "Team B"}, "a": {"title": "Team A"},
                 "goals": {}, "xG": {}},
            ]
        }


class CareerTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        self.fake = FakeCompareClient()
        app.state.analytics = AnalyticsService(client=self.fake)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    async def test_career_returns_season_rows_and_absent_seasons(self):
        response = await self.client.post(
            "/api/v1/analyze/player/career",
            json={"player_name": "Keeper Kev", "league_name": "EPL", "seasons": [2023, 2024]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["n_seasons_present"], 2)
        self.assertEqual(len(body["seasons"]), 2)
        self.assertTrue(all(row["present"] for row in body["seasons"]))
        self.assertIn("xGChain_per90", body["seasons"][0])

    async def test_career_season_end_default_window(self):
        response = await self.client.post(
            "/api/v1/analyze/player/career",
            json={"player_name": "Player One", "league_name": "EPL", "season_end": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["seasons"]), 6)
        self.assertEqual(body["seasons"][0]["season"], 2020)
        self.assertEqual(body["seasons"][-1]["season"], 2025)

    async def test_career_unknown_player_returns_422(self):
        response = await self.client.post(
            "/api/v1/analyze/player/career",
            json={"player_name": "Nobody Real"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_parameters")

    async def test_compare_players_returns_shared_pool_and_aligned_radar(self):
        response = await self.client.post(
            "/api/v1/compare/players",
            json={"player_1": "Player One", "player_2": "Player Two"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["pool_size"], 3)
        self.assertIn("Player One", body["players"])
        self.assertIn("Player Two", body["players"])
        self.assertGreater(len(body["radar_labels"]), 2)
        first = body["players"]["Player One"]["radar"]["profile"]
        second = body["players"]["Player Two"]["radar"]["profile"]
        self.assertEqual([p["label"] for p in first], [p["label"] for p in second])

    async def test_compare_players_unknown_returns_422(self):
        response = await self.client.post(
            "/api/v1/compare/players",
            json={"player_1": "Player One", "player_2": "Mystery Man"},
        )

        self.assertEqual(response.status_code, 422)

    async def test_compare_teams_returns_styles_and_meetings(self):
        response = await self.client.post(
            "/api/v1/compare/teams",
            json={"team_1": "Team A", "team_2": "Team B", "league_name": "EPL", "season": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("xG_per_game", body["team_1"]["report"]["style"])
        self.assertEqual(len(body["head_to_head"]), 2)
        played = [m for m in body["head_to_head"] if m["played"]]
        self.assertEqual(played[0]["home_goals"], 2)
        self.assertEqual(played[0]["away_goals"], 1)

    async def test_date_window_passed_through_and_validated(self):
        await self.client.post(
            "/api/v1/compare/players",
            json={"player_1": "Player One", "player_2": "Player Two",
                  "start_date": "2026-01-01", "end_date": "2026-05-31"},
        )
        _, _, start, end = self.fake.league_player_stats_calls[-1]
        self.assertEqual(start, "2026-01-01")
        self.assertEqual(end, "2026-05-31")

        bad = await self.client.post(
            "/api/v1/analyze/league",
            json={"league_name": "EPL", "season": 2025,
                  "start_date": "2026-05-31", "end_date": "2026-01-01"},
        )
        self.assertEqual(bad.status_code, 422)

        ok = await self.client.post(
            "/api/v1/analyze/league",
            json={"league_name": "EPL", "season": 2025, "start_date": "2026-04-01"},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["date_window"], {"start_date": "2026-04-01", "end_date": None})
        _, _, start, end = self.fake.league_table_calls[-1]
        self.assertEqual((start, end), ("2026-04-01", None))


if __name__ == "__main__":
    unittest.main()
