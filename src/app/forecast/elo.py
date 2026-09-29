"""Elo ratings from results only: the independent, xG-blind cross-check.

Margin of victory nudges the update (a 4-0 says more than a 1-0), each new
season pulls ratings part-way back toward the mean, and the two constants that
map a rating gap to win/draw/loss probabilities (home advantage, draw share)
are fitted by minimising Brier score on the matches themselves.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .ratings import MatchRow

INITIAL = 1500.0
K = 22.0
SEASON_REGRESSION = 0.30  # fraction pulled back to the mean at a season boundary


@dataclass
class Elo:
    ratings: dict[str, float]
    home_advantage: float
    draw_share: float
    n_matches: int
    _fit: dict = field(default_factory=dict, repr=False)

    def probabilities(self, home: str, away: str) -> tuple[float, float, float]:
        rh = self.ratings.get(home, INITIAL - 40) + self.home_advantage
        ra = self.ratings.get(away, INITIAL - 40)
        return _probs(rh, ra, self.draw_share)

    def to_public(self, top: int | None = None) -> dict:
        ordered = sorted(self.ratings.items(), key=lambda kv: -kv[1])
        return {"home_advantage": round(self.home_advantage), "draw_share": round(self.draw_share, 2), "ratings": {k: round(v) for k, v in ordered[:top]}}


def _expected(rh: float, ra: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((ra - rh) / 400.0))


def _probs(rh: float, ra: float, draw_share: float) -> tuple[float, float, float]:
    s = _expected(rh, ra)
    p_draw = min(draw_share * 4.0 * s * (1.0 - s), 0.6)
    p_home = max(1e-4, s - p_draw / 2.0)
    p_away = max(1e-4, 1.0 - s - p_draw / 2.0)
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


def fit_elo(matches: list[MatchRow], home_advantage: float | None = None, draw_share: float | None = None) -> Elo:
    ordered = sorted(matches, key=lambda m: (m.date, m.home, m.away))
    ratings: dict[str, float] = {}
    seasons_seen: int | None = None
    history = []  # (rating_home_before, rating_away_before, outcome)
    ha_guess = home_advantage if home_advantage is not None else 60.0

    for m in ordered:
        season = int(m.date[:4]) + (1 if int(m.date[5:7]) >= 7 else 0)
        if seasons_seen is not None and season != seasons_seen:
            mean = sum(ratings.values()) / len(ratings) if ratings else INITIAL
            ratings = {t: r + SEASON_REGRESSION * (mean - r) for t, r in ratings.items()}
        seasons_seen = season
        rh, ra = ratings.get(m.home, INITIAL), ratings.get(m.away, INITIAL)
        outcome = 1.0 if m.hg > m.ag else 0.5 if m.hg == m.ag else 0.0
        history.append((rh, ra, outcome))
        expected = _expected(rh + ha_guess, ra)
        margin = 1.0 + math.log(1.0 + abs(m.hg - m.ag)) * 0.6
        delta = K * margin * (outcome - expected)
        ratings[m.home] = rh + delta
        ratings[m.away] = ra - delta

    arr = np.array(history) if history else np.zeros((0, 3))

    def brier(ha: float, ds: float) -> float:
        if not len(arr):
            return 0.0
        s = 1.0 / (1.0 + 10.0 ** ((arr[:, 1] - (arr[:, 0] + ha)) / 400.0))
        pd = np.minimum(ds * 4.0 * s * (1.0 - s), 0.6)
        ph = np.maximum(1e-4, s - pd / 2.0)
        pa = np.maximum(1e-4, 1.0 - s - pd / 2.0)
        tot = ph + pd + pa
        ph, pd, pa = ph / tot, pd / tot, pa / tot
        out = arr[:, 2]
        return float(np.mean((ph - (out == 1.0)) ** 2 + (pd - (out == 0.5)) ** 2 + (pa - (out == 0.0)) ** 2))

    ha = home_advantage if home_advantage is not None else min(np.linspace(0, 140, 15), key=lambda v: brier(v, 0.9))
    ds = draw_share if draw_share is not None else min(np.linspace(0.3, 1.2, 19), key=lambda v: brier(ha, v))
    return Elo(ratings, float(ha), float(ds), len(ordered))
