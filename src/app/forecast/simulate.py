"""Monte Carlo of the rest of the season from the fitted model."""

from __future__ import annotations

import numpy as np

from app.analytics.table import compute_table
from app.data.models import LeagueSeason
from app.leagues import LEAGUES

from .model import Forecaster


def simulate_season(fc: Forecaster, ls: LeagueSeason, *, n_sims: int = 4000, seed: int = 11) -> dict:
    table = compute_table(ls)
    teams = [r["team"] for r in table]
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    points0 = np.array([r["pts"] for r in table], dtype=float)
    gd0 = np.array([r["gd"] for r in table], dtype=float)
    fixtures = [f for f in ls.upcoming if f.home in index and f.away in index]
    rng = np.random.default_rng(seed)

    points = np.tile(points0[:, None], (1, n_sims))
    gd = np.tile(gd0[:, None], (1, n_sims))
    goals_for = np.zeros((n, n_sims))
    for f in fixtures:
        matrix, _parts = fc.blend(f.home, f.away)
        cdf = np.cumsum(matrix.ravel())
        cell = np.minimum(np.searchsorted(cdf, rng.random(n_sims)), matrix.size - 1)
        h, a = cell // matrix.shape[1], cell % matrix.shape[1]
        i, j = index[f.home], index[f.away]
        points[i] += np.where(h > a, 3, np.where(h == a, 1, 0))
        points[j] += np.where(a > h, 3, np.where(h == a, 1, 0))
        gd[i] += h - a
        gd[j] += a - h
        goals_for[i] += h
        goals_for[j] += a

    # final positions: points, then goal difference, then a coin flip
    score = points * 1e6 + gd * 1e2 + rng.random((n, n_sims))
    order = np.argsort(-score, axis=0)
    positions = np.empty_like(order)
    rows = np.arange(n_sims)
    positions[order, rows[None, :]] = np.arange(1, n + 1)[:, None]

    cfg = LEAGUES.get(ls.league)
    ucl = cfg.ucl_places if cfg else 4
    relegation = cfg.relegation_places if cfg else 3
    distribution = np.stack([(positions == p).mean(axis=1) for p in range(1, n + 1)], axis=1)

    out = []
    for i, team in enumerate(teams):
        pos = positions[i]
        out.append(
            {
                "team": team,
                "short": ls.teams[team].short,
                "played": table[i]["played"],
                "points": int(points0[i]),
                "gd": int(gd0[i]),
                "exp_points": round(float(points[i].mean()), 1),
                "points_p10": int(np.percentile(points[i], 10)),
                "points_p90": int(np.percentile(points[i], 90)),
                "exp_position": round(float(pos.mean()), 1),
                "p_title": round(float((pos == 1).mean()), 4),
                "p_top4": round(float((pos <= ucl).mean()), 4),
                "p_relegation": round(float((pos > n - relegation).mean()), 4),
                "distribution": [round(float(v), 4) for v in distribution[i]],
                "remaining": sum(1 for f in fixtures if team in (f.home, f.away)),
            }
        )
    out.sort(key=lambda r: (-r["exp_points"], r["team"]))
    return {
        "n_sims": n_sims,
        "remaining_fixtures": len(fixtures),
        "ucl_places": ucl,
        "relegation_places": relegation,
        "teams": out,
        "as_of": fc.as_of,
    }
