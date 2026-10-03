"""The front page: what changed, what to read, what is coming."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from app.analytics.table import rank_trajectories
from app.data.models import LeagueSeason
from app.stats import outcome_probs

from .core import Insight, rank

MAX_GOALS = 10


def _pmf(mu: float) -> np.ndarray:
    k = np.arange(MAX_GOALS + 1)
    return np.exp(-mu + k * math.log(max(mu, 1e-9)) - np.array([math.lgamma(i + 1) for i in k]))


def result_probabilities(hxg: float, axg: float) -> tuple[float, float, float]:
    """Poisson approximation of a result from the two xG totals (exact version needs shots)."""
    return outcome_probs(_pmf(hxg), _pmf(axg))


def recent_matches(ls: LeagueSeason, limit: int = 10) -> list[dict]:
    rows = []
    for f in sorted(ls.played, key=lambda f: (f.dt, f.id), reverse=True)[:limit]:
        ph, pd, pa = result_probabilities(f.hxg or 0.0, f.axg or 0.0)
        hg, ag = f.hg or 0, f.ag or 0
        actual = "home" if hg > ag else "away" if ag > hg else "draw"
        p_actual = {"home": ph, "draw": pd, "away": pa}[actual]
        flag = None
        if actual != "draw" and p_actual < 0.22:
            flag = "against_run_of_play"
        elif actual == "draw" and max(ph, pa) >= 0.55:
            flag = "favourite_held"
        rows.append(
            {
                "id": f.id, "date": f.date, "round": f.round, "home": f.home, "away": f.away,
                "home_short": f.home_short, "away_short": f.away_short, "hg": f.hg, "ag": f.ag,
                "hxg": round(f.hxg or 0, 2), "axg": round(f.axg or 0, 2),
                "p_home": round(ph, 3), "p_draw": round(pd, 3), "p_away": round(pa, 3), "flag": flag,
            }
        )
    return rows


def movers(ls: LeagueSeason, span: int = 3) -> dict:
    """Biggest movers in table position over the last ``span`` matchweeks."""
    paths = rank_trajectories(ls)
    rounds = paths["rounds"]
    if rounds <= span:
        return {"risers": [], "fallers": [], "span": span}
    changes = []
    for team, ranks in paths["rank"].items():
        if len(ranks) > span and ranks[-1] is not None and ranks[-1 - span] is not None:
            changes.append({"team": team, "short": ls.teams[team].short, "from": ranks[-1 - span], "to": ranks[-1], "change": ranks[-1 - span] - ranks[-1]})
    risers = sorted((c for c in changes if c["change"] >= 2), key=lambda c: -c["change"])[:3]
    fallers = sorted((c for c in changes if c["change"] <= -2), key=lambda c: c["change"])[:3]
    return {"risers": risers, "fallers": fallers, "span": span}


def compose_insights(
    league: Sequence[Insight],
    scouting: Sequence[Insight],
    *,
    limit: int = 8,
) -> list[Insight]:
    """A balanced front page: strongest team stories plus a few players worth a look."""
    picked = rank(league, limit=max(1, limit - 3), per_kind=2)
    picked += rank(scouting, limit=3, per_kind=1, diversify=True)
    return sorted(picked, key=lambda i: (-i.score, i.id))[:limit]
