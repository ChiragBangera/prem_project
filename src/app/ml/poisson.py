from __future__ import annotations

"""Dixon-Coles Poisson match model, fit on per-match xG (denoised inputs).

Pure numpy reimplementation of the canonical Dixon-Coles (1997) bivariate
Poisson with the low-score correction parameter rho (adjusts the underprediction
of 0-0, 1-0, 0-1, 1-1). Attack/defense strengths are identified by sum-to-zero
constraints; home advantage is an explicit parameter. Time-decay (half-life in
days) follows the canonical recipe so recent matches weigh more.

Honest scope with Understat data: fit on xG (better predictive than goals);
no per-minute scoring timestamps at match-level, no game-state weighting.
"""

import math

import numpy as np


DC_LIMITATIONS = [
    "Poisson models assume goals arrive independently; comebacks and game-state effects are not modelled.",
    "Attack/defense strengths are identified from ~2 matches per pair of teams per season — treat single-season team ratings as noisy.",
    "The low-score correction rho has a large standard error on one season of data.",
    "Fit on xG (denoised) when use_xg is on: this predicts underlying quality, not realised goals.",
    "No injuries, suspensions, transfers, or fixture-congestion awareness.",
]


def fit_dixon_coles(
    matches: list[dict],
    home_advantage_init: float = 0.3,
    decay_half_life_days: float | None = None,
    max_iter: int = 400,
    tol: float = 1e-6,
) -> dict:
    """Fit Dixon-Coles attack/defense strengths + home advantage + rho via
    gradient ascent on the true log-likelihood.

    Net strengths (attack + defense) are pinned to zero mean, which is the
    only identifiability constraint the bivariate Poisson actually needs.

    `matches` rows: {"home", "away", "home_goals", "away_goals", "date"}.
    Returns {"teams", "attack", "defense", "home_advantage", "rho", "n_matches",
             "log_likelihood"}.
    """
    teams = sorted({m["home"] for m in matches} | {m["away"] for m in matches})
    idx = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    M = len(matches)

    h_idx = np.array([idx[m["home"]] for m in matches], dtype=int)
    a_idx = np.array([idx[m["away"]] for m in matches], dtype=int)
    hg = np.array([float(m["home_goals"]) for m in matches], dtype=float)
    ag = np.array([float(m["away_goals"]) for m in matches], dtype=float)

    latest = max(_to_ord(m.get("date", "2025-01-01")) for m in matches)
    if decay_half_life_days is not None:
        weights = np.array(
            [2 ** (-max(0.0, latest - _to_ord(m.get("date", "2025-01-01"))) / decay_half_life_days) for m in matches],
            dtype=float,
        )
    else:
        weights = np.ones(M)

    attack = np.zeros(n)
    defense = np.zeros(n)
    home = home_advantage_init
    rho = -0.05

    # Precompute everything that does not change across iterations:
    # one-hot team membership, low-score masks, and score factorial terms.
    team_axis = np.arange(n)[:, None]
    home_of = h_idx[None, :] == team_axis
    away_of = a_idx[None, :] == team_axis
    m00 = (hg == 0) & (ag == 0)
    m10 = (hg == 1) & (ag == 0)
    m01 = (hg == 0) & (ag == 1)
    m11 = (hg == 1) & (ag == 1)
    low_00_11 = m00 | m11
    low_10_01 = m10 | m01
    log_fact_h = _log_factorials(hg)
    log_fact_a = _log_factorials(ag)

    ll_prev = -math.inf
    for iteration in range(max_iter):
        lam_h = np.clip(np.exp(attack[h_idx] - defense[a_idx] + home), 1e-9, None)
        lam_a = np.clip(np.exp(attack[a_idx] - defense[h_idx]), 1e-9, None)

        # Dixon-Coles likelihood correction tau(hg, ag) for low scores.
        # Note: tau depends only on rho, NOT on the lambdas, so its derivative
        # only enters the rho gradient (the lambda gradients are exactly those
        # of the plain bivariate Poisson).
        tau = np.ones(M)
        tau[low_00_11] = 1 - rho
        tau[low_10_01] = 1 + rho

        log_pois_h = -lam_h + hg * np.log(lam_h) - log_fact_h
        log_pois_a = -lam_a + ag * np.log(lam_a) - log_fact_a
        ll = float(np.sum(weights * (log_pois_h + log_pois_a + np.log(np.clip(tau, 1e-9, None)))))

        # d/d lambda (log poisson(k)) = (k/lambda - 1).
        w_g_h = weights * (hg - lam_h)
        w_g_a = weights * (ag - lam_a)

        # Gradients (first-order conditions of the true log-likelihood):
        # lam_h = exp(attack_h - defense_a + home) -> d ll/d attack_h = w*(hg - lam_h),
        #                                          -> d ll/d defense_a = w*(lam_h - hg).
        grad_attack = (home_of * w_g_h).sum(axis=1) + (away_of * w_g_a).sum(axis=1)
        grad_defense = -(away_of * w_g_h).sum(axis=1) - (home_of * w_g_a).sum(axis=1)
        grad_home = float(np.sum(w_g_h))

        # rho gradient: d/d rho log(tau) = -1/(1-rho) at 0-0 / 1-1, +1/(1+rho) at 1-0 / 0-1.
        dlogtau_drho = np.zeros(M)
        dlogtau_drho[low_00_11] = -1.0 / max(1 - rho, 1e-9)
        dlogtau_drho[low_10_01] = 1.0 / max(1 + rho, 1e-9)
        grad_rho = float(np.sum(weights * dlogtau_drho))

        # Diagonally-damped Fisher scoring (Poisson IRLS): step = grad / info,
        # where info for attack_i is the expected negative curvature sum of lambdas.
        # This keeps every step finite and monotone-ish even from a bad start,
        # unlike plain gradient ascent which diverges on this exponential family.
        info_attack = (home_of * (weights * lam_h)).sum(axis=1) + (away_of * (weights * lam_a)).sum(axis=1)
        info_defense = (away_of * (weights * lam_h)).sum(axis=1) + (home_of * (weights * lam_a)).sum(axis=1)
        info_home = float(np.sum(weights * lam_h))
        info_rho = float(np.sum(weights * dlogtau_drho ** 2))

        max_step = 0.5
        attack += np.clip(grad_attack / np.maximum(info_attack, 1e-9), -max_step, max_step)
        defense += np.clip(grad_defense / np.maximum(info_defense, 1e-9), -max_step, max_step)
        home += np.clip(0.5 * grad_home / max(info_home, 1e-9), -max_step, max_step)
        home = max(min(home, 1.2), -0.2)
        rho += np.clip(0.5 * grad_rho / max(info_rho, 1e-9), -max_step, max_step)
        rho = max(min(rho, 0.5), -0.5)

        # Identifiability: the lambdas are invariant to a common shift of all
        # attack and defense values, so pin the net strengths (attack+defense)
        # to zero mean. This projection preserves the lambdas exactly, which
        # keeps the optimization free of the limit cycles that separate
        # sum-to-zero pins on each array would cause.
        shift = float((attack.mean() + defense.mean()) / 2.0)
        attack -= shift
        defense -= shift

        if abs(ll - ll_prev) < tol:
            break
        ll_prev = ll

    return {
        "teams": teams,
        "attack": attack,
        "defense": defense,
        "home_advantage": float(home),
        "rho": float(rho),
        "n_matches": M,
        "log_likelihood": float(ll),
    }


