import unittest

import numpy as np

from app.ml import elo, poisson
from app.ml.engine import (
    _table_points_map,
    _understat_probs,
    build_match_rows,
    dc_input,
    elo_input,
    forecast_calibration,
)


def synthetic_league_dates(teams=8, rounds=4, home_advantage=0.35, seed=11):
    rng = np.random.default_rng(seed)
    strength = np.linspace(1.6, 0.4, teams)
    dates, mid = [], 1000
    for _ in range(rounds):
        for i in range(teams):
            for j in range(teams):
                if i == j:
                    continue
                hg = int(rng.poisson(strength[i] + home_advantage))
                ag = int(rng.poisson(strength[j]))
                dates.append(
                    {
                        "id": str(mid),
                        "isResult": True,
                        "h": {"title": f"Team {i}"},
                        "a": {"title": f"Team {j}"},
                        "goals": {"h": str(hg), "a": str(ag)},
                        "xG": {"h": f"{max(strength[i] + home_advantage + rng.normal(0, 0.2), 0.05):.2f}",
                               "a": f"{max(strength[j] + rng.normal(0, 0.2), 0.05):.2f}"},
                        "datetime": f"2025-01-{1 + (mid % 27):02d} 15:00:00",
                        "forecast": {"w": "45", "d": "25", "l": "30"},
                    }
                )
                mid += 1
    return dates


class PoissonFitTestCase(unittest.TestCase):
    def setUp(self):
        self.matches = [
            {"home": "A", "away": "B", "home_goals": 2.1, "away_goals": 0.8, "date": "2025-01-01"},
            {"home": "B", "away": "A", "home_goals": 1.0, "away_goals": 1.4, "date": "2025-01-08"},
            {"home": "A", "away": "C", "home_goals": 2.6, "away_goals": 0.6, "date": "2025-01-15"},
            {"home": "C", "away": "A", "home_goals": 0.9, "away_goals": 2.0, "date": "2025-01-22"},
            {"home": "B", "away": "C", "home_goals": 1.5, "away_goals": 1.1, "date": "2025-01-29"},
            {"home": "C", "away": "B", "home_goals": 1.2, "away_goals": 1.7, "date": "2025-02-05"},
        ] * 6
        self.model = poisson.fit_dixon_coles(self.matches)

    def test_model_structure(self):
        self.assertEqual(self.model["n_matches"], len(self.matches))
        self.assertEqual(self.model["teams"], sorted({"A", "B", "C"}))
        self.assertTrue(np.isfinite(self.model["log_likelihood"]))
        self.assertAlmostEqual(float(np.sum(self.model["attack"]) + np.sum(self.model["defense"])), 0.0, places=6)
        self.assertTrue(-0.5 <= self.model["rho"] <= 0.5)
        self.assertTrue(-0.2 <= self.model["home_advantage"] <= 1.2)

    def test_match_probabilities_normalize_and_rank(self):
        probs = poisson.match_probabilities(self.model, "A", "B")
        self.assertAlmostEqual(probs["p_home"] + probs["p_draw"] + probs["p_away"], 1.0, places=3)
        matrix = np.array(probs["scoreline_matrix"])
        self.assertAlmostEqual(float(matrix.sum()), 1.0, places=3)
        # A attacks more than B in the data
        self.assertGreater(probs["p_home"], probs["p_away"])
        self.assertEqual(len(probs["most_likely_score"]), 2)

    def test_unknown_team_raises(self):
        with self.assertRaises(ValueError):
            poisson.match_probabilities(self.model, "A", "NotATeam")

    def test_derived_market_probabilities_are_consistent(self):
        probs = poisson.match_probabilities(self.model, "A", "B")
        derived = probs["derived"]
        for line in ("1.5", "2.5", "3.5"):
            pair = derived["over_under"][line]
            self.assertAlmostEqual(pair["over"] + pair["under"], 1.0, places=3)
        self.assertTrue(0.0 <= derived["both_teams_score"] <= 1.0)
        self.assertTrue(0.0 <= derived["clean_sheet_home"] <= 1.0)
        self.assertTrue(0.0 <= derived["clean_sheet_away"] <= 1.0)

    def test_decay_weights_recent_matches(self):
        recent = [
            {"home": "A", "away": "B", "home_goals": 2.0, "away_goals": 0.8, "date": "2025-06-01"},
            {"home": "B", "away": "A", "home_goals": 1.0, "away_goals": 1.2, "date": "2025-06-08"},
        ] * 10
        old = [
            {"home": "B", "away": "A", "home_goals": 3.0, "away_goals": 0.3, "date": "2024-01-01"},
            {"home": "A", "away": "B", "home_goals": 0.5, "away_goals": 2.5, "date": "2024-01-08"},
        ] * 10
        model = poisson.fit_dixon_coles(recent + old, decay_half_life_days=60)
        probs = poisson.match_probabilities(model, "A", "B")
        self.assertGreater(probs["p_home"], probs["p_away"])


