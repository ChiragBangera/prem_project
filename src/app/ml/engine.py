from __future__ import annotations

"""Model engine: turns Understat league data into fitted forecasts.

The seam is deliberately small so a future Rust/numpy-speed extension can slot
in behind the same functions without touching the API layer. Everything here
is pure Python + numpy; the models are:

- Dixon-Coles bivariate Poisson (poisson.py) fit on xG — scoreline forecasts.
- Elo (elo.py) fit on results — win/draw/loss forecasts.

Calibration is walk-forward over the played fixtures of a season and always
reports Brier/log-loss against empirical baselines (and Understat's own
forecast when the payload carries one), so the numbers are honest.
"""

import numpy as np

from . import elo, poisson

MIN_FIT_MATCHES = 20
MAX_WALKFORWARD_FITS = 120
SEASON_SIM_SIMS = 2000


def build_match_rows(dates: list[dict]) -> list[dict]:
    """Normalize Understat league-data `dates` rows into model-ready match rows."""
    rows = []
    for item in dates or []:
        home = (item.get("h") or {}).get("title")
        away = (item.get("a") or {}).get("title")
        if not home or not away:
            continue
        goals = item.get("goals") or {}
        xg = item.get("xG") or {}
        rows.append(
            {
                "home": home,
                "away": away,
                "home_goals": _to_int(goals.get("h")),
                "away_goals": _to_int(goals.get("a")),
                "home_xg": _to_float(xg.get("h")),
                "away_xg": _to_float(xg.get("a")),
                "date": (item.get("datetime") or "")[:10],
                "is_result": bool(item.get("isResult")),
                "match_id": item.get("id"),
                "forecast": item.get("forecast"),
            }
        )
    return rows


def dc_input(rows: list[dict], use_xg: bool = True, decay_half_life_days: float | None = None) -> list[dict]:
    """Rows for poisson.fit_dixon_coles; fit on xG by default (denoised)."""
    return [
        {
            "home": row["home"],
            "away": row["away"],
            "home_goals": row["home_xg"] if use_xg else float(row["home_goals"]),
            "away_goals": row["away_xg"] if use_xg else float(row["away_goals"]),
            "date": row["date"],
        }
        for row in rows
    ]


def elo_input(rows: list[dict]) -> list[dict]:
    """Rows for elo.fit_elo (results only; goals are integers)."""
    return [
        {
            "home": row["home"],
            "away": row["away"],
            "home_goals": row["home_goals"],
            "away_goals": row["away_goals"],
            "date": row["date"],
        }
        for row in rows
    ]


async def predict_match(client, league_name: str, season, home: str, away: str, use_xg: bool = True) -> dict:
    data = await client.get_league_data(league_name, season)
    rows = build_match_rows(data.get("dates", []))
    played = [row for row in rows if row["is_result"]]
    if len(played) < MIN_FIT_MATCHES:
        raise ValueError(
            f"Only {len(played)} played matches available for {league_name} {season}; "
            f"need at least {MIN_FIT_MATCHES} to fit a model."
        )
    known_teams = {row["home"] for row in rows} | {row["away"] for row in rows}
    if home not in known_teams or away not in known_teams:
        raise ValueError(f"Unknown teams for {league_name} {season}: '{home}' or '{away}'.")

    dc_model = poisson.fit_dixon_coles(dc_input(played, use_xg=use_xg), decay_half_life_days=180)
    dc_probs = poisson.match_probabilities(dc_model, home, away)
    elo_model = elo.fit_elo(elo_input(played))
    elo_probs = elo_model["predict"](home, away)

    return {
        "league_name": league_name,
        "season": season,
        "match": {"home": home, "away": away},
        "model": {
            "dixon_coles": {
                "fit_on": "xG" if use_xg else "goals",
                "n_matches": dc_model["n_matches"],
                "home_advantage": round(dc_model["home_advantage"], 3),
                "rho": round(dc_model["rho"], 3),
                "lambda_home": dc_probs["lambda_home"],
                "lambda_away": dc_probs["lambda_away"],
                "p_home": dc_probs["p_home"],
                "p_draw": dc_probs["p_draw"],
                "p_away": dc_probs["p_away"],
                "most_likely_score": dc_probs["most_likely_score"],
                "most_likely_score_prob": dc_probs["most_likely_score_prob"],
                "scoreline_matrix": dc_probs["scoreline_matrix"],
            },
            "elo": {
                "n_matches": elo_model["n_matches"],
                "home_advantage": elo_model["home_advantage"],
                "ratings": {
                    team: elo_model["ratings"][team]
                    for team in (home, away)
                    if team in elo_model["ratings"]
                },
                "p_home": elo_probs["p_home"],
                "p_draw": elo_probs["p_draw"],
                "p_away": elo_probs["p_away"],
            },
        },
        "interpretation": (
            f"Dixon-Coles (fit on {'xG' if use_xg else 'goals'} over {dc_model['n_matches']} played matches) "
            f"gives {home} a {dc_probs['p_home'] * 100:.1f}% win probability vs {away} at "
            f"{dc_probs['p_away'] * 100:.1f}%; Elo on results agrees/disagrees at "
            f"{elo_probs['p_home'] * 100:.1f}%/{elo_probs['p_away'] * 100:.1f}%."
        ),
        "limitations": poisson.DC_LIMITATIONS + elo.ELO_LIMITATIONS,
    }


