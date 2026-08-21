import unittest

from app.analytics import team as team_engine
from app.analytics_service import AnalyticsService


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


class Phase0UnderstatMaxuseTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_shot_profile_detail_zones_types_shares_sum_one(self):
        class Client(FakeBaseClient):
            async def get_player_data(self, player_id):
                return {
                    "groups": {
                        "situation": {
                            "2025": [
                                {"situation": "OpenPlay", "shots": 10, "goals": 2, "xG": 3.0},
                                {"situation": "SetPiece", "shots": 5, "goals": 1, "xG": 1.0},
                            ]
                        },
                        "shotZones": {
                            "2025": [
                                {"shotZones": "InsideBox", "shots": 8, "goals": 2, "xG": 2.0},
                                {"shotZones": "OutsideBox", "shots": 7, "goals": 1, "xG": 2.0},
                            ]
                        },
                        "shotTypes": {
                            "2025": [
                                {"shotTypes": "RightFoot", "shots": 6, "goals": 1, "xG": 2.0},
                                {"shotTypes": "LeftFoot", "shots": 9, "goals": 2, "xG": 2.0},
                            ]
                        },
                        "position": {
                            "2025": [
                                {"position": "FW", "games": 10, "time": 900},
                            ]
                        },
                        "season": [{"season": "2025"}],
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
        self.assertIsNotNone(detail)
        zones = detail.get("zones")
        types = detail.get("types")
        self.assertEqual(len(zones), 2)
        self.assertEqual(len(types), 2)
        # shares should sum to ~1.0
        self.assertAlmostEqual(sum(z["xG_share"] for z in zones), 1.0, places=2)
        self.assertAlmostEqual(sum(t["xG_share"] for t in types), 1.0, places=2)
        # _source forwarded
        self.assertEqual(zones[0].get("_source"), "groups.shotZones")
        self.assertEqual(types[0].get("_source"), "groups.shotTypes")
        self.assertEqual(detail["situations"][0].get("_source"), "groups.situation")
        self.assertEqual(detail["role_split"][0].get("_source"), "groups.position")

    async def test_assisted_network_top_assister(self):
        class Client(FakeBaseClient):
            async def get_player_shots(self, player_id):
                return [
                    {"minute": 10, "xG": "0.5", "result": "Goal", "situation": "OpenPlay", "shotType": "RightFoot", "lastAction": "Pass", "player": "Test Player", "X": 0.8, "Y": 0.3, "date": "2025-08-16", "h_a": "h", "season": "2025", "player_assisted": "De Bruyne"},
                    {"minute": 15, "xG": "0.4", "result": "Shot", "situation": "OpenPlay", "shotType": "LeftFoot", "lastAction": "Pass", "player": "Test Player", "X": 0.7, "Y": 0.4, "date": "2025-08-16", "h_a": "h", "season": "2025", "player_assisted": "De Bruyne"},
                    {"minute": 20, "xG": "0.3", "result": "Shot", "situation": "OpenPlay", "shotType": "Head", "lastAction": "Pass", "player": "Test Player", "X": 0.6, "Y": 0.2, "date": "2025-08-17", "h_a": "a", "season": "2025", "player_assisted": "De Bruyne"},
                    {"minute": 25, "xG": "0.2", "result": "Shot", "situation": "SetPiece", "shotType": "RightFoot", "lastAction": "Pass", "player": "Test Player", "X": 0.5, "Y": 0.5, "date": "2025-08-18", "h_a": "a", "season": "2025", "player_assisted": "Saka"},
                ]

            async def get_player_data(self, player_id):
                return {"groups": {}, "player": {"favorite_position": "FW"}}

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_player(player_name="Test Player", league_name="EPL", season=2025)
        net = result.get("assisted_network")
        self.assertIsNotNone(net)
        self.assertIn("top_assisters", net)
        top = net["top_assisters"]
        self.assertGreaterEqual(len(top), 1)
        self.assertEqual(top[0]["count"], 3)
        self.assertEqual(top[0]["assister"], "De Bruyne")
        self.assertIn("honest_note", net)

    async def test_match_rosters_and_forecast(self):
        match_id = 12345

        class Client(FakeBaseClient):
            async def get_match_shots(self, match_id_arg):
                return {
                    "h": [{"minute": 10, "xG": "0.4", "result": "Goal", "h_team": "Arsenal", "a_team": "Chelsea", "situation": "OpenPlay", "shotType": "RightFoot", "lastAction": "Pass", "player": "Saka", "X": 0.8, "Y": 0.3}],
                    "a": [{"minute": 30, "xG": "0.8", "result": "Shot", "h_team": "Arsenal", "a_team": "Chelsea", "situation": "OpenPlay", "shotType": "LeftFoot", "lastAction": "Run", "player": "Palmer", "X": 0.2, "Y": 0.5}],
                }

            async def get_match_data(self, mid):
                return {
                    "rosters": {
                        "h": {
                            "1": {"player_name": "Saka", "goals": 1, "xG": 0.6, "shots": 3, "key_passes": 2, "team_title": "Arsenal"},
                            "2": {"player_name": "Odegaard", "goals": 0, "xG": 0.2, "shots": 1, "key_passes": 1, "team_title": "Arsenal"},
                        },
                        "a": {
                            "3": {"player_name": "Palmer", "goals": 0, "xG": 0.8, "shots": 2, "key_passes": 0, "team_title": "Chelsea"},
                            "4": {"player_name": "Jackson", "goals": 0, "xG": 0.1, "shots": 1, "key_passes": 0, "team_title": "Chelsea"},
                        },
                    },
                    "shots": {"h": [], "a": []},
                }

            async def get_league_data(self, league_name, season):
                return {
                    "dates": [
                        {
                            "id": str(match_id),
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
        result = await svc.analyze_match(match_id)
        self.assertIn("rosters", result)
        rosters = result["rosters"]
        self.assertIsNotNone(rosters)
        self.assertEqual(len(rosters["h"]), 2)
        self.assertEqual(len(rosters["a"]), 2)
        self.assertIn("forecast", result)
        fc = result["forecast"]
        self.assertIsNotNone(fc)
        self.assertAlmostEqual(fc["w"], 0.42, places=2)
        self.assertEqual(fc["source"], "understat")

    async def test_metric_trends_deep_rolling_length(self):
        history = [
            {"date": f"2025-08-{10+i:02d}", "h_a": "h", "xG": 1.0, "xGA": 0.5, "scored": 1, "missed": 0, "npxGD": 0.5, "xpts": 1.0, "ppda": {"att": 100, "def": 10}, "deep": 10+i, "deep_allowed": 5+i}
            for i in range(6)
        ]
        result = team_engine.metric_trends(history, window=5)
        self.assertEqual(len(result["deep_for"]), 6)
        self.assertEqual(len(result["deep_against"]), 6)
        self.assertEqual(result["window"], 5)
        # window 5 avg: last entry should be avg of last 5 deeps: 11,12,13,14,15 => 13.0
        self.assertAlmostEqual(result["deep_for"][-1], 13.0, places=1)
        self.assertIn("dates", result)
        self.assertEqual(len(result["dates"]), 6)

    async def test_enrichment_noop(self):
        class Client(FakeBaseClient):
            async def get_player_shots(self, player_id):
                return []

            async def get_player_data(self, player_id):
                return {"groups": {}, "player": {"favorite_position": "FW"}}

        svc = AnalyticsService(client=Client())
        result = await svc.analyze_player(player_name="Test Player", league_name="EPL", season=2025)
        self.assertIn("enrichment", result)
        self.assertEqual(result["enrichment"]["source"], "none")
        self.assertIn("honest_note", result["enrichment"])
        self.assertIsNone(result["enrichment"]["fetched_at"])

    async def test_match_rounds_upcoming_grouped(self):
        class Client(FakeBaseClient):
            async def get_league_data(self, league_name, season):
                return {
                    "dates": [
                        # 2 played
                        {"id": "1", "h": {"title": "Arsenal"}, "a": {"title": "Leeds"}, "datetime": "2025-08-16 15:00:00", "isResult": True, "goals": {"h": 1, "a": 0}, "xG": {"h": 1.4, "a": 0.9}, "forecast": {"w": 0.6, "d": 0.2, "l": 0.2}},
                        {"id": "2", "h": {"title": "Chelsea"}, "a": {"title": "Arsenal"}, "datetime": "2025-08-16 15:00:00", "isResult": True, "goals": {"h": 0, "a": 0}, "xG": {"h": 0.8, "a": 0.8}, "forecast": {"w": 0.4, "d": 0.3, "l": 0.3}},
                        # 3 upcoming
                        {"id": "3", "h": {"title": "Arsenal"}, "a": {"title": "Chelsea"}, "datetime": "2025-08-23 15:00:00", "isResult": False, "goals": {"h": 0, "a": 0}, "xG": {"h": 0, "a": 0}, "forecast": {"w": 0.42, "d": 0.25, "l": 0.33}},
                        {"id": "4", "h": {"title": "Leeds"}, "a": {"title": "Chelsea"}, "datetime": "2025-08-23 15:00:00", "isResult": False, "goals": {"h": 0, "a": 0}, "xG": {"h": 0, "a": 0}, "forecast": {"w": 0.3, "d": 0.3, "l": 0.4}},
                        {"id": "5", "h": {"title": "Chelsea"}, "a": {"title": "Leeds"}, "datetime": "2025-08-30 15:00:00", "isResult": False, "goals": {"h": 0, "a": 0}, "xG": {"h": 0, "a": 0}, "forecast": {"w": 0.5, "d": 0.25, "l": 0.25}},
                    ],
                    "teams": {},
                }

        svc = AnalyticsService(client=Client())
        result = await svc.match_rounds(league_name="EPL", season=2025)
        self.assertIn("rounds", result)
        self.assertIn("upcoming_by_round", result)
        self.assertGreater(len(result["upcoming_by_round"]), 0)
        # rounds should correspond to played only (2 played but grouped by home nth -> 1 round per played?)
        # At least ensure rounds length not equal to upcoming count and unchanged logic
        self.assertEqual(result["n_played"], 2)
        # check upcoming matches have forecast attached where available
        found_forecast = False
        for rnd in result["upcoming_by_round"]:
            for m in rnd["matches"]:
                if "forecast" in m:
                    found_forecast = True
                    self.assertIn("w", m["forecast"])
        self.assertTrue(found_forecast)
