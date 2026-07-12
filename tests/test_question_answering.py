import asyncio
import unittest

from app.question_answering import FootballQuestionAnswerer


class FakeClient:
    async def search_players(self, query):
        if query == "Erling Haaland":
            return [{"id": "8260", "player": "Erling Haaland", "team": "Manchester City"}]
        if query == "Bukayo Saka":
            return [{"id": "8000", "player": "Bukayo Saka", "team": "Arsenal"}]
        return []

    async def get_player_data(self, player_id):
        player_map = {
            8260: {"name": "Erling Haaland", "favorite_position": "F"},
            8000: {"name": "Bukayo Saka", "favorite_position": "M"},
        }
        return {"player": player_map[player_id], "matches": [], "shots": []}

    async def get_player_matches(self, player_id):
        if player_id == 8000:
            return [
                {"id": "3", "goals": "1", "xG": "0.9", "assists": "2", "time": "88", "shots": "3", "date": "2025-01-18"},
                {"id": "4", "goals": "0", "xG": "0.4", "assists": "1", "time": "90", "shots": "2", "date": "2025-02-03"},
            ]
        return [
            {"id": "1", "goals": "1", "xG": "0.7", "assists": "0", "time": "90", "shots": "4", "date": "2025-01-15"},
            {"id": "2", "goals": "2", "xG": "1.4", "assists": "1", "time": "85", "shots": "5", "date": "2025-02-01"},
        ]

    async def get_player_grouped_stats(self, player_id):
        return {"season": []}

    async def get_player_shots(self, player_id):
        return [{"id": "s1", "date": "2025-02-01"}]

    async def get_player_matches_via_ajax(self, player_id):
        return [{"id": "1"}]

    async def get_player_last_match(self, player_id):
        return {"id": "1"}

    async def get_team_stats(self, team_name, season):
        return {
            "xG": "50.1",
            "xGA": "41.3",
            "ppda": {"att": 100, "def": 10},
            "situation": {
                "OpenPlay": {"shots": 120, "goals": 12, "xG": 18.4},
                "FromCorner": {"shots": 32, "goals": 4, "xG": 5.2},
                "SetPiece": {"shots": 18, "goals": 3, "xG": 3.6},
            },
            "shotZone": {
                "shotOboxTotal": {"shots": 70, "goals": 3, "xG": 4.1},
                "shotPenaltyArea": {"shots": 110, "goals": 15, "xG": 20.8},
                "shotSixYardBox": {"shots": 22, "goals": 7, "xG": 7.9},
            },
            "attackSpeed": {
                "Fast": {"shots": 28, "goals": 6, "xG": 6.7},
                "Normal": {"shots": 100, "goals": 9, "xG": 14.3},
                "Standard": {"shots": 54, "goals": 5, "xG": 8.2},
            },
            "timing": {
                "1-15": {"shots": 20, "goals": 2, "xG": 2.9},
                "46-60": {"shots": 34, "goals": 5, "xG": 6.1},
                "76+": {"shots": 40, "goals": 6, "xG": 6.8},
            },
        }

    async def get_team_players(self, team_name, season):
        return [{"player_name": "Player A"}]

    async def get_team_results(self, team_name, season):
        return [
            {"id": "m1", "pts": "3", "scored": "2", "missed": "0", "side": "h", "xG": {"h": "1.8", "a": "0.6"}, "shots": {"h": "16", "a": "7"}, "date": "2025-01-04"},
            {"id": "m2", "pts": "1", "scored": "1", "missed": "1", "side": "a", "xG": {"h": "1.1", "a": "1.0"}, "shots": {"h": "11", "a": "9"}, "date": "2025-01-11"},
            {"id": "m3", "pts": "3", "scored": "3", "missed": "1", "side": "h", "xG": {"h": "2.3", "a": "0.9"}, "shots": {"h": "18", "a": "8"}, "date": "2025-01-18"},
            {"id": "m4", "pts": "0", "scored": "0", "missed": "2", "side": "a", "xG": {"h": "1.7", "a": "0.8"}, "shots": {"h": "14", "a": "6"}, "date": "2025-01-25"},
            {"id": "m5", "pts": "3", "scored": "2", "missed": "1", "side": "h", "xG": {"h": "1.9", "a": "0.7"}, "shots": {"h": "15", "a": "5"}, "date": "2025-02-01"},
            {"id": "m6", "pts": "3", "scored": "2", "missed": "0", "side": "a", "xG": {"h": "0.8", "a": "1.6"}, "shots": {"h": "7", "a": "13"}, "date": "2025-02-08"},
            {"id": "m7", "pts": "1", "scored": "1", "missed": "1", "side": "h", "xG": {"h": "1.4", "a": "0.9"}, "shots": {"h": "12", "a": "8"}, "date": "2025-02-15"},
            {"id": "m8", "pts": "3", "scored": "3", "missed": "0", "side": "a", "xG": {"h": "0.5", "a": "2.1"}, "shots": {"h": "6", "a": "17"}, "date": "2025-02-22"},
            {"id": "m9", "pts": "0", "scored": "1", "missed": "2", "side": "h", "xG": {"h": "0.7", "a": "1.8"}, "shots": {"h": "8", "a": "15"}, "date": "2025-03-01"},
            {"id": "m10", "pts": "3", "scored": "2", "missed": "1", "side": "a", "xG": {"h": "1.2", "a": "1.9"}, "shots": {"h": "10", "a": "14"}, "date": "2025-03-08"},
        ]

    async def get_team_player_stats(self, team_name, season, start_date=None, end_date=None):
        return [
            {"player_name": "Bruno Fernandes", "goals": "8", "xG": "6.1", "xA": "7.9", "shots": "55", "time": "2200"},
            {"player_name": "Amad", "goals": "10", "xG": "7.4", "xA": "4.2", "shots": "40", "time": "1700"},
            {"player_name": "Rasmus Hojlund", "goals": "11", "xG": "12.5", "xA": "1.8", "shots": "44", "time": "1600"},
        ]

    async def get_league_table(self, league_name, season, start_date=None, end_date=None):
        return [
            ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA", "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
            ["Liverpool", 30, 20, 5, 5, 60, 25, 65, 58.2, 55.0, 26.1, 25.0, 30.0, 10.2, 12.4, 300, 200, 58.3],
            ["Arsenal", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0, 9.8, 11.9, 290, 210, 60.1],
            ["Manchester United", 30, 14, 7, 9, 47, 38, 49, 50.1, 47.8, 41.3, 39.9, 8.8, 11.2, 13.1, 255, 245, 48.7],
            ["Chelsea", 30, 12, 8, 10, 48, 40, 44, 50.0, 47.0, 39.0, 38.0, 9.0, 11.0, 12.8, 250, 260, 50.8],
        ]

    async def get_league_player_stats(self, league_name, season, start_date=None, end_date=None):
        return [
            {"player_name": "Erling Haaland", "team_title": "Manchester City", "goals": "22", "xG": "20.1", "xA": "4.2", "shots": "110", "time": "2400"},
            {"player_name": "Bukayo Saka", "team_title": "Arsenal", "goals": "15", "xG": "11.4", "xA": "9.4", "shots": "62", "time": "2300"},
            {"player_name": "Cole Palmer", "team_title": "Chelsea", "goals": "14", "xG": "16.2", "xA": "8.2", "shots": "95", "time": "2200"},
        ]

    async def get_league_fixtures(self, league_name, season):
        return [{"id": "f1"}]

    async def get_league_results(self, league_name, season):
        return [{"id": "r1"}]

    async def get_league_data(self, league_name, season):
        arsenal_history = [
            {"pts": 3, "scored": 2, "missed": 0},
            {"pts": 1, "scored": 1, "missed": 1},
            {"pts": 3, "scored": 3, "missed": 1},
        ]
        liverpool_history = [
            {"pts": 3, "scored": 3, "missed": 0},
            {"pts": 3, "scored": 2, "missed": 0},
            {"pts": 3, "scored": 2, "missed": 1},
        ]
        return {
            "teams": {
                "1": {"title": "Arsenal", "history": arsenal_history},
                "2": {"title": "Liverpool", "history": liverpool_history},
            }
        }

    async def get_stats(self):
        return [{"league": "EPL"}]