async def simulate_rest_of_season(client, league_name: str, season, n_sims: int = SEASON_SIM_SIMS, use_xg: bool = True) -> dict:
    data = await client.get_league_data(league_name, season)
    rows = build_match_rows(data.get("dates", []))
    played = [row for row in rows if row["is_result"]]
    remaining = [row for row in rows if not row["is_result"]]
    if len(played) < MIN_FIT_MATCHES:
        raise ValueError(
            f"Only {len(played)} played matches available for {league_name} {season}; "
            f"need at least {MIN_FIT_MATCHES} to fit a model."
        )
    if not remaining:
        raise ValueError(
            f"No unplayed fixtures remain in the Understat schedule for {league_name} {season}; "
            "there is nothing to simulate."
        )

    dc_model = poisson.fit_dixon_coles(dc_input(played, use_xg=use_xg), decay_half_life_days=180)
    fixtures = [{"home": row["home"], "away": row["away"]} for row in remaining]
    table = await client.get_league_table(league_name, season)
    points = _table_points_map(table)
    sim = poisson.simulate_season(dc_model, fixtures, current_points=points, n_sims=n_sims)

    return {
        "league_name": league_name,
        "season": season,
        "model": {
            "fit_on": "xG" if use_xg else "goals",
            "n_matches": dc_model["n_matches"],
            "home_advantage": round(dc_model["home_advantage"], 3),
            "rho": round(dc_model["rho"], 3),
        },
        "n_played": len(played),
        "n_remaining": len(remaining),
        "current_points": {team: int(value) for team, value in sorted(points.items(), key=lambda kv: -kv[1])},
        **sim,
    }