class PoissonSimulationTestCase(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(2)
        self.matches = []
        for _ in range(4):
            for i in range(6):
                for j in range(6):
                    if i == j:
                        continue
                    strength = np.linspace(1.4, 0.5, 6)
                    hg = int(rng.poisson(strength[i] + 0.3))
                    ag = int(rng.poisson(strength[j]))
                    self.matches.append(
                        {"home": f"T{i}", "away": f"T{j}", "home_goals": hg, "away_goals": ag,
                         "date": "2025-01-01"}
                    )
        self.model = poisson.fit_dixon_coles(self.matches)

    def test_simulation_consistency(self):
        fixtures = [{"home": "T0", "away": "T1"}, {"home": "T2", "away": "T3"}]
        sim = poisson.simulate_season(
            self.model, fixtures, current_points={"T0": 40, "T1": 35}, n_sims=1000, seed=7
        )
        self.assertEqual(sim["n_sims"], 1000)
        for team, counts in sim["final_position_distribution"].items():
            self.assertEqual(sum(counts), 1000)
        self.assertGreaterEqual(sim["expected_points"]["T0"], 40.0)
        self.assertAlmostEqual(sum(sim["p_top_4"].values()), sum(t < 4 for t in range(6)), places=0)

    def test_simulation_empty_fixtures(self):
        sim = poisson.simulate_season(self.model, [], n_sims=100)
        self.assertEqual(sim["n_sims"], 0)

    def test_simulation_exposes_champion_and_goal_projections(self):
        fixtures = [{"home": "T0", "away": "T1"}, {"home": "T2", "away": "T3"}]
        sim = poisson.simulate_season(self.model, fixtures, n_sims=1000, seed=7)
        self.assertAlmostEqual(sum(sim["p_champion"].values()), 1.0, places=3)
        self.assertEqual(set(sim["expected_goals_for"]), set(sim["expected_points"]))
        self.assertGreater(sim["expected_goals_for"]["T0"], 0)
        self.assertGreater(sim["expected_goals_against"]["T1"], 0)

    def test_simulated_points_match_dc_implied_expectation(self):
        probs = poisson.match_probabilities(self.model, "T0", "T5")
        expected_points = 3 * probs["p_home"] + 1 * probs["p_draw"]
        sim = poisson.simulate_season(
            self.model, [{"home": "T0", "away": "T5"}], n_sims=2000, seed=7
        )
        self.assertLess(abs(sim["expected_points"]["T0"] - expected_points), 0.15)


class EloTestCase(unittest.TestCase):
    def setUp(self):
        self.rows = build_match_rows(synthetic_league_dates(teams=8, rounds=6, seed=13))
        self.model = elo.fit_elo(elo_input(self.rows))

    def test_ratings_order_strongest_first(self):
        ratings = self.model["ratings"]
        self.assertGreater(ratings["Team 0"], ratings["Team 7"])
        self.assertGreater(ratings["Team 1"], ratings["Team 6"])

    def test_home_advantage_fitted_positive(self):
        self.assertGreater(self.model["home_advantage"], 0.0)

    def test_predict_sums_to_one_and_flips_with_venue(self):
        home_win = self.model["predict"]("Team 0", "Team 7")
        self.assertAlmostEqual(home_win["p_home"] + home_win["p_draw"] + home_win["p_away"], 1.0, places=3)
        self.assertGreater(home_win["p_home"], home_win["p_away"])
        away_win = self.model["predict"]("Team 7", "Team 0")
        self.assertGreater(away_win["p_away"], away_win["p_home"])

    def test_unknown_team_raises(self):
        with self.assertRaises(ValueError):
            self.model["predict"]("Team 0", "Mystery FC")


class EngineHelpersTestCase(unittest.TestCase):
    def test_build_match_rows_parses_understat_dates(self):
        dates = [
            {
                "id": "1", "isResult": True,
                "h": {"title": "Arsenal"}, "a": {"title": "Chelsea"},
                "goals": {"h": "3", "a": "1"}, "xG": {"h": "2.4", "a": "0.9"},
                "datetime": "2025-08-15 19:00:00",
            },
            {
                "id": "2", "isResult": False,
                "h": {"title": "Arsenal"}, "a": {"title": "Liverpool"},
                "goals": {"h": None, "a": None},
                "datetime": "2025-08-22 19:00:00",
            },
            {"id": "3", "isResult": True, "h": {"title": "Chelsea"}, "a": {"title": "Liverpool"},
             "goals": {}, "datetime": "2025-08-08 12:30:00"},
        ]
        rows = build_match_rows(dates)
        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["home_goals"], 3)
        self.assertAlmostEqual(first["home_xg"], 2.4)
        self.assertEqual(first["date"], "2025-08-15")
        self.assertTrue(first["is_result"])
        self.assertFalse(rows[1]["is_result"])
        self.assertEqual(rows[2]["home_goals"], 0)

    def test_dc_input_switches_between_xg_and_goals(self):
        rows = [
            {"home": "A", "away": "B", "home_goals": 2, "away_goals": 1,
             "home_xg": 2.7, "away_xg": 0.8, "date": "2025-01-01",
             "is_result": True, "match_id": "1", "forecast": None},
        ]
        self.assertEqual(dc_input(rows, use_xg=True)[0]["home_goals"], 2.7)
        self.assertEqual(dc_input(rows, use_xg=False)[0]["home_goals"], 2.0)

    def test_table_points_map_with_and_without_header(self):
        header = ["Team", "M", "W", "D", "L", "G", "GA", "PTS"]
        body = [["Arsenal", 30, 19, 6, 5, 55, 24, 63], ["Chelsea", 30, 12, 8, 10, 48, 40, 44]]
        self.assertEqual(_table_points_map([header] + body), {"Arsenal": 63, "Chelsea": 44})
        self.assertEqual(_table_points_map(body), {"Arsenal": 63, "Chelsea": 44})
        self.assertEqual(_table_points_map([]), {})

    def test_understat_probs_handles_percent_scale(self):
        probs = _understat_probs({"w": "45", "d": "25", "l": "30"})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=3)
        self.assertAlmostEqual(probs["p_home"], 0.45, places=2)
        fracs = _understat_probs({"w": 0.5, "d": 0.3, "l": 0.2})
        self.assertAlmostEqual(sum(fracs.values()), 1.0, places=3)
        empty = _understat_probs(None)
        self.assertAlmostEqual(sum(empty.values()), 1.0, places=3)


