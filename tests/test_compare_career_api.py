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

    async def test_compare_players_multi_basket(self):
        response = await self.client.post(
            "/api/v1/compare/players",
            json={"players": ["Player One", "Player Two", "Keeper Kev"], "league_name": "EPL", "season": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["order"], ["Player One", "Player Two", "Keeper Kev"])
        self.assertEqual(len(body["players"]), 3)
        self.assertGreater(len(body["radar_labels"]), 2)

        too_many = await self.client.post(
            "/api/v1/compare/players",
            json={"players": [f"Player {i}" for i in range(13)]},
        )
        self.assertEqual(too_many.status_code, 422)

    async def test_discover_returns_richer_metrics_and_honours_limit(self):
        response = await self.client.post(
            "/api/v1/discover/players",
            json={"league_name": "EPL", "season": 2025, "limit": 50},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("npxG_per90", body["players"][0])
        self.assertIn("goal_involvement_per90", body["players"][0])
        self.assertIn("xG_per_shot", body["players"][0])
        self.assertIn("conversion", body["players"][0])
        self.assertIn("g_minus_xg", body["players"][0])
        self.assertEqual(body["limit"], 50)

    async def test_group_from_favorite_dmc_is_midfield(self):
        from app.analytics.percentiles import group_from_favorite, position_families

        self.assertEqual(group_from_favorite("DMC"), "M")
        self.assertEqual(group_from_favorite("DML"), "M")
        self.assertEqual(group_from_favorite("MC"), "M")
        self.assertEqual(group_from_favorite("AMC"), "M")
        self.assertEqual(group_from_favorite("DC"), "D")
        self.assertEqual(group_from_favorite("DR"), "D")
        self.assertEqual(group_from_favorite("FW"), "F")
        self.assertEqual(group_from_favorite("FWR"), "F")
        self.assertEqual(group_from_favorite("GK"), "GK")
        self.assertEqual(group_from_favorite("Non"), "")
        self.assertEqual(position_families("D M S"), {"D", "M"})
        self.assertEqual(position_families("F M S"), {"F", "M"})
        self.assertEqual(position_families("GK"), {"GK"})

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

    async def test_glossary_endpoint_exposes_explanations(self):
        response = await self.client.get("/api/v1/glossary")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(len(body["groups"]), 5)
        self.assertIn("xG", body["by_key"])
        entry = body["by_key"]["xG"]
        self.assertIn("label", entry)
        self.assertIn("long", entry)
        self.assertIn("brier", body["by_key"])
        self.assertIn("champion", body["by_key"])
        self.assertIn("age", body["by_key"])
        self.assertIn("regain_xg", body["by_key"])
        self.assertIn("position_trend", body["by_key"])

    async def test_match_rounds_groups_by_home_team_match_count(self):
        class RoundsClient(FakeCompareClient):
            async def get_league_data(self, league_name, season):
                dates = []
                for i in range(4):
                    for j in range(4):
                        if i == j:
                            continue
                        dates.append({
                            "id": f"m{i}{j}", "isResult": True,
                            "h": {"title": f"T{i}"}, "a": {"title": f"T{j}"},
                            "goals": {"h": "1", "a": "0"}, "xG": {"h": "1.0", "a": "0.5"},
                            "datetime": f"2025-01-{10 + i + j:02d} 15:00:00",
                        })
                return {"dates": dates}

        app.state.analytics = AnalyticsService(client=RoundsClient())
        response = await self.client.post(
            "/api/v1/matches/rounds",
            json={"league_name": "EPL", "season": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["rounds"]), 6)
        self.assertEqual(body["rounds"][0]["round"], 1)
        total_matches = sum(len(r["matches"]) for r in body["rounds"])
        self.assertEqual(total_matches, 12)

    async def test_team_analysis_includes_position_trend_and_splits(self):
        class TeamCtxClient(FakeCompareClient):
            async def get_team_history(self, team_name, season, league_name="EPL"):
                return [
                    {"date": "2025-01-10 15:00:00", "h_a": "h", "pts": 3, "xpts": 2.4, "xG": 2.0, "xGA": 0.5,
                     "npxGD": 1.5, "scored": 2, "missed": 0, "wins": 1, "draws": 0, "loses": 0,
                     "ppda": {"att": 200, "def": 20}, "ppda_allowed": {"att": 150, "def": 15}},
                    {"date": "2025-01-17 15:00:00", "h_a": "a", "pts": 1, "xpts": 1.0, "xG": 1.0, "xGA": 1.0,
                     "npxGD": 0.0, "scored": 1, "missed": 1, "wins": 0, "draws": 1, "loses": 0,
                     "ppda": {"att": 180, "def": 30}, "ppda_allowed": {"att": 170, "def": 25}},
                    {"date": "2025-01-24 15:00:00", "h_a": "h", "pts": 0, "xpts": 0.4, "xG": 0.6, "xGA": 1.8,
                     "npxGD": -1.2, "scored": 0, "missed": 2, "wins": 0, "draws": 0, "loses": 1,
                     "ppda": {"att": 190, "def": 19}, "ppda_allowed": {"att": 160, "def": 16}},
                ]

            async def get_league_data(self, league_name, season):
                return {"teams": {"Team A": {"history": [
                    {"date": "2025-01-10 15:00:00", "pts": 3}, {"date": "2025-01-17 15:00:00", "pts": 1},
                    {"date": "2025-01-24 15:00:00", "pts": 0}]},
                    "Team B": {"history": [
                    {"date": "2025-01-10 15:00:00", "pts": 0}, {"date": "2025-01-17 15:00:00", "pts": 3},
                    {"date": "2025-01-24 15:00:00", "pts": 3}]}}}

        app.state.analytics = AnalyticsService(client=TeamCtxClient())
        response = await self.client.post(
            "/api/v1/analyze/team",
            json={"team_name": "Team A", "league_name": "EPL", "season": 2025},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["position_trend"]["matchdays"]), 3)
        self.assertEqual(body["position_trend"]["matchdays"][-1]["rank"], 2)
        self.assertIn("first_half", body["half_split"])
        self.assertIn("home", body["home_away_splits"])
        self.assertAlmostEqual(body["home_away_splits"]["home"]["points_per_game"], 1.5, places=2)
        self.assertEqual(body["luck_curve"]["final"], -0.6)
        self.assertIn("xG_for", body["metric_trends"])

    async def test_team_timeline_monthly_aggregation(self):
        async def fake_history(team_name, season, league_name="EPL"):
            return {
                "1": {"date": f"{season}-08-10 15:00:00", "xG": 2.0, "xGA": 0.5, "npxGD": 1.5,
                      "scored": 3, "missed": 1, "pts": 3, "xpts": 2.6, "wins": 1, "draws": 0, "loses": 0,
                      "ppda": {"att": 200, "def": 20}, "ppda_allowed": {"att": 150, "def": 15},
                      "deep": 10, "deep_allowed": 4, "h_a": "h"},
                "2": {"date": f"{season}-08-20 15:00:00", "xG": 1.0, "xGA": 1.0, "npxGD": 0.0,
                      "scored": 1, "missed": 1, "pts": 1, "xpts": 1.0, "wins": 0, "draws": 1, "loses": 0,
                      "ppda": {"att": 180, "def": 30}, "ppda_allowed": {"att": 170, "def": 25},
                      "deep": 5, "deep_allowed": 6, "h_a": "a"},
                "3": {"date": f"{season}-09-05 15:00:00", "xG": 0.5, "xGA": 2.0, "npxGD": -1.5,
                      "scored": 0, "missed": 2, "pts": 0, "xpts": 0.3, "wins": 0, "draws": 0, "loses": 1,
                      "ppda": {"att": 190, "def": 19}, "ppda_allowed": {"att": 160, "def": 16},
                      "deep": 3, "deep_allowed": 8, "h_a": "h"},
            }

        self.fake.get_team_history = fake_history
        response = await self.client.post(
            "/api/v1/analyze/team/timeline",
            json={"team_name": "Team A", "league_name": "EPL", "seasons": [2024, 2025]},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([s["season"] for s in body["seasons"]], [2024, 2025])
        season_2024 = body["seasons"][0]
        self.assertEqual(len(season_2024["months"]), 2)
        august = season_2024["months"][0]
        self.assertEqual(august["month"], "2024-08")
        self.assertEqual(august["matches"], 2)
        self.assertEqual(august["points"], 4)
        self.assertEqual(august["goals"], 4)
        self.assertAlmostEqual(august["xG_per_game"], 1.5, places=2)
        self.assertAlmostEqual(august["g_minus_xg"], 1.0, places=2)
        self.assertAlmostEqual(august["ppda"], 7.6, places=2)


if __name__ == "__main__":
    unittest.main()