def match_probabilities(model: dict, home: str, away: str, max_goals: int = 8) -> dict:
    """Predict win/draw/loss probabilities + most-likely scoreline from the fitted model."""
    teams = model["teams"]
    if home not in teams or away not in teams:
        raise ValueError(f"Both '{home}' and '{away}' must be teams in the fitted model.")
    i = teams.index(home)
    j = teams.index(away)
    lam_h = math.exp(float(model["attack"][i] - model["defense"][j] + model["home_advantage"]))
    lam_a = math.exp(float(model["attack"][j] - model["defense"][i]))
    return outcome_probs_from_lambdas(lam_h, lam_a, model["rho"], max_goals=max_goals)


def outcome_probs_from_lambdas(lam_h: float, lam_a: float, rho: float, max_goals: int = 8) -> dict:
    """Win/draw/loss + scoreline matrix for arbitrary expected goals (no team names)."""
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for h_ in range(max_goals + 1):
        for a_ in range(max_goals + 1):
            base = _poisson(h_, lam_h) * _poisson(a_, lam_a)
            if h_ == 0 and a_ == 0:
                base *= (1 - rho)
            elif (h_ == 1 and a_ == 0) or (h_ == 0 and a_ == 1):
                base *= (1 + rho)
            elif h_ == 1 and a_ == 1:
                base *= (1 - rho)
            matrix[h_, a_] = base
    matrix /= matrix.sum()

    p_home = float(np.tril(matrix, -1).sum())
    p_draw = float(np.trace(matrix))
    p_away = float(np.triu(matrix, 1).sum())
    flat = int(np.argmax(matrix))
    best_h, best_a = flat // (max_goals + 1), flat % (max_goals + 1)
    return {
        "lambda_home": round(lam_h, 3),
        "lambda_away": round(lam_a, 3),
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
        "most_likely_score": [int(best_h), int(best_a)],
        "most_likely_score_prob": round(float(matrix[best_h, best_a]), 4),
        "scoreline_matrix": matrix.tolist(),
        "derived": _derived_market_probs(matrix),
    }


