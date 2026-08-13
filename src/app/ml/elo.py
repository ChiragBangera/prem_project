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
    results: list[tuple[str, str, float]] = []
    for m in ordered:
        home, away = m["home"], m["away"]
        rh = ratings.setdefault(home, initial_rating)
        ra = ratings.setdefault(away, initial_rating)
        hg, ag = int(m.get("home_goals", 0)), int(m.get("away_goals", 0))
        score = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        results.append((home, away, score))
        e = expected_share(rh, ra)
        delta = k * (score - e)
        ratings[home] = rh + delta
        ratings[away] = ra - delta

    ha = home_advantage if home_advantage is not None else _fit_home_advantage(results, ratings)
    ds = draw_share if draw_share is not None else _fit_draw_share(results, ratings, ha)

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

    train_brier = _brier(results, ratings, ha, ds) if results else None
    return {
        "ratings": {team: round(rating, 2) for team, rating in sorted(ratings.items(), key=lambda kv: -kv[1])},
        "home_advantage": round(ha, 2),
        "draw_share": round(ds, 3),
        "k": k,
        "n_matches": len(ordered),
        "train_brier": round(train_brier, 4) if train_brier is not None else None,
        "predict": predict,
    }


def _outcome_probs(ratings: dict[str, float], home: str, away: str, ha: float, ds: float) -> tuple[float, float, float]:
    s = expected_share(ratings[home] + ha, ratings[away])
    p_draw = min(ds * 4.0 * s * (1.0 - s), 1.0)
    p_home = max(0.0, s - p_draw / 2.0)
    p_away = max(0.0, 1.0 - s - p_draw / 2.0)
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


def _brier(results: list[tuple[str, str, float]], ratings: dict[str, float], ha: float, ds: float) -> float:
    total = 0.0
    for home, away, score in results:
        ph, pd, pa = _outcome_probs(ratings, home, away, ha, ds)
        if score == 1.0:
            target = (1.0, 0.0, 0.0)
        elif score == 0.5:
            target = (0.0, 1.0, 0.0)
        else:
            target = (0.0, 0.0, 1.0)
        total += (ph - target[0]) ** 2 + (pd - target[1]) ** 2 + (pa - target[2]) ** 2
    return total / len(results)


def _fit_home_advantage(results: list[tuple[str, str, float]], ratings: dict[str, float]) -> float:
    ds = 0.5
    best, best_brier = 0.0, float("inf")
    for ha in np.linspace(*HOME_ADVANTAGE_GRID):
        value = _brier(results, ratings, float(ha), ds)
        if value < best_brier:
            best, best_brier = float(ha), value
    return best


def _fit_draw_share(results: list[tuple[str, str, float]], ratings: dict[str, float], ha: float) -> float:
    best, best_brier = 0.5, float("inf")
    for ds in np.linspace(*DRAW_SHARE_GRID):
        value = _brier(results, ratings, ha, float(ds))
        if value < best_brier:
            best, best_brier = float(ds), value
    return best


ELO_LIMITATIONS = [
    "Elo sees only W/D/L results: no scorelines, no xG, no shot quality.",
    "Ratings react slowly to abrupt changes (new manager, injuries, sale of a key player).",
    "Home advantage and the draw constant are fitted on training data; small leagues can overfit.",
    "No game-state or strength-of-schedule weighting beyond sequential updates.",
]
