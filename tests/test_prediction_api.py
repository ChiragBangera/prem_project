import unittest

import httpx
import numpy as np

from app.api import app
from app.prediction_service import PredictionService


def synthetic_dates(teams=6, rounds=3, seed=5, unplayed=2):
    rng = np.random.default_rng(seed)
    strength = np.linspace(1.5, 0.5, teams)
    dates, mid = [], 1000
    for rnd in range(rounds):
        for i in range(teams):
            for j in range(teams):
                if i == j:
                    continue
                hg = int(rng.poisson(strength[i] + 0.3))
                ag = int(rng.poisson(strength[j]))
                dates.append(
                    {
                        "id": str(mid),
                        "isResult": True,
                        "h": {"title": f"Team {i}"},
                        "a": {"title": f"Team {j}"},
                        "goals": {"h": str(hg), "a": str(ag)},
                        "xG": {"h": f"{max(strength[i] + 0.3 + rng.normal(0, 0.2), 0.05):.2f}",
                               "a": f"{max(strength[j] + rng.normal(0, 0.2), 0.05):.2f}"},
                        "datetime": f"2025-01-{1 + (mid % 27):02d} 15:00:00",
                        "forecast": {"w": "45", "d": "25", "l": "30"},
                    }
                )
                mid += 1
    for k in range(unplayed):
        dates.append(
            {
                "id": str(mid + k),
                "isResult": False,
                "h": {"title": f"Team {k}"},
                "a": {"title": f"Team {k + 2}"},
                "datetime": f"2025-05-{10 + k:02d} 15:00:00",
            }
        )
    return dates


class FakePredictionClient:
    def __init__(self, dates):
        self.dates = dates

    async def get_league_data(self, league_name, season):
        return {"dates": self.dates}

    async def get_league_table(self, league_name, season):
        header = ["Team", "M", "W", "D", "L", "G", "GA", "PTS"]
        body = [[f"Team {i}", 30, 10, 10, 10, 40, 40, 40 + i] for i in range(6)]
        return [header] + body


class PredictionApiTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lifespan = app.router.lifespan_context(app)
        await self.lifespan.__aenter__()
        app.state.predictions = PredictionService(client=FakePredictionClient(synthetic_dates()))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)

    async def test_predict_match_returns_both_models(self):
        response = await self.client.post(
            "/api/v1/predict/match",
            json={"league_name": "EPL", "season": 2025, "home": "Team 0", "away": "Team 5"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["match"], {"home": "Team 0", "away": "Team 5"})
        dc = body["model"]["dixon_coles"]
        self.assertIn("p_home", dc)
        self.assertIn("scoreline_matrix", dc)
        self.assertAlmostEqual(dc["p_home"] + dc["p_draw"] + dc["p_away"], 1.0, places=3)
        elo_model = body["model"]["elo"]
        self.assertIn("ratings", elo_model)
        self.assertIn("limitations", body)

    async def test_predict_match_unknown_team_returns_422(self):
        response = await self.client.post(
            "/api/v1/predict/match",
            json={"home": "Mystery FC", "away": "Team 1"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_parameters")

    async def test_simulate_season_returns_remaining_fixture_sim(self):
        response = await self.client.post(
            "/api/v1/predict/season",
            json={"league_name": "EPL", "season": 2025, "n_sims": 300},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["n_remaining"], 2)
        self.assertEqual(body["n_sims"], 300)
        self.assertIn("expected_points", body)
        self.assertIn("Team 0", body["expected_points"])
        self.assertIn("p_relegation", body)
        self.assertEqual(sum(body["final_position_distribution"]["Team 0"]), 300)

    async def test_calibration_reports_model_comparison(self):
        response = await self.client.post(
            "/api/v1/predict/calibration",
            json={"league_name": "EPL", "season": 2025, "min_train": 30, "step": 20, "pool_leagues": False},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("dixon_coles", body["models"])
        self.assertIn("elo", body["models"])
        self.assertIn("baseline", body["models"])
        self.assertIn("xgb_poisson", body["models"])
        self.assertIn("rps", body["models"]["dixon_coles"])
        self.assertIn("best_brier_model", body)
        self.assertLessEqual(body["models"]["dixon_coles"]["brier"], 2.0)


if __name__ == "__main__":
    unittest.main()
