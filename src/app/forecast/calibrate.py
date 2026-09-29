"""Walk-forward calibration: how good are the forecasts, out of sample?

At each block of matches the models are refitted using only matches played
before the block, then score the block. Nothing ever sees the future. Results are
reported as Brier score, ranked probability score (RPS), log-loss and accuracy,
alongside the naive base-rate forecast and (when available) Understat's own.
"""

from __future__ import annotations

import math

import numpy as np

from app.data.models import LeagueSeason

from .elo import fit_elo
from .model import ENSEMBLE_WEIGHT, match_rows
from .ratings import MatchRow, fit_ratings, scoreline_matrix, summarize_matrix

MIN_TRAIN = 40


def _outcome(m: MatchRow) -> int:
    return 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2


def _score(probs: np.ndarray, outcome: int) -> dict:
    target = np.zeros(3)
    target[outcome] = 1.0
    cum_p, cum_t = np.cumsum(probs), np.cumsum(target)
    return {
        "brier": float(np.sum((probs - target) ** 2)),
        "rps": float(np.sum((cum_p[:2] - cum_t[:2]) ** 2) / 2.0),
        "log_loss": float(-math.log(max(probs[outcome], 1e-9))),
        "correct": float(np.argmax(probs) == outcome),
    }


def calibrate(ls: LeagueSeason, prior: LeagueSeason | None = None, *, block: int = 10) -> dict:
    played = sorted(ls.played, key=lambda f: (f.dt, f.id))
    current = match_rows(ls)
    current.sort(key=lambda m: (m.date, m.home, m.away))
    prior_rows = match_rows(prior) if prior is not None else []
    if len(current) + len(prior_rows) < MIN_TRAIN + block:
        raise ValueError(f"Walk-forward calibration needs at least {MIN_TRAIN + block} matches; only {len(current) + len(prior_rows)} are available.")

    start = 0 if prior_rows and len(prior_rows) >= MIN_TRAIN else max(0, MIN_TRAIN - len(prior_rows))
    scores: dict[str, list[dict]] = {"ensemble": [], "ratings": [], "elo": [], "understat": [], "baseline": []}
    predictions: list[tuple[float, float]] = []  # (predicted home/draw/away prob, hit) pooled for reliability

    for begin in range(start, len(current), block):
        train = prior_rows + current[:begin]
        test = current[begin : begin + block]
        test_fixtures = played[begin : begin + block]
        if not test or len(train) < MIN_TRAIN:
            continue
        ratings = fit_ratings(train, as_of=test[0].date)
        elo = fit_elo(train)
        base = np.array([sum(_outcome(m) == k for m in train) / len(train) for k in range(3)])
        for m, fixture in zip(test, test_fixtures):
            lam_h, lam_a = ratings.rates(m.home, m.away)
            summary = summarize_matrix(scoreline_matrix(lam_h, lam_a, ratings.rho))
            rp = np.array([summary["p_home"], summary["p_draw"], summary["p_away"]])
            ep = np.array(elo.probabilities(m.home, m.away))
            blend = ENSEMBLE_WEIGHT * rp + (1 - ENSEMBLE_WEIGHT) * ep
            blend /= blend.sum()
            outcome = _outcome(m)
            scores["ensemble"].append(_score(blend, outcome))
            scores["ratings"].append(_score(rp, outcome))
            scores["elo"].append(_score(ep, outcome))
            scores["baseline"].append(_score(base, outcome))
            if fixture.forecast:
                scores["understat"].append(_score(np.array(fixture.forecast), outcome))
            for k in range(3):
                predictions.append((float(blend[k]), float(k == outcome)))

    summary_rows = {}
    for name, entries in scores.items():
        if not entries:
            continue
        n = len(entries)
        summary_rows[name] = {
            "n": n,
            "brier": round(sum(e["brier"] for e in entries) / n, 4),
            "rps": round(sum(e["rps"] for e in entries) / n, 4),
            "log_loss": round(sum(e["log_loss"] for e in entries) / n, 4),
            "accuracy": round(sum(e["correct"] for e in entries) / n, 4),
        }

    bins = np.linspace(0, 1, 11)
    reliability = []
    probs = np.array([p for p, _ in predictions])
    hits = np.array([h for _, h in predictions])
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi if hi < 1 else probs <= hi)
        if mask.sum() >= 5:
            reliability.append({"predicted": round(float(probs[mask].mean()), 3), "observed": round(float(hits[mask].mean()), 3), "n": int(mask.sum())})

    n_scored = summary_rows.get("ensemble", {}).get("n", 0)
    skill = None
    if "ensemble" in summary_rows and "baseline" in summary_rows:
        skill = round(1 - summary_rows["ensemble"]["rps"] / summary_rows["baseline"]["rps"], 4)
    return {
        "league": ls.league, "season": ls.season, "method": "walk-forward", "block": block,
        "n_scored": n_scored, "models": summary_rows, "reliability": reliability, "skill_vs_baseline": skill,
        "used_previous_season": bool(prior_rows),
    }
