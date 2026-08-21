import unittest

from app.analytics_service import AnalyticsService, _forecast_cache, DEFAULT_SEASON


class FakeBaseClient:
    TABLE = [
        ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA", "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
        ["Arsenal", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0, 9.8, 11.9, 290, 210, 60.1],
    ]
    PLAYERS = [
        {
            "id": "9999",
            "player_name": "Test Player",
            "team_title": "Arsenal",
            "position": "FW",
            "goals": "10",
            "xG": "9.5",
            "npxG": "9.0",
            "npg": "10",
            "assists": "2",
            "xA": "1.5",
            "shots": "30",
            "key_passes": "15",
            "xGChain": "40",
            "xGBuildup": "20",
            "time": "1800",
            "games": "20",
            "yellow_cards": "1",
            "red_cards": "0",
        }
    ]

    async def get_league_player_stats(self, league_name, season, *args, **kwargs):
        return self.PLAYERS

    async def search_players(self, query):
        if query == "Test Player":
            return [{"id": "9999", "player": "Test Player", "team": "Arsenal"}]
        return []

    async def get_team_history(self, team_name, season, league_name="EPL"):
        return []

    async def get_team_results(self, team_name, season):
        return []

    async def get_match_shots(self, match_id):
        return {"h": [], "a": []}

    async def get_league_data(self, league_name, season):
        return {"dates": [], "teams": {}}

    async def get_league_table(self, league_name, season, *args, **kwargs):
        return self.TABLE

    async def get_player_data(self, player_id):
        return {"groups": {}, "player": {"favorite_position": "FW"}}

    async def get_match_data(self, match_id):
        return {"rosters": {"h": {}, "a": {}}, "shots": {"h": [], "a": []}}

    async def get_team_player_stats(self, team_name, season, *args, **kwargs):
        return []

    async def get_player_shots(self, player_id):
        return []


class Def008BoundedForecastTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        _forecast_cache.clear()

    def setUp(self):
        _forecast_cache.clear()

    async def test_analyze_match_forecast_bounded_calls_found(self):
        call_count = 0

        class Client(FakeBaseClient):
            async def get_match_shots(self, match_id_arg):
                return {
                    "h": [{"minute": 10, "xG": "0.4", "result": "Goal", "h_team": "Arsenal", "a_team": "Chelsea", "situation": "OpenPlay", "shotType": "RightFoot", "lastAction": "Pass", "player": "Saka", "X": 0.8, "Y": 0.3}],
                    "a": [{"minute": 30, "xG": "0.8", "result": "Shot", "h_team": "Arsenal", "a_team": "Chelsea", "situation": "OpenPlay", "shotType": "LeftFoot", "lastAction": "Run", "player": "Palmer", "X": 0.2, "Y": 0.5}],
                }

            async def get_match_data(self, mid):
                return {
                    "rosters": {
                        "h": {"1": {"player_name": "Saka", "goals": 1, "xG": 0.6, "shots": 3, "key_passes": 2, "team_title": "Arsenal"}},
                        "a": {"3": {"player_name": "Palmer", "goals": 0, "xG": 0.8, "shots": 2, "key_passes": 0, "team_title": "Chelsea"}},
                    },
                    "shots": {"h": [], "a": []},
                }

            async def get_league_data(self, league_name, season):
                nonlocal call_count
                call_count += 1
                return {
                    "dates": [
                        {
                            "id": "12345",
                            "h": {"title": "Arsenal"},
                            "a": {"title": "Chelsea"},
                            "datetime": "2025-08-16 15:00:00",
                            "isResult": True,
                            "goals": {"h": 1, "a": 0},
                            "xG": {"h": 1.4, "a": 0.9},
                            "forecast": {"w": 0.42, "d": 0.25, "l": 0.33},
                        }
                    ],
                    "teams": {},
                }

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_match(12345)
        self.assertEqual(result["rosters"]["h"][0]["player_name"], "Saka")
        self.assertIsNotNone(result["forecast"])
        self.assertAlmostEqual(result["forecast"]["w"], 0.42, places=2)
        self.assertLessEqual(call_count, 3, f"forecast lookup should be ≤3 calls, got {call_count} (was ~25 before fix)")

    async def test_analyze_match_forecast_bounded_when_missing(self):
        call_count = 0

        class Client(FakeBaseClient):
            async def get_match_shots(self, match_id_arg):
                return {"h": [], "a": []}

            async def get_match_data(self, mid):
                return {"rosters": {"h": {}, "a": {}}}

            async def get_league_data(self, league_name, season):
                nonlocal call_count
                call_count += 1
                return {"dates": [{"id": "99999", "forecast": {"w": 0.1, "d": 0.1, "l": 0.8}}], "teams": {}}

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_match(12345)
        self.assertIsNone(result["forecast"])
        self.assertLessEqual(call_count, 3, f"missing forecast lookup should still be ≤3 calls, got {call_count}")

    async def test_analyze_match_forecast_cache_dedup(self):
        call_count = 0

        class Client(FakeBaseClient):
            async def get_match_shots(self, match_id_arg):
                return {"h": [], "a": []}

            async def get_match_data(self, mid):
                return {"rosters": {"h": {}, "a": {}}}

            async def get_league_data(self, league_name, season):
                nonlocal call_count
                call_count += 1
                return {"dates": [{"id": "12345", "forecast": {"w": 0.42, "d": 0.25, "l": 0.33}}], "teams": {}}

        svc = AnalyticsService(client=Client())
        await svc.analyze_match(12345)
        first = call_count
        call_count = 0
        await svc.analyze_match(12345)
        # second call should hit cache => fewer fetches (0 for same league/season)
        self.assertLessEqual(call_count, first)
        self.assertLessEqual(call_count, 3)