async def forecast_calibration(client, league_name: str, season, use_xg: bool = True, min_train: int = 30, step: int = 5) -> dict:
    data = await client.get_league_data(league_name, season)
    rows = build_match_rows(data.get("dates", []))
    played = sorted((row for row in rows if row["is_result"]), key=lambda row: (row["date"], row["home"]))
    if len(played) < min_train + 5:
        raise ValueError(
            f"Walk-forward calibration needs at least {min_train + 5} played matches; "
            f"{league_name} {season} has {len(played)}."
        )

    interval = max(step, (len(played) - min_train) // MAX_WALKFORWARD_FITS)
    metrics = {name: [] for name in ("dixon_coles", "elo", "understat", "baseline")}
    for start in range(min_train, len(played), interval):
        train, test = played[:start], played[start : start + interval]
        dc_model = poisson.fit_dixon_coles(dc_input(train, use_xg=use_xg))
        elo_model = elo.fit_elo(elo_input(train))
        for row in test:
            outcome = _outcome(row)
            _record(metrics["dixon_coles"], _dc_outcome_probs(dc_model, row), outcome, row)
            _record(metrics["elo"], elo_model["predict"](row["home"], row["away"]), outcome, row)
            if row["forecast"]:
                _record(metrics["understat"], _understat_probs(row["forecast"]), outcome, row)
            _record(metrics["baseline"], _train_frequencies(train), outcome, row)

    summary = {}
    for name, entries in metrics.items():
        if not entries:
            continue
        n = len(entries)
        summary[name] = {
            "n": n,
            "brier": round(sum(e["brier"] for e in entries) / n, 4),
            "log_loss": round(sum(e["log_loss"] for e in entries) / n, 4),
            "accuracy": round(sum(e["correct"] for e in entries) / n, 4),
        }

    best = min(
        (name for name in summary if summary[name]["n"] == len(metrics["dixon_coles"])),
        key=lambda name: summary[name]["brier"],
        default=None,
    )
    return {
        "league_name": league_name,
        "season": season,
        "method": "walk-forward",
        "fit_on": "xG" if use_xg else "goals",
        "n_played": len(played),
        "min_train": min_train,
        "step": interval,
        "models": summary,
        "best_brier_model": best,
        "interpretation": (
            f"Walk-forward calibration over {len(metrics['dixon_coles'])} out-of-sample predictions. "
            f"Lower Brier/log-loss and higher accuracy are better; the baseline is the training-set "
            f"home/draw/away frequency, the standard honest benchmark."
        ),
        "limitations": [
            "One season is a small sample; calibration Brier values are noisy.",
            "Understat's forecast column is used as-is when present; its methodology is undisclosed.",
            "Walk-forward fits refit every N matches, not after every single match.",
            "Fit-on-xG Dixon-Coles may look better on xG than on realised results; Elo is the pure-results counterpoint.",
        ],
    }


def _dc_outcome_probs(dc_model: dict, row: dict) -> dict:
    probs = poisson.match_probabilities(dc_model, row["home"], row["away"])
    return {"p_home": probs["p_home"], "p_draw": probs["p_draw"], "p_away": probs["p_away"]}


def _understat_probs(forecast) -> dict:
    values = {
        "p_home": _to_float((forecast or {}).get("w")),
        "p_draw": _to_float((forecast or {}).get("d")),
        "p_away": _to_float((forecast or {}).get("l")),
    }
    total = values["p_home"] + values["p_draw"] + values["p_away"]
    if total > 1.5:  # percentage-scale values
        values = {key: value / 100.0 for key, value in values.items()}
        total = sum(values.values())
    if total <= 0:
        return {"p_home": 1 / 3, "p_draw": 1 / 3, "p_away": 1 / 3}
    return {key: round(value / total, 4) for key, value in values.items()}


def _train_frequencies(train: list[dict]) -> dict:
    n = len(train) or 1
    home_wins = sum(1 for row in train if row["home_goals"] > row["away_goals"]) / n
    draws = sum(1 for row in train if row["home_goals"] == row["away_goals"]) / n
    away_wins = 1.0 - home_wins - draws
    return {"p_home": home_wins, "p_draw": draws, "p_away": away_wins}


def _outcome(row: dict) -> int:
    if row["home_goals"] > row["away_goals"]:
        return 0
    if row["home_goals"] < row["away_goals"]:
        return 2
    return 1


def _record(entries: list, probs: dict, outcome: int, row: dict) -> None:
    pred = np.array([probs["p_home"], probs["p_draw"], probs["p_away"]])
    target = np.zeros(3)
    target[outcome] = 1.0
    entries.append(
        {
            "brier": float(((pred - target) ** 2).sum()),
            "log_loss": float(-np.log(np.clip(pred[outcome], 1e-9, 1.0))),
            "correct": int(np.argmax(pred) == outcome),
        }
    )


def _table_points_map(table) -> dict[str, int]:
    points: dict[str, int] = {}
    rows = table[1:] if table and _is_header(table[0]) else (table or [])
    for row in rows:
        if not row or not row[0]:
            continue
        points[str(row[0])] = _to_int(row[7]) if len(row) > 7 else 0
    return points


def _is_header(row) -> bool:
    return bool(row) and str(row[0]).strip().lower() == "team"


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
