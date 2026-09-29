"""Ratings, Elo, the blended forecaster, the season simulation and calibration."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from app.analytics.table import compute_table
from app.forecast.calibrate import calibrate
from app.forecast.elo import fit_elo
from app.forecast.model import build_forecaster, fixtures_forecast, match_rows
from app.forecast.ratings import MatchRow, fit_ratings, scoreline_matrix, summarize_matrix, tau
from app.forecast.simulate import simulate_season


def synthetic_league(seed=3, n_teams=16, reps=2, home=0.25, start="2025-08-10"):
    """Matches drawn from known attack/defence strengths so recovery can be checked."""
    from datetime import date, timedelta

    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    attack = rng.normal(0, 0.28, n_teams)
    defence = rng.normal(0, 0.28, n_teams)
    rows, day = [], date.fromisoformat(start)
    for rep in range(reps):
        for h in range(n_teams):
            for a in range(n_teams):
                if h == a:
                    continue
                lam_h = math.exp(0.15 + home + attack[h] - defence[a])
                lam_a = math.exp(0.15 + attack[a] - defence[h])
                hg, ag = int(rng.poisson(lam_h)), int(rng.poisson(lam_a))
                rows.append(MatchRow(teams[h], teams[a], (day + timedelta(days=len(rows) // 8)).isoformat(), hg, ag, lam_h, lam_a))
    return teams, attack, defence, rows


# ------------------------------------------------------------------ ratings


def test_ratings_recover_true_strengths():
    teams, attack, defence, rows = synthetic_league()
    fit = fit_ratings(rows, half_life=10_000, xg_weight=0.0)  # goals only, no decay
    est = np.array([fit.attack[fit.index(t)] - fit.defence[fit.index(t)] for t in teams])
    truth = attack - defence
    assert np.corrcoef(est, truth)[0, 1] > 0.9
    assert abs(float(fit.attack.mean())) < 0.1


def test_home_advantage_estimate_is_unbiased():
    # a single 480-match sample has sd ~0.06, so judge the estimator on the average of several
    fits = [fit_ratings(synthetic_league(seed=s)[3], half_life=10_000, xg_weight=0.0).home for s in range(8)]
    assert float(np.mean(fits)) == pytest.approx(0.25, abs=0.05)


def test_xg_response_is_more_accurate_than_goals_for_the_same_matches():
    teams, attack, defence, rows = synthetic_league(seed=9, reps=1)
    truth = attack - defence

    def corr(w):
        fit = fit_ratings(rows, half_life=10_000, xg_weight=w)
        est = np.array([fit.attack[fit.index(t)] - fit.defence[fit.index(t)] for t in teams])
        return np.corrcoef(est, truth)[0, 1]

    assert corr(1.0) > corr(0.0)  # xG here is the noiseless expectation, as in real xG vs goals


def test_ridge_shrinks_thin_evidence():
    teams, _a, _d, rows = synthetic_league(reps=2)
    few = fit_ratings(rows[:40], half_life=10_000)
    many = fit_ratings(rows, half_life=10_000)
    assert np.abs(few.attack).mean() < np.abs(many.attack).mean()


def test_recent_matches_outweigh_old_ones():
    old = [MatchRow("A", "B", "2024-01-01", 4, 0, 3.5, 0.3), MatchRow("B", "A", "2024-01-08", 0, 3, 0.3, 3.0)] * 12
    new = [MatchRow("A", "B", "2025-06-01", 0, 2, 0.4, 2.0), MatchRow("B", "A", "2025-06-08", 3, 0, 2.6, 0.4)] * 12
    lam_h, lam_a = fit_ratings(old + new, half_life=90).rates("A", "B")
    assert lam_h < lam_a  # A was dominant long ago but B is better now


def test_scoreline_matrix_is_a_distribution_that_preserves_marginals():
    from app.forecast.ratings import _pmf

    lam_h, lam_a, rho = 1.6, 1.1, -0.08
    matrix = scoreline_matrix(lam_h, lam_a, rho)
    assert matrix.sum() == pytest.approx(1.0)
    assert matrix.sum(axis=1)[:4] == pytest.approx(_pmf(lam_h)[:4] / _pmf(lam_h).sum(), abs=2e-3)  # marginals kept
    assert matrix[0, 0] > _pmf(lam_h)[0] * _pmf(lam_a)[0]  # negative rho lifts 0-0 ...
    assert matrix[1, 0] < _pmf(lam_h)[1] * _pmf(lam_a)[0]  # ... and trims 1-0
    assert tau(3, 2, lam_h, lam_a, rho) == 1.0


def test_summary_markets_are_consistent():
    s = summarize_matrix(scoreline_matrix(1.8, 0.9, -0.05))
    assert s["p_home"] + s["p_draw"] + s["p_away"] == pytest.approx(1.0)
    assert s["p_home"] > s["p_away"] and s["most_likely"][0] >= s["most_likely"][1]
    assert s["over"]["1.5"] > s["over"]["2.5"] > s["over"]["3.5"]
    assert 0 < s["btts"] < 1 and s["clean_sheet_home"] > s["clean_sheet_away"]  # the stronger side keeps more clean sheets
    assert s["exp_home"] == pytest.approx(1.8, abs=0.05)


def test_unknown_team_gets_a_slightly_below_average_prior():
    _t, _a, _d, rows = synthetic_league(reps=1)
    fit = fit_ratings(rows)
    known_h, known_a = fit.rates("T00", "T01")
    new_h, _ = fit.rates("Promoted FC", "T01")
    avg_h, _ = fit.rates("T05", "T01")
    assert math.isfinite(new_h) and new_h > 0
    assert fit.evidence.get("Promoted FC", 0) == 0


# ------------------------------------------------------------------ elo


def test_elo_orders_teams_and_yields_valid_probabilities():
    rows = [MatchRow("Strong", "Weak", f"2025-09-{i + 1:02d}", 3, 0, 2, 0.5) for i in range(10)]
    rows += [MatchRow("Weak", "Strong", f"2025-10-{i + 1:02d}", 0, 2, 0.5, 2) for i in range(10)]
    elo = fit_elo(rows)
    assert elo.ratings["Strong"] > elo.ratings["Weak"]
    p = elo.probabilities("Strong", "Weak")
    assert sum(p) == pytest.approx(1.0) and p[0] > p[2]
    assert elo.home_advantage >= 0 and 0.3 <= elo.draw_share <= 1.2


def test_elo_regresses_ratings_between_seasons():
    a = [MatchRow("X", "Y", f"2024-09-{i + 1:02d}", 3, 0, 2, 0.5) for i in range(20)]
    b = [MatchRow("X", "Y", "2025-09-01", 0, 0, 1, 1)]
    same = fit_elo(a).ratings["X"]
    after_break = fit_elo(a + b).ratings["X"]
    assert after_break < same  # pulled back toward the mean at the season boundary


# ------------------------------------------------------------------ forecaster


def test_forecaster_is_coherent(demo_league_partial, demo_league):
    fc = build_forecaster(demo_league_partial, prior=demo_league)
    assert fc.used_previous_season
    home, away = "Arsenal", "Chelsea"
    p = fc.predict(home, away, understat=(0.5, 0.25, 0.25))
    assert p["p_home"] + p["p_draw"] + p["p_away"] == pytest.approx(1.0, abs=2e-3)
    matrix = np.array(p["matrix"])
    assert matrix.shape == (9, 9) and matrix.sum() == pytest.approx(1.0, abs=1e-3)
    # the displayed grid agrees with the headline probabilities
    assert np.tril(matrix, -1).sum() == pytest.approx(p["p_home"], abs=2e-3)
    assert np.trace(matrix) == pytest.approx(p["p_draw"], abs=2e-3)
    assert p["models"]["weights"] == {"ratings": 0.7, "elo": 0.3} and p["understat"]["home"] == 0.5
    assert p["expected_goals"]["home"] > 0 and len(p["top_scorelines"]) == 5


def test_stronger_side_is_favoured_home_or_away(demo_league):
    table = compute_table(demo_league)
    strong, weak = table[0]["team"], table[-1]["team"]
    fc = build_forecaster(demo_league)
    assert fc.predict(strong, weak)["p_home"] > 0.6
    assert fc.predict(weak, strong)["p_away"] > fc.predict(weak, strong)["p_home"]
    assert fc.predict(strong, weak)["p_home"] > fc.predict(weak, strong)["p_away"]  # home edge


def test_home_advantage_is_positive_and_rho_is_bounded(demo_league):
    fc = build_forecaster(demo_league)
    assert 0.05 < math.exp(fc.ratings.home) - 1 < 0.35 and -0.25 <= fc.ratings.rho <= 0.15


def test_fixture_rows_for_the_next_round(demo_league_partial, demo_league):
    fc = build_forecaster(demo_league_partial, prior=demo_league)
    rows = fixtures_forecast(fc, demo_league_partial, limit=10)
    assert 1 <= len(rows) <= 10 and rows == sorted(rows, key=lambda r: (r["dt"], r["id"]))
    for r in rows:
        assert r["p_home"] + r["p_draw"] + r["p_away"] == pytest.approx(1.0, abs=2e-3)
        assert r["understat"] and r["date"] > "2021-01-01"


def test_too_little_data_is_a_clear_error():
    with pytest.raises(ValueError, match="at least"):
        from app.data.models import LeagueSeason

        build_forecaster(LeagueSeason("EPL", 2030, {}, [], []))


def test_fit_is_fast(demo_league):
    started = time.perf_counter()
    build_forecaster(demo_league)
    assert time.perf_counter() - started < 3.0


# ------------------------------------------------------------------ simulation


def test_simulation_is_a_proper_distribution(demo_league_partial, demo_league):
    fc = build_forecaster(demo_league_partial, prior=demo_league)
    sim = simulate_season(fc, demo_league_partial, n_sims=1500)
    teams = sim["teams"]
    assert len(teams) == 20 and sim["remaining_fixtures"] > 0
    assert sum(t["p_title"] for t in teams) == pytest.approx(1.0, abs=0.01)
    assert sum(t["p_top4"] for t in teams) == pytest.approx(4.0, abs=0.05)
    assert sum(t["p_relegation"] for t in teams) == pytest.approx(3.0, abs=0.05)
    for t in teams:
        assert sum(t["distribution"]) == pytest.approx(1.0, abs=0.01)
        assert t["exp_points"] >= t["points"] and t["points_p10"] <= t["exp_points"] <= t["points_p90"] + 1
    assert sim["teams"][0]["p_title"] == max(t["p_title"] for t in teams) or sim["teams"][0]["p_top4"] > 0.5
    again = simulate_season(fc, demo_league_partial, n_sims=1500)
    assert again["teams"][0] == sim["teams"][0]  # seeded: reproducible


def test_finished_season_has_nothing_left_to_simulate(demo_league):
    fc = build_forecaster(demo_league)
    sim = simulate_season(fc, demo_league, n_sims=200)
    champion = compute_table(demo_league)[0]["team"]
    assert sim["remaining_fixtures"] == 0
    assert next(t for t in sim["teams"] if t["team"] == champion)["p_title"] == 1.0


# ------------------------------------------------------------------ calibration


def test_walk_forward_calibration_beats_the_base_rate(demo_league):
    started = time.perf_counter()
    result = calibrate(demo_league, block=10)
    assert time.perf_counter() - started < 15
    models = result["models"]
    assert set(models) >= {"ensemble", "ratings", "elo", "baseline", "understat"}
    assert result["n_scored"] > 300 and result["skill_vs_baseline"] > 0
    assert models["ensemble"]["brier"] < models["baseline"]["brier"]
    assert models["ensemble"]["rps"] < models["baseline"]["rps"]
    assert 0.35 < models["ensemble"]["accuracy"] < 0.75
    for b in result["reliability"]:
        if b["n"] >= 40:
            assert abs(b["predicted"] - b["observed"]) < 0.15  # roughly calibrated


def test_calibration_needs_enough_matches():
    from app.data.models import LeagueSeason

    with pytest.raises(ValueError, match="at least"):
        calibrate(LeagueSeason("EPL", 2030, {}, [], []))
