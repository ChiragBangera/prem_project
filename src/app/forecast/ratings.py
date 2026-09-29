"""Team attack/defence ratings: a ridge-regularised Poisson model fitted on xG.

log(rate_home) = mu + home + attack[home] - defence[away]
log(rate_away) = mu +        attack[away] - defence[home]

* The response is a blend of xG (less noisy) and goals (captures real finishing
  and goalkeeping); xG-only is the default.
* Recent matches count more (exponential half-life), and last season's matches
  carry over with the same decay, so early-season forecasts are not wild.
* Ridge shrinkage pulls every team toward the league average in proportion to
  how little evidence there is - a team with three games gets a modest rating.
* The Dixon-Coles low-score correlation ``rho`` is estimated from *actual
  goals* (it is meaningless on fractional xG) with the standard
  marginal-preserving correction.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np

MAX_GOALS = 8
DEFAULT_HALF_LIFE = 240.0  # days
DEFAULT_RIDGE = 14.0
NEWCOMER_OFFSET = -0.10  # a team with no data starts a little below average


@dataclass(slots=True)
class MatchRow:
    home: str
    away: str
    date: str  # YYYY-MM-DD
    hg: int
    ag: int
    hxg: float
    axg: float


@dataclass
class Ratings:
    teams: list[str]
    attack: np.ndarray
    defence: np.ndarray
    home: float
    mu: float
    rho: float
    n_matches: int
    effective_n: float
    evidence: dict[str, float]  # team -> weighted number of matches behind its rating

    def index(self, team: str) -> int | None:
        try:
            return self.teams.index(team)
        except ValueError:
            return None

    def rates(self, home: str, away: str) -> tuple[float, float]:
        i, j = self.index(home), self.index(away)
        a_h = self.attack[i] if i is not None else NEWCOMER_OFFSET
        d_h = self.defence[i] if i is not None else NEWCOMER_OFFSET
        a_a = self.attack[j] if j is not None else NEWCOMER_OFFSET
        d_a = self.defence[j] if j is not None else NEWCOMER_OFFSET
        return math.exp(self.mu + self.home + a_h - d_a), math.exp(self.mu + a_a - d_h)

    def to_public(self) -> dict:
        return {
            "home_advantage": round(math.exp(self.home) - 1, 3),
            "rho": round(self.rho, 3),
            "n_matches": self.n_matches,
            "teams": {
                t: {"attack": round(float(self.attack[i]), 3), "defence": round(float(self.defence[i]), 3),
                    "evidence": round(self.evidence.get(t, 0.0), 1)}
                for i, t in enumerate(self.teams)
            },
        }


def _days(d: str) -> int:
    return date.fromisoformat(d[:10]).toordinal()


def fit_ratings(
    matches: list[MatchRow],
    *,
    as_of: str | None = None,
    half_life: float = DEFAULT_HALF_LIFE,
    ridge: float = DEFAULT_RIDGE,
    xg_weight: float = 1.0,
) -> Ratings:
    if not matches:
        raise ValueError("Cannot fit ratings without matches.")
    teams = sorted({m.home for m in matches} | {m.away for m in matches})
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    reference = _days(as_of) if as_of else max(_days(m.date) for m in matches)

    rows, cols_a, cols_d, y, w, is_home = [], [], [], [], [], []
    for m in matches:
        age = max(0, reference - _days(m.date))
        weight = 0.5 ** (age / half_life)
        h, a = index[m.home], index[m.away]
        th = xg_weight * m.hxg + (1 - xg_weight) * m.hg
        ta = xg_weight * m.axg + (1 - xg_weight) * m.ag
        cols_a += [h, a]
        cols_d += [a, h]
        is_home += [1.0, 0.0]
        y += [th, ta]
        w += [weight, weight]
    y_arr, w_arr, home_arr = np.array(y), np.array(w), np.array(is_home)
    a_idx, d_idx = np.array(cols_a), np.array(cols_d)
    m_obs = len(y_arr)

    # design matrix columns: [mu, home, attack(n), defence(n)]
    X = np.zeros((m_obs, 2 + 2 * n))
    X[:, 0] = 1.0
    X[:, 1] = home_arr
    X[np.arange(m_obs), 2 + a_idx] = 1.0
    X[np.arange(m_obs), 2 + n + d_idx] = -1.0
    penalty = np.zeros(2 + 2 * n)
    penalty[2:] = ridge

    beta = np.zeros(2 + 2 * n)
    beta[0] = math.log(max(1e-3, np.average(y_arr, weights=w_arr)))
    for _ in range(40):
        eta = np.clip(X @ beta, -6, 3)
        mu = np.exp(eta)
        weights = w_arr * mu
        z = eta + (y_arr - mu) / np.maximum(mu, 1e-9)
        A = X.T @ (weights[:, None] * X) + np.diag(penalty)
        b = X.T @ (weights * z)
        new = np.linalg.solve(A, b)
        if np.max(np.abs(new - beta)) < 1e-7:
            beta = new
            break
        beta = new

    attack, defence = beta[2 : 2 + n], beta[2 + n :]
    evidence = {t: 0.0 for t in teams}
    for m, weight in zip(matches, w_arr[::2]):
        evidence[m.home] += weight
        evidence[m.away] += weight

    ratings = Ratings(teams, attack, defence, float(beta[1]), float(beta[0]), -0.05, len(matches), float(w_arr[::2].sum()), evidence)
    ratings.rho = fit_rho(ratings, matches, w_arr[::2])
    return ratings


def tau(hg: int, ag: int, lam_h: float, lam_a: float, rho: float) -> float:
    """Dixon-Coles low-score correction (marginal preserving)."""
    if hg == 0 and ag == 0:
        return 1.0 - lam_h * lam_a * rho
    if hg == 0 and ag == 1:
        return 1.0 + lam_h * rho
    if hg == 1 and ag == 0:
        return 1.0 + lam_a * rho
    if hg == 1 and ag == 1:
        return 1.0 - rho
    return 1.0


def fit_rho(ratings: Ratings, matches: list[MatchRow], weights: np.ndarray) -> float:
    """Maximum-likelihood rho on realised goals, mildly shrunk toward -0.05."""
    rates = [ratings.rates(m.home, m.away) for m in matches]
    best_rho, best_ll = -0.05, -math.inf
    for rho in np.linspace(-0.25, 0.15, 81):
        ll = -20.0 * (rho + 0.05) ** 2  # weak prior
        valid = True
        for m, (lh, la), weight in zip(matches, rates, weights):
            t = tau(m.hg, m.ag, lh, la, rho)
            if t <= 0:
                valid = False
                break
            ll += weight * math.log(t)
        if valid and ll > best_ll:
            best_rho, best_ll = float(rho), ll
    return best_rho


# ---------------------------------------------------------------------- predictions


def _pmf(lam: float) -> np.ndarray:
    k = np.arange(MAX_GOALS + 1)
    logs = -lam + k * math.log(max(lam, 1e-9)) - np.array([math.lgamma(i + 1) for i in k])
    return np.exp(logs)


def scoreline_matrix(lam_h: float, lam_a: float, rho: float) -> np.ndarray:
    matrix = np.outer(_pmf(lam_h), _pmf(lam_a))
    for hg, ag in ((0, 0), (0, 1), (1, 0), (1, 1)):
        matrix[hg, ag] *= max(0.0, tau(hg, ag, lam_h, lam_a, rho))
    return matrix / matrix.sum()


def summarize_matrix(matrix: np.ndarray) -> dict:
    p_home = float(np.tril(matrix, -1).sum())
    p_draw = float(np.trace(matrix))
    p_away = float(np.triu(matrix, 1).sum())
    goals = np.add.outer(np.arange(matrix.shape[0]), np.arange(matrix.shape[1]))
    flat = np.argsort(matrix, axis=None)[::-1][:5]
    top = [(int(i // matrix.shape[1]), int(i % matrix.shape[1]), float(matrix.flat[i])) for i in flat]
    return {
        "p_home": p_home, "p_draw": p_draw, "p_away": p_away,
        "exp_home": float((matrix.sum(axis=1) * np.arange(matrix.shape[0])).sum()),
        "exp_away": float((matrix.sum(axis=0) * np.arange(matrix.shape[1])).sum()),
        "most_likely": top[0][:2], "top_scorelines": [{"score": [h, a], "p": round(p, 4)} for h, a, p in top],
        "over": {str(line): float(matrix[goals > line].sum()) for line in (1.5, 2.5, 3.5)},
        "btts": float(matrix[1:, 1:].sum()),
        "clean_sheet_home": float(matrix[:, 0].sum()),
        "clean_sheet_away": float(matrix[0, :].sum()),
    }