class FakeLeagueClient:
    def __init__(self, dates):
        self.dates = dates

    async def get_league_data(self, league_name, season):
        return {"dates": self.dates}

    async def get_league_table(self, league_name, season):
        header = ["Team", "M", "W", "D", "L", "G", "GA", "PTS"]
        body = [[f"Team {i}", 30, 10, 10, 10, 40, 40, 30 + i] for i in range(8)]
        return [header] + body


class CalibrationTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_walkforward_calibration_reports_all_models(self):
        dates = synthetic_league_dates(teams=8, rounds=5, seed=31)
        client = FakeLeagueClient(dates)
        report = await forecast_calibration(client, "EPL", 2025, min_train=40, step=6)
        self.assertEqual(report["method"], "walk-forward")
        self.assertIn("dixon_coles", report["models"])
        self.assertIn("baseline", report["models"])
        dc = report["models"]["dixon_coles"]
        self.assertGreater(dc["n"], 0)
        self.assertLessEqual(dc["brier"], 2.0)
        self.assertLessEqual(dc["accuracy"], 1.0)
        self.assertIn(report["best_brier_model"], report["models"])

    async def test_calibration_too_few_matches_raises(self):
        client = FakeLeagueClient(synthetic_league_dates(teams=4, rounds=1, seed=41))
        with self.assertRaises(ValueError):
            await forecast_calibration(client, "EPL", 2025, min_train=30)


if __name__ == "__main__":
    unittest.main()
