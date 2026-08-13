from __future__ import annotations

"""Elo ratings for results-based win/draw/loss forecasts.

A deliberately simple counterpoint to the Dixon-Coles engine: Elo tracks only
results (W/D/L), so it makes no claims about scorelines or goals. Home
advantage (rating points) and the draw-share constant are fitted on the
training set by Brier minimization, which keeps the forecast honest rather
than borrowing hand-tuned constants.

Honest scope: ratings are fit sequentially over dated matches and never know
about match context beyond the final result; no xG, no injuries, no form
decay beyond what Elo's built-in update provides.
"""

import numpy as np

DRAW_SHARE_GRID = (0.2, 0.85, 14)
HOME_ADVANTAGE_GRID = (0.0, 180.0, 13)


def expected_share(rating: float, opponent_rating: float) -> float:
    """Expected points-share of `rating` against `opponent_rating` (0..1)."""
    return 1.0 / (1.0 + 10.0 ** ((opponent_rating - rating) / 400.0))


def fit_elo(
    matches: list[dict],
    k: float = 24.0,
    initial_rating: float = 1500.0,
    home_advantage: float | None = None,
    draw_share: float | None = None,
) -> dict:
    """Fit sequential Elo ratings over dated matches.

    `matches` rows: {"home", "away", "home_goals", "away_goals", "date"}.

    If home_advantage / draw_share are None they are fitted by Brier-grid over
    the training matches. Returns a dict with "ratings", fitted constants, and
    a "predict(home, away)" callable returning win/draw/loss probabilities.
    """
    ordered = sorted(matches, key=lambda m: (m.get("date") or "", m.get("home") or ""))
    ratings: dict[str, float] = {}
    home_seq: list[int] = []
    away_seq: list[int] = []
    score_seq: list[float] = []
    team_list: list[str] = []
    team_index: dict[str, int] = {}
    for m in ordered:
        home, away = m["home"], m["away"]
        if home not in team_index:
            team_index[home] = len(team_list)
            team_list.append(home)
        if away not in team_index:
            team_index[away] = len(team_list)
            team_list.append(away)
        rh = ratings.get(home, initial_rating)
        ra = ratings.get(away, initial_rating)
        hg, ag = int(m.get("home_goals", 0)), int(m.get("away_goals", 0))
        score = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        home_seq.append(team_index[home])
        away_seq.append(team_index[away])
        score_seq.append(score)
        e = expected_share(rh, ra)
        delta = k * (score - e)
        ratings[home] = rh + delta
        ratings[away] = ra - delta

    rating_vec = np.array([ratings.get(team, initial_rating) for team in team_list], dtype=float)
    home_arr = np.array(home_seq, dtype=int)
    away_arr = np.array(away_seq, dtype=int)
    score_arr = np.array(score_seq, dtype=float)

    def brier_for(ha: float, ds: float) -> float:
        return _brier_arrays(home_arr, away_arr, score_arr, rating_vec, ha, ds)

    ha = home_advantage if home_advantage is not None else _fit_home_advantage(brier_for)
    ds = draw_share if draw_share is not None else _fit_draw_share(brier_for, ha)

    def predict(home: str, away: str) -> dict:
        if home not in ratings or away not in ratings:
            raise ValueError(f"Both '{home}' and '{away}' must be teams in the fitted Elo ratings.")
        s = expected_share(ratings[home] + ha, ratings[away])
        p_draw = min(ds * 4.0 * s * (1.0 - s), 1.0)
        p_home = max(0.0, s - p_draw / 2.0)
        p_away = max(0.0, 1.0 - s - p_draw / 2.0)
        total = p_home + p_draw + p_away
        return {
            "home": home,
            "away": away,
            "p_home": round(p_home / total, 4),
            "p_draw": round(p_draw / total, 4),
            "p_away": round(p_away / total, 4),
        }

    train_brier = brier_for(ha, ds) if len(ordered) else None
    return {
        "ratings": {team: round(rating, 2) for team, rating in sorted(ratings.items(), key=lambda kv: -kv[1])},
        "home_advantage": round(ha, 2),
        "draw_share": round(ds, 3),
        "k": k,
        "n_matches": len(ordered),
        "train_brier": round(train_brier, 4) if train_brier is not None else None,
        "predict": predict,
    }


def _brier_arrays(home_arr, away_arr, score_arr, rating_vec, ha: float, ds: float) -> float:
    rh = rating_vec[home_arr] + ha
    ra = rating_vec[away_arr]
    s = 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))
    pd = np.minimum(ds * 4.0 * s * (1.0 - s), 1.0)
    ph = np.maximum(0.0, s - pd / 2.0)
    pa = np.maximum(0.0, 1.0 - s - pd / 2.0)
    total = ph + pd + pa
    ph = ph / total
    pd = pd / total
    pa = pa / total
    th = (score_arr == 1.0).astype(float)
    td = (score_arr == 0.5).astype(float)
    ta = (score_arr == 0.0).astype(float)
    return float(np.mean((ph - th) ** 2 + (pd - td) ** 2 + (pa - ta) ** 2))


def _fit_home_advantage(brier_for) -> float:
    ds = 0.5
    best, best_brier = 0.0, float("inf")
    for ha in np.linspace(*HOME_ADVANTAGE_GRID):
        value = brier_for(float(ha), ds)
        if value < best_brier:
            best, best_brier = float(ha), value
    return best


def _fit_draw_share(brier_for, ha: float) -> float:
    best, best_brier = 0.5, float("inf")
    for ds in np.linspace(*DRAW_SHARE_GRID):
        value = brier_for(ha, float(ds))
        if value < best_brier:
            best, best_brier = float(ds), value
    return best


ELO_LIMITATIONS = [
    "Elo sees only W/D/L results: no scorelines, no xG, no shot quality.",
    "Ratings react slowly to abrupt changes (new manager, injuries, sale of a key player).",
    "Home advantage and the draw constant are fitted on training data; small leagues can overfit.",
    "No game-state or strength-of-schedule weighting beyond sequential updates.",
]