class QuestionAnsweringTestCase(unittest.TestCase):
    def test_player_question_resolves_search_and_builds_answer(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How good has Erling Haaland been in 2025?")
            self.assertEqual(result["plan"]["player_id"], 8260)
            self.assertEqual(result["plan"]["intent"], "player_overview")
            self.assertTrue(result["answer"]["reasons"])
            self.assertIn("goals", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_league_table_question_selects_table_endpoint(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Show me the EPL table for 2025")
            self.assertEqual(result["plan"]["intent"], "league_table")
            self.assertIn("league_table", result["plan"]["endpoints"])

        asyncio.run(run())

    def test_since_month_builds_date_range(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How good has Erling Haaland been since January 2025?")
            self.assertEqual(result["plan"]["start_date"], "2025-01-01")
            self.assertEqual(result["plan"]["end_date"], "2026-04-06")

        asyncio.run(run())

    def test_best_finisher_question_uses_ranking(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Who has been the best finisher in the EPL in 2025?")
            self.assertEqual(result["plan"]["intent"], "player_ranking")
            self.assertEqual(result["plan"]["metric"], "finishing")
            self.assertIn("goals minus xG", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_xpts_question_uses_team_gap_analysis(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Which team is overperforming xPTS most in the EPL in 2025?")
            self.assertEqual(result["plan"]["intent"], "team_xpts_gap")
            self.assertIn("xPTS", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_process_vs_results_lens(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Show the EPL process vs results lens in 2025")
            self.assertEqual(result["plan"]["intent"], "process_vs_results")
            self.assertEqual(result["template"]["name"], "process_vs_results")
            self.assertIn("Process vs results", result["answer"]["direct_answer"])
            self.assertIn("points-minus-xPTS", " ".join(result["answer"]["reasons"]))
            self.assertEqual(result["answer"]["social_ready"]["visualizations"]["card_type"], "process_vs_results_lens")
            self.assertEqual(result["answer"]["social_ready"]["visualizations"]["framework"], "custom_svg")
            self.assertEqual(result["answer"]["social_ready"]["visualizations"]["template"], "process_vs_results_lens_v1")
            self.assertEqual(result["answer"]["social_ready"]["visualizations"]["template_status"], "needs_review")

        asyncio.run(run())

    def test_player_comparison_question_resolves_two_players(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Compare Erling Haaland vs Bukayo Saka in 2025")
            self.assertEqual(result["plan"]["intent"], "player_compare")
            self.assertEqual(result["plan"]["comparison_player_id"], 8000)
            self.assertIn("vs", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_recent_form_question_uses_recent_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How has Arsenal looked over the last 5 matches in 2025?")
            self.assertEqual(result["plan"]["intent"], "team_recent_form")
            self.assertEqual(result["template"]["name"], "team_recent_form")
            self.assertIn("last 5 matches", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_position_trend_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Arsenal table position over the years compared across weeks in 2025")
            self.assertEqual(result["plan"]["intent"], "team_position_trend")
            self.assertEqual(result["template"]["name"], "team_position_trend")
            self.assertIn("weekly table-position trend", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_player_ranking_for_creativity(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Who has been Manchester United's most creative player in 2025?")
            self.assertEqual(result["plan"]["intent"], "team_player_ranking")
            self.assertEqual(result["plan"]["team_name"], "Manchester United")
            self.assertIsNone(result["plan"]["player_name"])
            self.assertEqual(result["template"]["name"], "team_player_ranking")
            self.assertIn("Bruno Fernandes", result["answer"]["direct_answer"])
            self.assertIn("xA", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_attack_defense_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How do Manchester United look in attack and defense in 2025?")
            self.assertEqual(result["plan"]["intent"], "team_attack_defense")
            self.assertEqual(result["template"]["name"], "team_attack_defense")
            self.assertIn("xG", result["answer"]["direct_answer"])
            self.assertIn("xGA", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_compare_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Compare Arsenal vs Liverpool in 2025")
            self.assertEqual(result["plan"]["intent"], "team_compare")
            self.assertEqual(result["plan"]["comparison_team_name"], "Liverpool")
            self.assertEqual(result["template"]["name"], "team_comparison")
            self.assertIn("Arsenal vs Liverpool", result["answer"]["direct_answer"])
            self.assertIn("W-D-L", " ".join(result["answer"]["reasons"]))
            visualizations = result["answer"]["social_ready"]["visualizations"]
            self.assertEqual(visualizations["framework"], "custom_svg")
            self.assertEqual(visualizations["template"], "premium_team_compare_v1")
            self.assertEqual(visualizations["template_status"], "needs_review")
            self.assertEqual(len(visualizations["teams"]), 2)

        asyncio.run(run())

    def test_recent_window_can_parse_custom_number(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How has Arsenal looked over the last 8 matches in 2025?")
            self.assertEqual(result["plan"]["metric"], "recent_8")
            self.assertEqual(result["plan"]["intent"], "team_recent_form")

        asyncio.run(run())

    def test_club_question_defaults_league_and_builds_social_payload(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Who has been Manchester United's best finisher in 2025?")
            self.assertEqual(result["plan"]["league_name"], "EPL")
            self.assertIn("x_post", result["answer"]["social_ready"])
            self.assertIn("instagram_caption", result["answer"]["social_ready"])

        asyncio.run(run())

    def test_coach_timeline_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How have Arsenal looked under Mikel Arteta in 2024?")
            self.assertEqual(result["plan"]["intent"], "coach_timeline")
            self.assertEqual(result["plan"]["coach_name"], "Mikel Arteta")
            self.assertEqual(result["template"]["name"], "coach_timeline")
            self.assertIn("under Mikel Arteta", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_carrick_coach_timeline_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("How have Manchester United looked under Michael Carrick in 2025?")
            self.assertEqual(result["plan"]["intent"], "coach_timeline")
            self.assertEqual(result["plan"]["coach_name"], "Michael Carrick")
            self.assertEqual(result["plan"]["team_name"], "Manchester United")

        asyncio.run(run())

    def test_coach_compare_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Compare Mikel Arteta vs Arne Slot in 2024")
            self.assertEqual(result["plan"]["intent"], "coach_compare")
            self.assertEqual(result["plan"]["coach_name"], "Mikel Arteta")
            self.assertEqual(result["plan"]["comparison_coach_name"], "Arne Slot")
            self.assertEqual(result["template"]["name"], "coach_comparison")
            self.assertIn("Mikel Arteta vs Arne Slot", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_defensive_trend_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("What are Arsenal's defensive trends in 2025?")
            self.assertEqual(result["plan"]["intent"], "team_defensive_trend")
            self.assertEqual(result["template"]["name"], "team_defensive_trend")
            self.assertIn("xGA", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_chance_profile_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Show Arsenal chance creation by zone and type in 2025")
            self.assertEqual(result["plan"]["intent"], "team_chance_profile")
            self.assertEqual(result["template"]["name"], "team_chance_profile")
            self.assertIn("biggest xG source", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_team_window_compare_template(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Compare Arsenal first 5 vs last 5 league matches in 2025")
            self.assertEqual(result["plan"]["intent"], "team_window_compare")
            self.assertEqual(result["template"]["name"], "team_window_comparison")
            self.assertIn("first 5 vs last 5", result["answer"]["direct_answer"])

        asyncio.run(run())

    def test_social_payload_contains_thread_carousel_and_visualization(self):
        async def run():
            answerer = FootballQuestionAnswerer(client=FakeClient())
            result = await answerer.answer("Show Arsenal chance creation by zone and type in 2025")
            social_ready = result["answer"]["social_ready"]
            self.assertIn("x_thread", social_ready)
            self.assertIn("instagram_carousel", social_ready)
            self.assertIn("visualizations", social_ready)
            self.assertEqual(social_ready["visualizations"]["framework"], "echarts")
            self.assertIn("echarts_option", social_ready["visualizations"])

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
