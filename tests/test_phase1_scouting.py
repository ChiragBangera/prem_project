import unittest
from unittest.mock import AsyncMock, patch

from app.analytics_service import AnalyticsService


def _make_player(pid, name, team="Arsenal", position="FW", minutes=900, npxg=5, xa=2, xgchain=20, xgbuildup=10, goals=5, assists=2, shots=20, key_passes=10, xg=6, npxg_raw=None):
    return {
        "id": str(pid),
        "player_name": name,
        "team_title": team,
        "position": position,
        "time": str(minutes),
        "npxG": str(npxg),
        "xA": str(xa),
        "xGChain": str(xgchain),
        "xGBuildup": str(xgbuildup),
        "goals": str(goals),
        "assists": str(assists),
        "shots": str(shots),
        "key_passes": str(key_passes),
        "xG": str(xg),
        "npg": str(goals),
        "yellow_cards": "0",
        "red_cards": "0",
        "games": "10",
    }


class BaseFakeClient:
    TABLE = [
        ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA", "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
        ["Arsenal", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0, 9.8, 11.9, 290, 210, 60.1],
    ]

    async def get_league_table(self, *a, **kw):
        return self.TABLE

    async def get_league_player_stats(self, league_name, season, *args, **kwargs):
        return self.PLAYERS

    async def search_players(self, query):
        return []

    async def get_team_history(self, *a, **kw):
        return []

    async def get_team_results(self, *a, **kw):
        return []

    async def get_match_shots(self, *a, **kw):
        return {"h": [], "a": []}

    async def get_league_data(self, *a, **kw):
        return {"dates": [], "teams": {}}

    async def get_player_shots(self, *a, **kw):
        return []

    async def get_player_data(self, player_id):
        return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

    async def get_match_data(self, *a, **kw):
        return {"rosters": {"h": {}, "a": {}}, "shots": {"h": [], "a": []}}

    async def get_team_player_stats(self, *a, **kw):
        return []


