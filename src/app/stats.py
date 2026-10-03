"""Small, dependency-light statistics helpers shared across the app."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence

import numpy as np


def poisson_binomial(probs: Iterable[float]) -> np.ndarray:
    """PMF of the number of successes over independent Bernoulli(p_i) trials.

    The exact distribution of a side's goals given the xG of each of its shots.
    """
    pmf = np.array([1.0])
    for p in probs:
        p = min(max(float(p), 0.0), 1.0)
        pmf = np.convolve(pmf, (1.0 - p, p))
    return pmf


def outcome_probs(pmf_home: np.ndarray, pmf_away: np.ndarray) -> tuple[float, float, float]:
    """(P(home win), P(draw), P(away win)) from two independent goal PMFs."""
    n = max(len(pmf_home), len(pmf_away))
    h = np.pad(pmf_home, (0, n - len(pmf_home)))
    a = np.pad(pmf_away, (0, n - len(pmf_away)))
    cdf_a = np.cumsum(a)
    cdf_h = np.cumsum(h)
    p_home = float(np.sum(h[1:] * cdf_a[:-1]))
    p_away = float(np.sum(a[1:] * cdf_h[:-1]))
    p_draw = float(np.sum(h * a))
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


def shot_luck(goals: int, shot_xgs: Sequence[float]) -> dict:
    """How surprising is scoring ``goals`` from these shots, given their xG?

    Uses the exact Poisson-binomial distribution (each shot scores with
    probability equal to its xG). Returns the expectation, the standard
    deviation, a z-score and the one-sided tail probabilities.
    """
    if not len(shot_xgs):
        return {"expected": 0.0, "sd": 0.0, "z": 0.0, "p_at_least": 1.0, "p_at_most": 1.0, "shots": 0}
    pmf = poisson_binomial(shot_xgs)
    k = np.arange(len(pmf))
    mean = float(np.sum(k * pmf))
    var = float(np.sum((k - mean) ** 2 * pmf))
    sd = math.sqrt(var) if var > 0 else 0.0
    goals_i = max(0, min(int(goals), len(pmf) - 1))
    return {
        "expected": mean,
        "sd": sd,
        "z": (goals - mean) / sd if sd > 0 else 0.0,
        "p_at_least": float(pmf[goals_i:].sum()),
        "p_at_most": float(pmf[: goals_i + 1].sum()),
        "shots": len(shot_xgs),
    }


def percentile_rank(value: float, sample: Sequence[float]) -> float:
    """Mid-rank percentile of ``value`` within ``sample`` (0-100).

    Ties count half, so a value equal to everything sits at 50. ``sample`` may
    include ``value`` itself.
    """
    n = len(sample)
    if n == 0:
        return 50.0
    ordered = sorted(sample)
    below = bisect_left(ordered, value)
    equal = bisect_right(ordered, value) - below
    return 100.0 * (below + 0.5 * equal) / n


def percentile_ranks(values: Sequence[float]) -> list[float]:
    """Percentile of each value within the whole list (vectorised ``percentile_rank``)."""
    n = len(values)
    if n == 0:
        return []
    ordered = sorted(values)
    out = []
    for v in values:
        below = bisect_left(ordered, v)
        equal = bisect_right(ordered, v) - below
        out.append(100.0 * (below + 0.5 * equal) / n)
    return out


def zscore(value: float, sample: Sequence[float]) -> float:
    n = len(sample)
    if n < 2:
        return 0.0
    mean = sum(sample) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in sample) / (n - 1))
    return (value - mean) / sd if sd > 0 else 0.0


def mean(values: Sequence[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if len(values) else default


def per90(value: float, minutes: float) -> float:
    return value * 90.0 / minutes if minutes > 0 else 0.0


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b else default
