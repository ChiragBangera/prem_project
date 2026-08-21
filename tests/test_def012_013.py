"""Regression tests for DEF-012 (squad NameError swallowed) and DEF-013
(predict/match home_team/away_team alias contract mismatch)."""
import unittest

import numpy as np
from fastapi.testclient import TestClient

from app.analytics_service import AnalyticsService
from app.api import app
from app.prediction_service import PredictionService


# ---------------------------------------------------------------------------
# DEF-012 — analyze_team squad must be populated (round_value import)
# ---------------------------------------------------------------------------

SQUAD_TABLE = [
    ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA", "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
    ["Arsenal", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 25.0, 24.0, 30.0, 9.8, 11.9, 290, 210, 60.1],
]

SQUAD_ROWS = [
    {
        "id": "9999",
        "player_name": "Test Player",
        "team_title": "Arsenal",
        "position": "FW",
        "goals": "10",
        "xG": "9.546",
        "npxG": "9.001",
        "npg": "10",
        "assists": "2",
        "xA": "1.005",
        "shots": "30",
        "key_passes": "15",
        "xGChain": "40.129",
        "xGBuildup": "20.771",
        "time": "1800",
        "games": "20",
        "yellow_cards": "1",
        "red_cards": "0",
    },
    {
        "id": "8888",
        "player_name": "Second Player",
        "team_title": "Arsenal",
        "position": "MF",
        "goals": "4",
        "xG": "3.456",
        "npxG": "3.2",
        "npg": "4",
        "assists": "7",
        "xA": "6.111",
        "shots": "18",
        "key_passes": "33",
        "xGChain": "25.555",
        "xGBuildup": "30.994",
        "time": "2100",
        "games": "25",
        "yellow_cards": "2",
        "red_cards": "0",
    },
]


class FakeTeamClient:
    async def get_league_table(self, league_name, season, *args, **kwargs):
        return SQUAD_TABLE

    async def get_team_history(self, team_name, season, league_name="EPL"):
        return []

    async def get_team_results(self, team_name, season):
        return []

    async def get_league_data(self, league_name, season):
        return {"dates": [], "teams": {}}

    async def get_team_player_stats(self, team_name, season, *args, **kwargs):
        return [dict(row) for row in SQUAD_ROWS]


class Def012SquadTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_team_squad_populated(self):
        svc = AnalyticsService(client=FakeTeamClient())
        report = await svc.analyze_team(team_name="Arsenal", league_name="EPL", season=2025)

        squad = report["squad"]
        self.assertEqual(len(squad), 2, "squad must be populated; empty squad means the "
                                         "round_value NameError regression is back")
        first = squad[0]
        self.assertEqual(first["player_name"], "Test Player")
        # round_value path executes: unrounded inputs come back rounded to 2dp.
        self.assertEqual(first["xG"], 9.55)
        self.assertEqual(first["npxG"], 9.0)
        self.assertEqual(first["xA"], 1.0)  # 1.005 rounds via banker's rounding
        self.assertEqual(first["xGChain"], 40.13)
        self.assertEqual(first["xGBuildup"], 20.77)
        # row shape unchanged
        self.assertEqual(first["games"], 20)
        self.assertEqual(first["minutes"], 1800)
        self.assertEqual(first["goals"], 10)
        self.assertEqual(first["assists"], 2)
        self.assertEqual(squad[1]["xG"], 3.46)
        self.assertEqual(squad[1]["player_name"], "Second Player")


# ---------------------------------------------------------------------------
# DEF-013 — POST /api/v1/predict/match accepts home_team/away_team aliases
# ---------------------------------------------------------------------------

PREDICT_TEAMS = ["Arsenal", "Liverpool", "Chelsea", "Manchester City"]


def synthetic_predict_dates(rounds=4):
    """Round-robin results so Dixon-Coles/Elo/ensemble have enough fixtures
    (>= MIN_FIT_MATCHES for the fit and >= 40 for the ensemble blend)."""
    rng = np.random.default_rng(7)
    strength = {name: 1.5 - 0.3 * idx for idx, name in enumerate(PREDICT_TEAMS)}
    dates, mid = [], 5000
    for _ in range(rounds):
        for i, home in enumerate(PREDICT_TEAMS):
            for j, away in enumerate(PREDICT_TEAMS):
                if i == j:
                    continue
                hg = int(rng.poisson(strength[home] + 0.3))
                ag = int(rng.poisson(strength[away]))
                dates.append(
                    {
                        "id": str(mid),
                        "isResult": True,
                        "h": {"title": home},
                        "a": {"title": away},
                        "goals": {"h": str(hg), "a": str(ag)},
                        "xG": {"h": f"{max(hg + rng.normal(0, 0.2), 0.05):.2f}",
                               "a": f"{max(ag + rng.normal(0, 0.2), 0.05):.2f}"},
                        "datetime": f"2025-01-{1 + (mid % 27):02d} 15:00:00",
                        "forecast": {"w": "45", "d": "25", "l": "30"},
                    }
                )
                mid += 1
    return dates


class FakePredictionClient:
    def __init__(self, dates):
        self.dates = dates

    async def get_league_data(self, league_name, season):
        return {"dates": self.dates}

    async def get_league_table(self, league_name, season):
        header = ["Team", "M", "W", "D", "L", "G", "GA", "PTS"]
        body = [[name, 30, 10, 10, 10, 40, 40, 40 + idx] for idx, name in enumerate(PREDICT_TEAMS)]
        return [header] + body


class Def013PredictAliasTestCase(unittest.TestCase):
    def setUp(self):
        # predict/match only touches app.state.predictions; no lifespan needed.
        app.state.predictions = PredictionService(
            client=FakePredictionClient(synthetic_predict_dates())
        )
        self.client = TestClient(app)

    def tearDown(self):
        del app.state.predictions

    def test_predict_match_accepts_home_team_alias(self):
        response = self.client.post(
            "/api/v1/predict/match",
            json={"home_team": "Arsenal", "away_team": "Liverpool", "season": 2025},
        )
        self.assertNotEqual(
            response.status_code, 422,
            f"home_team/away_team alias rejected: {response.json()}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["match"], {"home": "Arsenal", "away": "Liverpool"})
        self.assertIn("p_home", body["model"]["dixon_coles"])
        self.assertIn("ratings", body["model"]["elo"])

    def test_predict_match_still_accepts_home(self):
        response = self.client.post(
            "/api/v1/predict/match",
            json={"home": "Arsenal", "away": "Liverpool", "season": 2025},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["match"], {"home": "Arsenal", "away": "Liverpool"})
        self.assertIn("p_home", body["model"]["dixon_coles"])

    def test_predict_match_missing_both_names_still_422(self):
        response = self.client.post(
            "/api/v1/predict/match",
            json={"season": 2025},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