class Phase1ScoutingTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_per90_sort_ranks_by_per90_not_totals(self):
        # A: 1800 mins npxG 6 => 0.30/90 ; B: 900 mins npxG 4 => 0.40/90
        class Client(BaseFakeClient):
            PLAYERS = [
                _make_player(1, "Player A", minutes=1800, npxg=6),
                _make_player(2, "Player B", minutes=900, npxg=4),
            ]

            async def get_player_data(self, pid):
                return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

        svc = AnalyticsService(client=Client())
        # patch birthdates to avoid Wikidata network
        with patch.object(svc, "_birthdate_map", new=AsyncMock(return_value={})):
            result_totals = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="npxG", per90_sort=False, limit=20)
            result_per90 = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="npxG", per90_sort=True, limit=20)

        names_totals = [p["name"] for p in result_totals["players"]]
        names_per90 = [p["name"] for p in result_per90["players"]]
        # totals: A (6) before B (4)
        self.assertEqual(names_totals[0], "Player A")
        self.assertEqual(names_totals[1], "Player B")
        # per90: B (0.40) before A (0.30)
        self.assertEqual(names_per90[0], "Player B")
        self.assertEqual(names_per90[1], "Player A")

    async def test_min_npxG_per90_threshold_filters(self):
        class Client(BaseFakeClient):
            PLAYERS = [
                _make_player(1, "Player A", minutes=1800, npxg=6),  # 0.30
                _make_player(2, "Player B", minutes=900, npxg=4),   # 0.40
            ]

            async def get_player_data(self, pid):
                return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

        svc = AnalyticsService(client=Client())
        with patch.object(svc, "_birthdate_map", new=AsyncMock(return_value={})):
            result = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="npxG", min_npxG_per90=0.35, per90_sort=False, limit=20)
        names = [p["name"] for p in result["players"]]
        self.assertNotIn("Player A", names)
        self.assertIn("Player B", names)
        self.assertEqual(len(names), 1)

    async def test_template_ranks_by_similarity(self):
        # template Haaland, pool 3 players; ensure similarity desc and order_by ignored
        template = _make_player(99, "Erling Haaland", minutes=1800, npxg=12, xa=1, xgchain=30, xgbuildup=10, goals=15, assists=1, shots=60, key_passes=5, xg=13)
        # candidates: clone1 very similar to template, clone2 different, clone3 somewhat
        c1 = _make_player(1, "Clone Close", minutes=1800, npxg=11, xa=1, xgchain=28, xgbuildup=9, goals=14, assists=1, shots=58, key_passes=6, xg=12)
        c2 = _make_player(2, "Far Away", minutes=1800, npxg=2, xa=8, xgchain=60, xgbuildup=40, goals=2, assists=8, shots=10, key_passes=30, xg=2)
        c3 = _make_player(3, "Mid", minutes=1800, npxg=6, xa=4, xgchain=40, xgbuildup=20, goals=6, assists=4, shots=30, key_passes=15, xg=6)

        class Client(BaseFakeClient):
            PLAYERS = [template, c1, c2, c3]

            async def search_players(self, query):
                if "haaland" in query.lower():
                    return [{"id": "99", "player": "Erling Haaland"}]
                return []

            async def get_player_data(self, pid):
                return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

        svc = AnalyticsService(client=Client())
        with patch.object(svc, "_birthdate_map", new=AsyncMock(return_value={})):
            result = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="goals", template_player_name="Erling Haaland", limit=10)
        # template meta present
        self.assertIsNotNone(result["template"])
        self.assertEqual(result["template"]["name"], "Erling Haaland")
        # similarity filled desc
        sims = [p["similarity"] for p in result["players"]]
        # all non-null
        self.assertTrue(all(s is not None for s in sims))
        self.assertEqual(sims, sorted(sims, reverse=True))
        # order_by ignored: if sorted by goals totals, Far Away would be last but similarity ranking should place Clone Close first (closest)
        self.assertEqual(result["players"][0]["name"], "Clone Close")
        # ensure similarity rounded 3
        for s in sims:
            self.assertEqual(round(s, 3), s)

    async def test_age_scatter_excludes_missing_age(self):
        class Client(BaseFakeClient):
            PLAYERS = [
                _make_player(1, "Player With Age", minutes=900, npxg=4),
                _make_player(2, "Player No Age", minutes=900, npxg=3),
                _make_player(3, "Player With Age 2", minutes=900, npxg=5),
            ]

            async def get_player_data(self, pid):
                return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

        svc = AnalyticsService(client=Client())
        # birthdate map returns one missing
        async def fake_birthdates(names, players):
            return {
                "Player With Age": "2000-01-01",
                "Player No Age": None,
                "Player With Age 2": "1998-06-15",
            }

        with patch.object(svc, "_birthdate_map", side_effect=fake_birthdates):
            result = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, limit=10)
        scatter = result["age_scatter"]
        # should exclude missing age
        scatter_names = [s["name"] for s in scatter]
        self.assertNotIn("Player No Age", scatter_names)
        self.assertIn("Player With Age", scatter_names)
        self.assertIn("Player With Age 2", scatter_names)
        self.assertEqual(len(scatter), 2)
        # check fields
        for entry in scatter:
            self.assertIn("id", entry)
            self.assertIn("age", entry)
            self.assertIn("npxG_per90", entry)
            self.assertIn("xA_per90", entry)
            self.assertIn("team", entry)
            self.assertIn("position_group", entry)

    async def test_sparkline_null_on_missing_player_data(self):
        class Client(BaseFakeClient):
            PLAYERS = [
                _make_player(1, "Player A", minutes=900, npxg=4),
                _make_player(2, "Player B", minutes=900, npxg=3),
            ]

            async def get_player_data(self, pid):
                raise RuntimeError("player_data missing")

        svc = AnalyticsService(client=Client())
        with patch.object(svc, "_birthdate_map", new=AsyncMock(return_value={})):
            result = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, limit=10)
        # still returns
        self.assertIn("players", result)
        for p in result["players"]:
            self.assertIsNone(p["sparkline"])
            self.assertIn("similarity", p)

    async def test_backward_compat_existing_call_unchanged(self):
        class Client(BaseFakeClient):
            PLAYERS = [
                _make_player(1, "Player A", minutes=1800, npxg=6),  # totals higher
                _make_player(2, "Player B", minutes=900, npxg=4),
            ]

            async def get_player_data(self, pid):
                return {"player": {"favorite_position": "FW"}, "matches": [], "groups": {}}

        svc = AnalyticsService(client=Client())
        with patch.object(svc, "_birthdate_map", new=AsyncMock(return_value={})):
            # old call without new params
            result_old = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="npxG", limit=20)
            # explicit defaults should match
            result_new = await svc.discover_players(league_name="EPL", season=2025, minimum_minutes=900, order_by="npxG", per90_sort=False, limit=20)

        self.assertEqual([p["name"] for p in result_old["players"]], [p["name"] for p in result_new["players"]])
        # check additive keys exist but old ordering unchanged
        self.assertIn("per90_sort", result_new)
        self.assertEqual(result_new["per90_sort"], False)
        self.assertIn("template", result_new)
        self.assertIsNone(result_new["template"])
        self.assertIn("age_scatter", result_new)
        for p in result_new["players"]:
            self.assertIn("similarity", p)
            self.assertIn("sparkline", p)
            self.assertIsNone(p["similarity"])
        # order should be totals desc: A before B
        self.assertEqual(result_old["players"][0]["name"], "Player A")