def _derived_market_probs(matrix: np.ndarray) -> dict:
    """Over/under, both-teams-score, and clean-sheet probabilities from the matrix."""
    max_goals = matrix.shape[0] - 1
    p_under = {line: 0.0 for line in (1.5, 2.5, 3.5)}
    p_over = dict(p_under)
    p_btts = 0.0
    p_home_cs = 0.0
    p_away_cs = 0.0
    for h_ in range(max_goals + 1):
        for a_ in range(max_goals + 1):
            prob = float(matrix[h_, a_])
            total = h_ + a_
            for line in p_under:
                if total < line:
                    p_under[line] += prob
                else:
                    p_over[line] += prob
            if h_ >= 1 and a_ >= 1:
                p_btts += prob
            if a_ == 0:
                p_home_cs += prob
            if h_ == 0:
                p_away_cs += prob
    return {
        "over_under": {
            str(line): {
                "over": round(p_over[line], 4),
                "under": round(p_under[line], 4),
            }
            for line in (1.5, 2.5, 3.5)
        },
        "both_teams_score": round(p_btts, 4),
        "clean_sheet_home": round(p_home_cs, 4),
        "clean_sheet_away": round(p_away_cs, 4),
    }


def simulate_season(model, fixtures, current_points=None, n_sims=5000, seed=7):
    """Monte-Carlo simulate the rest of a season. See module docstring.

    `fixtures`: [{"home","away"}]; `current_points` already-banked points.
    Returns P(team finishes position k) + aggregated xPTS per team.
    """
    rng = np.random.default_rng(seed)
    teams = model["teams"]
    idx = {team: k for k, team in enumerate(teams)}
    fixed = current_points or {}
    n_fix = len(fixtures)
    if n_fix == 0:
        return _empty_result(teams, fixed)

    lh = np.zeros(n_fix)
    la = np.zeros(n_fix)
    home_idx = np.full(n_fix, -1, dtype=int)
    away_idx = np.full(n_fix, -1, dtype=int)
    for k, f in enumerate(fixtures):
        if f["home"] in idx and f["away"] in idx:
            i, j = idx[f["home"]], idx[f["away"]]
            lh[k] = math.exp(float(model["attack"][i] - model["defense"][j] + model["home_advantage"]))
            la[k] = math.exp(float(model["attack"][j] - model["defense"][i]))
            home_idx[k] = i
            away_idx[k] = j

    # vectorized across simulations, sampling the DC-renormalized joint
    # (proposal = independent Poissons, accept per cell with prob tau / tau_max
    # so the low-score correction matches the fitted model; cells are redrawn
    # until individually accepted — expected ~1.4 passes total)
    tau_max = 1.0 + abs(model["rho"])
    h_goals = np.clip(rng.poisson(lh[:, None], size=(n_fix, n_sims)), 0, 10)
    a_goals = np.clip(rng.poisson(la[:, None], size=(n_fix, n_sims)), 0, 10)
    accepted = np.zeros((n_fix, n_sims), dtype=bool)
    while not accepted.all():
        rows, cols = np.where(~accepted)
        th = np.clip(rng.poisson(lh[rows], size=len(rows)), 0, 10)
        ta = np.clip(rng.poisson(la[rows], size=len(rows)), 0, 10)
        tau_cell = np.ones(len(rows))
        m00 = (th == 0) & (ta == 0)
        m11 = (th == 1) & (ta == 1)
        m10 = (th == 1) & (ta == 0)
        m01 = (th == 0) & (ta == 1)
        tau_cell[m00 | m11] = 1 - model["rho"]
        tau_cell[m10 | m01] = 1 + model["rho"]
        keep = rng.random(len(rows)) <= tau_cell / tau_max
        h_goals[rows[keep], cols[keep]] = th[keep]
        a_goals[rows[keep], cols[keep]] = ta[keep]
        accepted[rows[keep], cols[keep]] = True

    points = np.zeros((len(teams), n_sims), dtype=int)
    goals_for = np.zeros((len(teams), n_sims), dtype=float)
    goals_against = np.zeros((len(teams), n_sims), dtype=float)
    for i, team in enumerate(teams):
        if team in fixed:
            points[i] += int(fixed[team])

    h_win = h_goals > a_goals
    draw = h_goals == a_goals
    a_win = a_goals > h_goals
    # Encountered fixtures have known teams (we filtered above)
    valid = home_idx >= 0
    if valid.any():
        h_idx_v = home_idx[valid]
        a_idx_v = away_idx[valid]
        for sim in range(n_sims):
            wins = h_win[valid, sim]
            draws = draw[valid, sim]
            np.add.at(points[:, sim], h_idx_v[wins], 3)
            np.add.at(points[:, sim], h_idx_v[draws], 1)
            np.add.at(points[:, sim], a_idx_v[draws], 1)
            np.add.at(points[:, sim], a_idx_v[~(wins | draws)], 3)
            np.add.at(goals_for[:, sim], h_idx_v, h_goals[valid, sim])
            np.add.at(goals_against[:, sim], h_idx_v, a_goals[valid, sim])
            np.add.at(goals_for[:, sim], a_idx_v, a_goals[valid, sim])
            np.add.at(goals_against[:, sim], a_idx_v, h_goals[valid, sim])

    # final positions per sim: rank descending by points, ties broken alphabetically
    n_teams = len(teams)
    final = points  # (n_teams, n_sims)
    # deterministic alphabetic tiebreak: add tiny noise by team index
    tiebreak = np.linspace(0, 1e-6, n_teams)[:, None] * np.sign(np.arange(n_teams)[:, None] - n_teams / 2)
    sort_keys = final - tiebreak
    order = np.argsort(-sort_keys, axis=0, kind="stable")
    ranks = np.empty_like(order)
    rows = np.arange(n_sims)[None, :]
    ranks[order, rows] = np.broadcast_to(np.arange(1, n_teams + 1)[:, None], (n_teams, n_sims))

    p_top4 = {}
    p_releg = {}
    xpts = {}
    expected_goals_for = {}
    expected_goals_against = {}
    rank_counts = {team: np.zeros(n_teams, dtype=int) for team in teams}
    for i, team in enumerate(teams):
        r = ranks[i]
        for pos in r:
            rank_counts[team][int(pos) - 1] += 1
        p_top4[team] = float(np.mean(r <= 4))
        p_releg[team] = float(np.mean(r >= n_teams - 2))
        xpts[team] = round(float(final[i].mean()), 2)
        expected_goals_for[team] = round(float(goals_for[i].mean()), 1)
        expected_goals_against[team] = round(float(goals_against[i].mean()), 1)

    sort_order = sorted(teams, key=lambda t: -xpts[t])
    champion = {
        t: round(float(np.mean(ranks[i] == 1)), 4)
        for i, t in enumerate(teams)
    }
    return {
        "n_sims": n_sims,
        "expected_points": {t: xpts[t] for t in sort_order},
        "expected_goals_for": {t: expected_goals_for[t] for t in sort_order},
        "expected_goals_against": {t: expected_goals_against[t] for t in sort_order},
        "p_champion": {t: champion[t] for t in sort_order},
        "p_top_4": {t: round(p_top4[t], 4) for t in sort_order},
        "p_relegation": {t: round(p_releg[t], 4) for t in sort_order},
        "final_position_distribution": {
            t: [int(rank_counts[t][k]) for k in range(n_teams)] for t in sort_order
        },
        "interpretation": (
            f"Monte-Carlo expected points and top-4/relegation probabilities from a Dixon-Coles "
            f"bivariate Poisson fit on xG across {model.get('n_matches', 0)} matches. {n_sims} simulations."
        ),
        "limitations": [
            "Poisson assumes independent scoring; no time-of-goal or game-state structure.",
            "Silent on injuries, suspensions, and short-term form shifts.",
            "Tiebreakers are ignored (points only; alphabetic fallback in sim).",
            "Fit on xG (denoised) — differs from a goals-fit Poisson, which overweights luck.",
        ],
    }


def _poisson(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return float(np.exp(-lam) * (lam ** k) / math.factorial(int(k)))


def _log_factorials(values):
    sizes = np.clip(values.astype(int), 0, 20)
    factors = np.array([math.lgamma(s + 1) for s in sizes])
    return factors


def _to_ord(date_str: str) -> float:
    try:
        y, m, d = map(int, (date_str or "2025-01-01").split("-")[:3])
        return float(y * 365 + m * 30 + d)
    except (ValueError, AttributeError):
        return 0.0


def _empty_result(teams, current_points):
    return {
        "n_sims": 0,
        "expected_points": {t: int(current_points.get(t, 0)) for t in teams},
        "p_top_4": {}, "p_relegation": {}, "final_position_distribution": {},
        "interpretation": "No remaining fixtures to simulate.", "limitations": [],
    }
