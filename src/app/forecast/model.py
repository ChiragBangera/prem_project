"""The forecaster: ratings model + Elo, blended, with one coherent scoreline grid."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.data.models import Fixture, LeagueSeason

from .elo import Elo, fit_elo
from .ratings import MatchRow, Ratings, fit_ratings, scoreline_matrix, summarize_matrix

ENSEMBLE_WEIGHT = 0.7  # share of the ratings (xG) model; the rest is Elo (results)
MIN_MATCHES = 8


def match_rows(ls: LeagueSeason) -> list[MatchRow]:
    return [
        MatchRow(f.home, f.away, f.date, f.hg or 0, f.ag or 0, f.hxg if f.hxg is not None else float(f.hg or 0), f.axg if f.axg is not None else float(f.ag or 0))
        for f in ls.played
    ]


@dataclass
class Forecaster:
    ratings: Ratings
    elo: Elo
    weight: float
    league: str
    season: int
    as_of: str
    used_previous_season: bool

    def blend(self, home: str, away: str) -> tuple[np.ndarray, dict]:
        lam_h, lam_a = self.ratings.rates(home, away)
        matrix = scoreline_matrix(lam_h, lam_a, self.ratings.rho)
        raw = summarize_matrix(matrix)
        e_h, e_d, e_a = self.elo.probabilities(home, away)
        w = self.weight
        target = np.array([w * raw["p_home"] + (1 - w) * e_h, w * raw["p_draw"] + (1 - w) * e_d, w * raw["p_away"] + (1 - w) * e_a])
        target /= target.sum()
        # Rescale the grid so its outcome totals equal the blended probabilities.
        n = matrix.shape[0]
        home_mask, away_mask = np.tril(np.ones((n, n)), -1) > 0, np.triu(np.ones((n, n)), 1) > 0
        draw_mask = np.eye(n) > 0
        blended = matrix.copy()
        for mask, share, current in ((home_mask, target[0], raw["p_home"]), (draw_mask, target[1], raw["p_draw"]), (away_mask, target[2], raw["p_away"])):
            blended[mask] *= share / max(current, 1e-9)
        blended /= blended.sum()
        return blended, {"lambda": (lam_h, lam_a), "ratings_probs": (raw["p_home"], raw["p_draw"], raw["p_away"]), "elo_probs": (e_h, e_d, e_a)}

    def predict(self, home: str, away: str, understat: tuple[float, float, float] | None = None) -> dict:
        blended, parts = self.blend(home, away)
        summary = summarize_matrix(blended)
        lam_h, lam_a = parts["lambda"]
        return {
            "home": home, "away": away, "league": self.league, "season": self.season, "as_of": self.as_of,
            "p_home": round(summary["p_home"], 4), "p_draw": round(summary["p_draw"], 4), "p_away": round(summary["p_away"], 4),
            "expected_goals": {"home": round(lam_h, 2), "away": round(lam_a, 2)},
            "most_likely": list(summary["most_likely"]), "top_scorelines": summary["top_scorelines"],
            "markets": {"over": {k: round(v, 4) for k, v in summary["over"].items()}, "btts": round(summary["btts"], 4),
                        "clean_sheet_home": round(summary["clean_sheet_home"], 4), "clean_sheet_away": round(summary["clean_sheet_away"], 4)},
            "models": {
                "ratings": dict(zip(("home", "draw", "away"), (round(x, 4) for x in parts["ratings_probs"]))),
                "elo": dict(zip(("home", "draw", "away"), (round(x, 4) for x in parts["elo_probs"]))),
                "weights": {"ratings": self.weight, "elo": round(1 - self.weight, 2)},
                "elo_ratings": {home: round(self.elo.ratings.get(home, 0)), away: round(self.elo.ratings.get(away, 0))},
                "rho": round(self.ratings.rho, 3), "home_advantage": round(float(np.exp(self.ratings.home) - 1), 3),
            },
            "understat": None if understat is None else dict(zip(("home", "draw", "away"), (round(x, 4) for x in understat))),
            "matrix": [[round(float(v), 5) for v in row] for row in blended],
            "evidence": {"home": round(self.ratings.evidence.get(home, 0.0), 1), "away": round(self.ratings.evidence.get(away, 0.0), 1)},
        }

    def row(self, fixture: Fixture) -> dict:
        blended, parts = self.blend(fixture.home, fixture.away)
        s = summarize_matrix(blended)
        low = min(self.ratings.evidence.get(fixture.home, 0.0), self.ratings.evidence.get(fixture.away, 0.0)) < 4
        return {
            "id": fixture.id, "date": fixture.date, "dt": fixture.dt, "round": fixture.round,
            "home": fixture.home, "away": fixture.away, "home_short": fixture.home_short, "away_short": fixture.away_short,
            "p_home": round(s["p_home"], 3), "p_draw": round(s["p_draw"], 3), "p_away": round(s["p_away"], 3),
            "exp_home": round(parts["lambda"][0], 2), "exp_away": round(parts["lambda"][1], 2),
            "most_likely": list(s["most_likely"]),
            "over25": round(s["over"]["2.5"], 3), "btts": round(s["btts"], 3),
            "understat": None if fixture.forecast is None else dict(zip(("home", "draw", "away"), (round(x, 3) for x in fixture.forecast))),
            "low_evidence": low,
        }


def build_forecaster(
    ls: LeagueSeason,
    prior: LeagueSeason | None = None,
    *,
    as_of: str | None = None,
    weight: float = ENSEMBLE_WEIGHT,
    xg_weight: float = 1.0,
) -> Forecaster:
    rows = match_rows(ls)
    used_prior = False
    if prior is not None:
        rows = match_rows(prior) + rows
        used_prior = True
    if len(rows) < MIN_MATCHES:
        raise ValueError(f"Only {len(rows)} played matches are available; at least {MIN_MATCHES} are needed to fit a model.")
    stamp = as_of or (max(r.date for r in rows))
    ratings = fit_ratings(rows, as_of=stamp, xg_weight=xg_weight)
    elo = fit_elo(rows)
    return Forecaster(ratings, elo, weight, ls.league, ls.season, stamp, used_prior)


def fixtures_forecast(fc: Forecaster, ls: LeagueSeason, *, limit: int = 12, horizon_days: int = 9) -> list[dict]:
    upcoming = sorted(ls.upcoming, key=lambda f: (f.dt, f.id))
    if not upcoming:
        return []
    from datetime import date, timedelta

    first = date.fromisoformat(upcoming[0].date)
    cutoff = (first + timedelta(days=horizon_days)).isoformat()
    window = [f for f in upcoming if f.date <= cutoff]
    return [fc.row(f) for f in window[:limit]]
