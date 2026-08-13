import unittest

from app.stat_data import statsbomb


def make_events():
    """Canned StatsBomb-shaped events: two touches, a pressure + recovery,
    a carry, a pass, a shot."""
    return [
        {"type": {"id": 42, "name": "Carry"}, "team": {"name": "Team A"}, "player": {"name": "P1"},
         "possession_team": {"name": "Team A"}, "minute": 1, "second": 0,
         "location": [60, 40], "carry": {"end_location": [70, 40]}},
        {"type": {"id": 30, "name": "Pass"}, "team": {"name": "Team A"}, "player": {"name": "P1"},
         "possession_team": {"name": "Team A"}, "minute": 2, "second": 0,
         "location": [80, 40], "pass": {"end_location": [100, 40], "outcome": {"name": "Complete"}}},
        {"type": {"id": 17, "name": "Pressure"}, "team": {"name": "Team B"}, "player": {"name": "P2"},
         "possession_team": {"name": "Team A"}, "minute": 3, "second": 0,
         "location": [95, 40]},
        {"type": {"id": 7, "name": "Ball Recovery"}, "team": {"name": "Team B"}, "player": {"name": "P2"},
         "possession_team": {"name": "Team B"}, "minute": 3, "second": 2,
         "location": [95, 40]},
        {"type": {"id": 16, "name": "Shot"}, "team": {"name": "Team A"}, "player": {"name": "P1"},
         "possession_team": {"name": "Team A"}, "minute": 4, "second": 0,
         "location": [105, 40], "shot": {"outcome": {"name": "Goal"}}},
    ]


class StatsBombTestCase(unittest.TestCase):
    def test_aggregate_match_team_stats(self):
        aggregates = statsbomb.aggregate_match("m1", make_events())
        self.assertIn("Team A", aggregates["teams"])
        self.assertIn("Team B", aggregates["teams"])
        team_a = aggregates["teams"]["Team A"]
        team_b = aggregates["teams"]["Team B"]
        # Team A: carry, pass, shot = 3 touches; shot at x=105 is in the opp box
        self.assertEqual(team_a["touches"], 3)
        self.assertEqual(team_a["touches_opp_box"], 1)
        self.assertEqual(team_a["carries"], 1)
        self.assertAlmostEqual(team_a["carry_distance"], 10.0, places=1)
        self.assertEqual(team_a["goals"], 1)
        self.assertEqual(team_a["passes_completed"], 1)
        # Team B: pressure + recovery = 2 touches; pressure succeeded via recovery
        self.assertEqual(team_b["touches"], 2)
        self.assertEqual(team_b["pressures"], 1)
        self.assertEqual(team_b["successful_pressures"], 1)
        self.assertEqual(team_b["ball_recoveries"], 1)

    def test_attack_direction_inference(self):
        direction = statsbomb._attack_direction(make_events())
        self.assertEqual(direction["Team A"], 1.0)  # shots at x=105 -> attacks right

    def test_player_aggregates(self):
        players = statsbomb.player_aggregates(make_events(), "Team A", 1.0)
        by_name = {p["player"]: p for p in players}
        self.assertEqual(by_name["P1"]["touches"], 3)
        self.assertEqual(by_name["P1"]["touches_opp_box"], 1)
        self.assertEqual(by_name["P1"]["carries"], 1)
        self.assertAlmostEqual(by_name["P1"]["carry_distance"], 10.0, places=1)


class StatsBombApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_competitions_and_match_flow(self):
        import httpx
        from app.api import app
        from app.statsbomb_service import StatsBombService

        original_list = statsbomb.list_competitions
        original_matches = statsbomb.list_matches
        original_events = statsbomb.get_events

        async def fake_competitions():
            return [
                {"competition_id": 11, "season_id": 90, "competition_name": "La Liga",
                 "season_name": "2020/2021", "country_name": "Spain"},
            ]

        async def fake_matches(competition_id, season_id):
            return [
                {"match_id": 303470, "date": "2021-04-10", "home": "Real Madrid",
                 "away": "Barcelona", "home_score": 2, "away_score": 1},
            ]

        async def fake_events(match_id):
            return make_events()

        statsbomb.list_competitions = fake_competitions
        statsbomb.list_matches = fake_matches
        statsbomb.get_events = fake_events
        try:
            lifespan = app.router.lifespan_context(app)
            await lifespan.__aenter__()
            app.state.statsbomb = StatsBombService()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                comps = await client.get("/api/v1/statsbomb/competitions")
                self.assertEqual(comps.status_code, 200)
                self.assertEqual(comps.json()["competitions"][0]["competition_name"], "La Liga")

                matches = await client.post("/api/v1/statsbomb/matches",
                                            json={"competition_id": 11, "season_id": 90})
                self.assertEqual(matches.status_code, 200)
                self.assertEqual(matches.json()["matches"][0]["match_id"], 303470)

                report = await client.post("/api/v1/statsbomb/match/303470")
                self.assertEqual(report.status_code, 200)
                body = report.json()
                self.assertIn("Team A", body["teams"])
                self.assertIn("player_leaderboards", body)
                self.assertIn("definitions", body)
                self.assertIn("limitations", body)
            await lifespan.__aexit__(None, None, None)
        finally:
            statsbomb.list_competitions = original_list
            statsbomb.list_matches = original_matches
            statsbomb.get_events = original_events


if __name__ == "__main__":
    unittest.main()