class Def011ShotProfileFallbackTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_shot_profile_detail_has_profile_season_and_fallback_note(self):
        class Client(FakeBaseClient):
            async def get_player_data(self, player_id):
                return {
                    "groups": {
                        "situation": {"2024": [{"situation": "OpenPlay", "shots": 10, "goals": 2, "xG": 3.0}]},
                        "shotZones": {"2024": [{"shotZones": "InsideBox", "shots": 8, "goals": 2, "xG": 2.0}]},
                        "shotTypes": {"2024": [{"shotTypes": "RightFoot", "shots": 6, "goals": 1, "xG": 2.0}]},
                        "position": {"2024": [{"position": "FW", "games": 10, "time": 900}]},
                        "season": [{"season": "2024"}],
                    },
                    "player": {"favorite_position": "FW"},
                }

            async def get_player_shots(self, player_id):
                return [
                    {"minute": 10, "xG": "0.5", "result": "Goal", "situation": "OpenPlay", "shotType": "RightFoot", "lastAction": "Pass", "player": "Test Player", "X": 0.8, "Y": 0.3, "date": "2025-08-16", "h_a": "h", "season": "2025", "player_assisted": "None"},
                ]

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_player(player_name="Test Player", league_name="EPL", season=2025)
        detail = result.get("shot_profile_detail")
        self.assertIsNotNone(detail, "fallback should return 2024 detail when 2025 missing")
        self.assertIn("profile_season", detail)
        self.assertIn("requested_season", detail)
        self.assertEqual(detail["requested_season"], 2025)
        self.assertEqual(detail["profile_season"], 2024)
        self.assertTrue(detail.get("fallback") is True)
        self.assertIn("fallback", detail.get("honest_note", "").lower())
        self.assertIn("fallback", detail.get("fallback_note", "").lower())
        # zones still honest and _source forwarded
        self.assertEqual(detail["zones"][0].get("_source"), "groups.shotZones")

    async def test_shot_profile_detail_no_fallback_when_present(self):
        class Client(FakeBaseClient):
            async def get_player_data(self, player_id):
                return {
                    "groups": {
                        "situation": {"2025": [{"situation": "OpenPlay", "shots": 10, "goals": 2, "xG": 3.0}]},
                        "shotZones": {"2025": [{"shotZones": "InsideBox", "shots": 8, "goals": 2, "xG": 2.0}]},
                        "shotTypes": {"2025": [{"shotTypes": "RightFoot", "shots": 6, "goals": 1, "xG": 2.0}]},
                        "position": {"2025": [{"position": "FW", "games": 10, "time": 900}]},
                        "season": [{"season": "2025"}],
                    },
                    "player": {"favorite_position": "FW"},
                }

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_player(player_name="Test Player", league_name="EPL", season=2025)
        detail = result.get("shot_profile_detail")
        self.assertIsNotNone(detail)
        self.assertEqual(detail["profile_season"], 2025)
        self.assertEqual(detail["requested_season"], 2025)
        self.assertFalse(detail.get("fallback"))
        self.assertIn("profile_season", detail)
        self.assertIn("requested_season", detail)
