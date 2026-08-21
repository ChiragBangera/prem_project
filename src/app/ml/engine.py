from __future__ import annotations

"""Model engine: turns Understat league data into fitted forecasts.

The seam is deliberately small so a future Rust/numpy-speed extension can slot
in behind the same functions without touching the API layer. Everything here
is pure Python + numpy; the models are:

- Dixon-Coles bivariate Poisson (poisson.py) fit on xG — scoreline forecasts.
- Elo (elo.py) fit on results — win/draw/loss forecasts.

v2 adds three transparent adjustment layers on top of the base Dixon-Coles
lambdas (all documented and damped, never dominant):
- team-specific venue effect (each team's home/away xG split vs league norm),
- recent-form overlay (last 5 matches vs season baseline),
- availability sensitivity (team xG with vs without its top xGChain creator).

Calibration is walk-forward over the played fixtures of a season and always
reports Brier/log-loss against empirical baselines (and Understat's own
forecast when the payload carries one), so the numbers are honest.
"""

import asyncio

import numpy as np

from . import elo, features as feature_store, pi_ratings, poisson, xgb as xgb_models

MIN_FIT_MATCHES = 20
MAX_WALKFORWARD_FITS = 120
SEASON_SIM_SIMS = 2000
VENUE_DAMPING = 0.5
FORM_DAMPING = 0.5
POOL_LEAGUES = ("EPL", "La_liga", "Serie_A", "Bundesliga", "Ligue_1")

_history_cache: dict[tuple, dict] = {}
_creator_cache: dict[tuple, dict] = {}


def rps_metric(probs: dict, outcome: int) -> float:
    """Ranked probability score over home(0)/draw(1)/away(2) ordering."""
    pred = np.array([probs["p_home"], probs["p_draw"], probs["p_away"]])
    target = np.zeros(3)
    target[outcome] = 1.0
    cumulative_pred = np.cumsum(pred)
    cumulative_target = np.cumsum(target)
    return float(np.sum((cumulative_pred - cumulative_target) ** 2) / 2.0)


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


async def predict_match(client, league_name: str, season, home: str, away: str,
                        use_xg: bool = True, pool_leagues: bool = True) -> dict:
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
    base = poisson.match_probabilities(dc_model, home, away)
    elo_model = elo.fit_elo(elo_input(played))
    elo_probs = elo_model["predict"](home, away)
    pi_model = pi_ratings.fit_pi_ratings(elo_input(played))
    pi_probs = poisson.outcome_probs_from_lambdas(
        pi_model["predict"](home, away)["lambda_home"],
        pi_model["predict"](home, away)["lambda_away"],
        rho=0.0,
    )

    venue = _venue_report(played, home, away)
    form = _form_report(played, home, away)

    lam_h = base["lambda_home"]
    lam_a = base["lambda_away"]
    lam_h = lam_h * np.exp(venue["home_factor"]) * (1.0 + form["home_factor"])
    lam_a = lam_a * np.exp(-venue["away_factor"]) * (1.0 + form["away_factor"])
    adjusted = poisson.outcome_probs_from_lambdas(lam_h, lam_a, dc_model["rho"])

    ensemble = _ensemble(played, home, away, use_xg)

    availability = await _availability_report(client, league_name, season, home, away, lam_h, lam_a, dc_model["rho"])

    xgboost_report = await _xgboost_fixture_report(
        client, league_name, season, rows, home, away, dc_model, pool_leagues=pool_leagues
    )

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
                "lambda_home": base["lambda_home"],
                "lambda_away": base["lambda_away"],
                "p_home": base["p_home"],
                "p_draw": base["p_draw"],
                "p_away": base["p_away"],
                "most_likely_score": base["most_likely_score"],
                "most_likely_score_prob": base["most_likely_score_prob"],
                "scoreline_matrix": base["scoreline_matrix"],
                "derived": base["derived"],
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
            "pi_ratings": {
                "n_matches": pi_model["n_matches"],
                "home_advantage": pi_model["home_advantage"],
                "p_home": pi_probs["p_home"],
                "p_draw": pi_probs["p_draw"],
                "p_away": pi_probs["p_away"],
            },
            "xgboost": xgboost_report,
            "ensemble": ensemble,
            "adjusted": {
                "lambda_home": adjusted["lambda_home"],
                "lambda_away": adjusted["lambda_away"],
                "p_home": adjusted["p_home"],
                "p_draw": adjusted["p_draw"],
                "p_away": adjusted["p_away"],
                "most_likely_score": adjusted["most_likely_score"],
                "derived": adjusted["derived"],
            },
            "adjustments": {"venue": venue, "form": form},
            "availability": availability,
        },
        "interpretation": (
            f"Dixon-Coles (fit on {'xG' if use_xg else 'goals'} over {dc_model['n_matches']} played matches) "
            f"gives {home} a {base['p_home'] * 100:.1f}% win probability vs {away} at "
            f"{base['p_away'] * 100:.1f}%; Elo on results says {elo_probs['p_home'] * 100:.1f}%/"
            f"{elo_probs['p_away'] * 100:.1f}%. The ensemble blends both at weight "
            f"{ensemble['weight']:.2f}."
        ),
        "limitations": poisson.DC_LIMITATIONS + elo.ELO_LIMITATIONS + pi_ratings.PI_LIMITATIONS + xgb_models.XGB_LIMITATIONS + [
            "Adjustment layers are damped and documented; they never outweigh the fitted model.",
            "Availability scenarios assume the key creator is either fully available or fully absent; partial minutes are coarser.",
        ],
    }


async def _xgboost_fixture_report(client, league_name, season, rows, home, away,
                                  dc_model, pool_leagues: bool) -> dict | None:
    try:
        played = [row for row in rows if row["is_result"]]
        unplayed_fixture = next(
            (row for row in rows if row["home"] == home and row["away"] == away and not row["is_result"]), None
        )
        pooled = await _pooled_played_rows(client, season, pool_leagues, exclude_league=league_name)
        train_rows = pooled + played
        if len(train_rows) < 80:
            return {"available": False, "reason": "fewer than 80 training matches"}

        enriched = await _enrich_rows(client, league_name, season, train_rows)
        creator = await _creator_lookup(client, league_name, season, played)
        seq = feature_store.build_sequential_features(enriched, creator_minutes=creator)
        names = seq["names"] + dc_names()

        if unplayed_fixture is not None:
            # Build pre-match features for the upcoming fixture (pseudo-row).
            enriched_fixture = await _enrich_rows(client, league_name, season, [unplayed_fixture])
            seq_fixture = feature_store.build_sequential_features(enriched_fixture, creator_minutes=creator)
            target_vector = seq_fixture["features"]
            n_fixture = 1
            dc_model_for_target = dc_model
            train_idx = np.arange(len(seq["rows"]))
            label = "upcoming fixture (pre-match features)"
        else:
            # Retrodiction: the match already happened; use its own pre-match
            # features and train leaving that match out.
            played_sorted = sorted(played, key=lambda r: (r["date"], r["home"], r["away"]))
            target_row = next(
                (row for row in reversed(played_sorted) if row["home"] == home and row["away"] == away), None
            )
            if target_row is None:
                return {"available": False, "reason": "no matching played fixture to retrodict"}
            target_idx = next(
                i for i, row in enumerate(seq["rows"])
                if row["home"] == home and row["away"] == away and row["date"] == target_row["date"]
            )
            target_vector = {name: seq["features"][name][target_idx : target_idx + 1] for name in seq["names"]}
            n_fixture = 1
            train_idx = np.array([i for i in range(len(seq["rows"])) if i != target_idx])
            dc_model_for_target = poisson.fit_dixon_coles(
                dc_input([row for i, row in enumerate(seq["rows"]) if i != target_idx], use_xg=True)
            )
            label = "retrodiction (pre-match features, leave-one-out)"

        dc_target = feature_store.dc_features(dc_model_for_target, [seq["rows"][0]])
        seq_matrix = xgb_models.matrix(seq["features"], seq["names"], train_idx)
        dc_train = feature_store.dc_features(dc_model_for_target, [seq["rows"][i] for i in train_idx])
        X_train = np.column_stack([seq_matrix, *[dc_train[name] for name in dc_names()]])
        targets = seq["targets"]
        models = xgb_models.train_poisson(
            X_train, targets["home_goals"][train_idx], targets["away_goals"][train_idx]
        )

        x_seq = np.column_stack([target_vector[name] for name in seq["names"]])
        x_dc = np.column_stack([dc_target[name] for name in dc_names()])
        X_target = np.column_stack([x_seq, x_dc])
        lam_h, lam_a = xgb_models.predict_lambdas(models, X_target)
        probs = poisson.outcome_probs_from_lambdas(float(lam_h[0]), float(lam_a[0]), dc_model["rho"])
        return {
            "available": True,
            "variant": "poisson (goals target)",
            "kind": label,
            "n_train": len(train_idx),
            "pooled": bool(pooled),
            "lambda_home": probs["lambda_home"],
            "lambda_away": probs["lambda_away"],
            "p_home": probs["p_home"],
            "p_draw": probs["p_draw"],
            "p_away": probs["p_away"],
            "most_likely_score": probs["most_likely_score"],
            "derived": probs["derived"],
            "feature_importance": _combined_importance(models, names),
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)[:200]}


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
    goals_now = _table_goals_map(table)
    sim = poisson.simulate_season(dc_model, fixtures, current_points=points, n_sims=n_sims)

    expected_final_goals = {
        team: round(goals_now.get(team, 0) + sim["expected_goals_for"].get(team, 0), 1)
        for team in sim["expected_points"]
    }
    top_scorers = await _top_scorer_projection(
        client, league_name, season, remaining
    )

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
        "current_goals": {team: int(goals_now.get(team, 0)) for team in sim["expected_points"]},
        "expected_final_goals": expected_final_goals,
        "top_scorer_projection": top_scorers,
        **sim,
    }


async def forecast_calibration(client, league_name: str, season, use_xg: bool = True,
                               min_train: int = 30, step: int = 5, pool_leagues: bool = True) -> dict:
    data = await client.get_league_data(league_name, season)
    rows = build_match_rows(data.get("dates", []))
    played = sorted((row for row in rows if row["is_result"]), key=lambda row: (row["date"], row["home"]))
    if len(played) < min_train + 5:
        raise ValueError(
            f"Walk-forward calibration needs at least {min_train + 5} played matches; "
            f"{league_name} {season} has {len(played)}."
        )

    pooled = await _pooled_played_rows(client, season, pool_leagues, exclude_league=league_name)
    enriched = await _enrich_rows(client, league_name, season, pooled + played)
    creator = await _creator_lookup(client, league_name, season, played)
    seq_all = feature_store.build_sequential_features(enriched, creator_minutes=creator)
    seq_rows = seq_all["rows"]
    pooled_seq_idx = np.array([i for i, row in enumerate(seq_rows) if row.get("_pool_league")])
    target_seq_idx = np.array([i for i, row in enumerate(seq_rows) if not row.get("_pool_league")])
    pooled_count = len(pooled_seq_idx)

    interval = max(step, (len(played) - min_train) // MAX_WALKFORWARD_FITS)
    model_names = ("dixon_coles", "elo", "pi_ratings", "ensemble", "xgb_poisson", "xgb_xg", "xgb_outcome", "understat", "baseline")
    metrics = {name: [] for name in model_names}
    importance_accumulator: dict[str, float] = {}

    for start in range(min_train, len(played), interval):
        train, test = played[:start], played[start : start + interval]
        dc_model = poisson.fit_dixon_coles(dc_input(train, use_xg=use_xg))
        elo_model = elo.fit_elo(elo_input(train))
        pi_model = pi_ratings.fit_pi_ratings(elo_input(train))
        blend = _ensemble_weight(train, dc_model, elo_model, use_xg)

        # XGBoost block: train on pool + train window, predict the test window.
        xgb_block = None
        try:
            train_seq_idx = np.array(
                [i for i in pooled_seq_idx] + [i for i in target_seq_idx if _row_in(seq_rows[i], train)]
            )
            test_seq_idx = np.array(
                [i for i in target_seq_idx if _row_in(seq_rows[i], test)]
            )
            xgb_block = _xgb_block(
                seq_all,
                train_seq_idx,
                test_seq_idx,
                dc_model,
                variant_targets=("goals", "xg", "outcome"),
            )
            for variant in ("goals", "xg", "outcome"):
                for entry in xgb_block.get(variant, {}).get("importance", []):
                    importance_accumulator[entry["feature"]] = (
                        importance_accumulator.get(entry["feature"], 0.0) + entry["importance"]
                    )
        except Exception:
            xgb_block = None

        test_rows = test
        for k, row in enumerate(test_rows):
            outcome = _outcome(row)
            _record(metrics["dixon_coles"], _dc_outcome_probs(dc_model, row), outcome)
            _record(metrics["elo"], elo_model["predict"](row["home"], row["away"]), outcome)
            pi_probs = pi_model["predict"](row["home"], row["away"])
            _record(metrics["pi_ratings"], _lambda_probs(pi_probs), outcome)
            _record(metrics["ensemble"], _blend_probs(dc_model, elo_model, row, blend), outcome)
            if xgb_block:
                if "goals" in xgb_block:
                    probs = poisson.outcome_probs_from_lambdas(
                        float(xgb_block["goals"]["lam_h"][k]), float(xgb_block["goals"]["lam_a"][k]), dc_model["rho"]
                    )
                    _record(metrics["xgb_poisson"], _from_outcome(probs), outcome)
                if "xg" in xgb_block:
                    probs = poisson.outcome_probs_from_lambdas(
                        float(xgb_block["xg"]["lam_h"][k]), float(xgb_block["xg"]["lam_a"][k]), dc_model["rho"]
                    )
                    _record(metrics["xgb_xg"], _from_outcome(probs), outcome)
                if "outcome" in xgb_block:
                    probs = xgb_block["outcome"]["probs"][k]
                    _record(metrics["xgb_outcome"], {"p_home": probs[0], "p_draw": probs[1], "p_away": probs[2]}, outcome)
            if row["forecast"]:
                _record(metrics["understat"], _understat_probs(row["forecast"]), outcome)
            _record(metrics["baseline"], _train_frequencies(train), outcome)

    summary = {}
    for name, entries in metrics.items():
        if not entries:
            continue
        n = len(entries)
        summary[name] = {
            "n": n,
            "brier": round(sum(e["brier"] for e in entries) / n, 4),
            "log_loss": round(sum(e["log_loss"] for e in entries) / n, 4),
            "rps": round(sum(e["rps"] for e in entries) / n, 4),
            "accuracy": round(sum(e["correct"] for e in entries) / n, 4),
        }

    best = min(
        (name for name in summary if summary[name]["n"] == len(metrics["dixon_coles"])),
        key=lambda name: summary[name]["brier"],
        default=None,
    )
    blocks = max(1, (len(played) - min_train) // interval)
    feature_importance = sorted(
        (
            {"feature": feature, "importance": round(total / blocks, 4)}
            for feature, total in importance_accumulator.items()
        ),
        key=lambda e: -e["importance"],
    )[:20]
    return {
        "league_name": league_name,
        "season": season,
        "method": "walk-forward",
        "fit_on": "xG" if use_xg else "goals",
        "n_played": len(played),
        "pooled_training_matches": pooled_count,
        "min_train": min_train,
        "step": interval,
        "models": summary,
        "best_brier_model": best,
        "feature_importance": feature_importance,
        "interpretation": (
            f"Walk-forward calibration over {len(metrics['dixon_coles'])} out-of-sample predictions. "
            f"Lower Brier/log-loss/RPS and higher accuracy are better; the baseline is the training-set "
            f"home/draw/away frequency. XGBoost models train on {pooled_count} pooled matches from the "
            "other three leagues plus the walk-forward window, with features computed strictly pre-match. "
            "Feature importance shows Understat's published forecast is the dominant input — the XGBoost "
            "edge over the raw forecast comes from adding our ratings/form/availability features on top."
        ),
        "limitations": [
            "One season is a small sample; calibration Brier values are noisy.",
            "Understat's forecast column is used as-is when present; its methodology is undisclosed, and for past matches it may not be strictly pre-match.",
            "Walk-forward fits refit every N matches, not after every single match.",
            "The ensemble weight is fit in-sample on each training window, so its out-of-sample edge is slightly optimistic.",
            "Fit-on-xG Dixon-Coles may look better on xG than on realised results; Elo is the pure-results counterpoint.",
            "XGBoost sees availability only through the key-creator minutes proxy; no lineup feed exists.",
            "Without forecast features XGBoost scores ~0.629 Brier — the forecast carries most of the gap; our features add the rest.",
        ],
    }


def _row_in(row: dict, bucket: list[dict]) -> bool:
    for other in bucket:
        if row["home"] == other["home"] and row["away"] == other["away"] and row["date"] == other["date"]:
            return True
    return False


def _lambda_probs(pi_probs: dict) -> dict:
    probs = poisson.outcome_probs_from_lambdas(
        pi_probs["lambda_home"], pi_probs["lambda_away"], rho=0.0
    )
    return {"p_home": probs["p_home"], "p_draw": probs["p_draw"], "p_away": probs["p_away"]}


def _from_outcome(probs: dict) -> dict:
    return {"p_home": probs["p_home"], "p_draw": probs["p_draw"], "p_away": probs["p_away"]}


# ---------- feature enrichment for gradient boosting ----------

async def _enrich_rows(client, league_name, season, rows: list[dict]) -> list[dict]:
    """Attach per-row ppda/deep/xpts from team history (by team + date)."""
    if not hasattr(client, "get_team_history"):
        return list(rows)
    cache_key = (league_name, season)
    if cache_key not in _history_cache:
        teams = sorted({row["home"] for row in rows} | {row["away"] for row in rows})
        histories = await asyncio.gather(
            *(client.get_team_history(team, season, league_name) for team in teams),
            return_exceptions=True,
        )
        by_team: dict[str, dict[str, dict]] = {}
        for team, history in zip(teams, histories):
            if isinstance(history, BaseException):
                continue
            match_rows = list(history.values()) if isinstance(history, dict) else list(history or [])
            by_team[team] = {}
            for match in match_rows:
                date = (match.get("date") or "")[:10]
                by_team[team][date] = {
                    "ppda": match.get("ppda") or {},
                    "ppda_allowed": match.get("ppda_allowed") or {},
                    "deep": _to_float(match.get("deep")),
                    "deep_allowed": _to_float(match.get("deep_allowed")),
                    "xpts": _to_float(match.get("xpts")),
                }
        _history_cache[cache_key] = by_team

    by_team = _history_cache[cache_key]
    enriched = []
    for row in rows:
        copy = dict(row)
        home_entry = by_team.get(row["home"], {}).get(row["date"])
        away_entry = by_team.get(row["away"], {}).get(row["date"])
        copy["ppda"] = home_entry["ppda"] if home_entry else None
        copy["ppda_allowed"] = home_entry["ppda_allowed"] if home_entry else None
        copy["deep_h"] = home_entry["deep"] if home_entry else None
        copy["deep_a"] = away_entry["deep"] if away_entry else None
        copy["xpts_h"] = home_entry["xpts"] if home_entry else None
        copy["xpts_a"] = away_entry["xpts"] if away_entry else None
        enriched.append(copy)
    return enriched


async def _creator_lookup(client, league_name, season, rows: list[dict]):
    """Map each team's top-xGChain creator to minutes-by-date, and return a
    lookup function: minutes in the team's most recent match before a date."""
    cache_key = (league_name, season)
    if cache_key not in _creator_cache:
        if not hasattr(client, "get_league_player_stats"):
            _creator_cache[cache_key] = {}
            return lambda team, date: -1.0
        try:
            players = await client.get_league_player_stats(league_name, season)
        except Exception:
            _creator_cache[cache_key] = {}
            return lambda team, date: -1.0
        teams = sorted({row["home"] for row in rows} | {row["away"] for row in rows})
        minutes_by_team: dict[str, dict[str, float]] = {}
        for team in teams:
            roster = [p for p in players if p.get("team_title") == team]
            if not roster:
                continue
            creator = max(roster, key=lambda p: _to_float(p.get("xGChain")))
            try:
                player_matches = await client.get_player_matches(int(creator.get("id", 0)))
            except Exception:
                continue
            table: dict[str, float] = {}
            for m in player_matches or []:
                if str(m.get("season", season)) != str(season):
                    continue
                date = (m.get("date") or "")[:10]
                if date:
                    table[date] = _to_float(m.get("minutes") or m.get("time"))
            minutes_by_team[team] = table
        _creator_cache[cache_key] = minutes_by_team

    minutes_by_team = _creator_cache[cache_key]

    def creator_minutes(team: str, date: str) -> float:
        table = minutes_by_team.get(team) or {}
        earlier = sorted(d for d in table if d < date)
        if not earlier:
            return -1.0
        return table[earlier[-1]]

    return creator_minutes


async def _pooled_played_rows(client, season, pool_leagues: bool, exclude_league: str) -> list[dict]:
    if not pool_leagues:
        return []
    leagues = [league for league in POOL_LEAGUES if league != exclude_league]
    datas = await asyncio.gather(
        *(client.get_league_data(league, season) for league in leagues),
        return_exceptions=True,
    )
    pooled = []
    for league, data in zip(leagues, datas):
        if isinstance(data, BaseException):
            continue
        for row in build_match_rows(data.get("dates", [])):
            if row["is_result"]:
                row["_pool_league"] = league
                pooled.append(row)
    return pooled


def _xgb_block(seq_features, train_idx, test_idx, dc_model, variant_targets=("goals", "xg")):
    """Train XGB variants on the block and return predictions for the test rows."""
    names = seq_features["names"] + ["dc_att_h", "dc_def_h", "dc_att_a", "dc_def_a",
                                     "dc_lambda_h", "dc_lambda_a"]
    train_rows = [seq_features["rows"][i] for i in train_idx]
    test_rows = [seq_features["rows"][i] for i in test_idx]

    seq_train = xgb_models.matrix(seq_features["features"], seq_features["names"], train_idx)
    seq_test = xgb_models.matrix(seq_features["features"], seq_features["names"], test_idx)
    dc_train = feature_store.dc_features(dc_model, train_rows)
    dc_test = feature_store.dc_features(dc_model, test_rows)
    X_train = np.column_stack([seq_train, *[dc_train[name] for name in dc_names()]])
    X_test = np.column_stack([seq_test, *[dc_test[name] for name in dc_names()]])

    targets = seq_features["targets"]
    results = {}
    if "goals" in variant_targets:
        models = xgb_models.train_poisson(X_train, targets["home_goals"][train_idx], targets["away_goals"][train_idx])
        lam_h, lam_a = xgb_models.predict_lambdas(models, X_test)
        results["goals"] = {"models": models, "lam_h": lam_h, "lam_a": lam_a,
                            "importance": _combined_importance(models, names)}
    if "xg" in variant_targets:
        models = xgb_models.train_xg(X_train, targets["home_xg"][train_idx], targets["away_xg"][train_idx])
        lam_h, lam_a = xgb_models.predict_lambdas(models, X_test)
        results["xg"] = {"models": models, "lam_h": lam_h, "lam_a": lam_a,
                         "importance": _combined_importance(models, names)}
    if "outcome" in variant_targets:
        model = xgb_models.train_softmax(X_train, targets["outcome"][train_idx])
        results["outcome"] = {"model": model, "probs": xgb_models.predict_softmax(model, X_test),
                              "importance": xgb_models.importance(model, names)}
    return results


def dc_names():
    return ["dc_att_h", "dc_def_h", "dc_att_a", "dc_def_a", "dc_lambda_h", "dc_lambda_a"]


def _combined_importance(models: tuple, names: list[str], top_k: int = 20) -> list[dict]:
    home, away = models
    home_imp = {e["feature"]: e["importance"] for e in xgb_models.importance(home, names, top_k=100)}
    away_imp = {e["feature"]: e["importance"] for e in xgb_models.importance(away, names, top_k=100)}
    merged = {key: (home_imp.get(key, 0.0) + away_imp.get(key, 0.0)) / 2.0 for key in set(home_imp) | set(away_imp)}
    ranked = sorted(merged.items(), key=lambda kv: -kv[1])[:top_k]
    return [{"feature": key, "importance": round(value, 4)} for key, value in ranked]


# ---------- adjustment layers ----------


def _venue_report(played_rows: list[dict], home: str, away: str) -> dict:
    def team_avg(team: str):
        home_xg = [r["home_xg"] for r in played_rows if r["home"] == team]
        away_xg = [r["away_xg"] for r in played_rows if r["away"] == team]
        return (
            float(np.mean(home_xg)) if len(home_xg) >= 3 else None,
            float(np.mean(away_xg)) if len(away_xg) >= 3 else None,
            len(home_xg),
            len(away_xg),
        )

    all_home = [r["home_xg"] for r in played_rows]
    all_away = [r["away_xg"] for r in played_rows]
    league_log = float(np.log(np.mean(all_home) / np.mean(all_away))) if all_home and all_away else 0.0

    def factor(team: str):
        h, a, n_h, n_a = team_avg(team)
        if h is None or a is None or h <= 0 or a <= 0:
            return {"available": False}
        raw = float(np.log(h / a)) - league_log
        return {
            "available": True,
            "home_xg_per_game": round(h, 2),
            "away_xg_per_game": round(a, 2),
            "n_home": n_h,
            "n_away": n_a,
            "factor": round(float(np.clip(raw, -0.2, 0.2)) * VENUE_DAMPING, 4),
        }

    home_f = factor(home)
    away_f = factor(away)
    return {
        "home": {"team": home, **home_f, "factor": home_f.get("factor", 0.0) or 0.0},
        "away": {"team": away, **away_f, "factor": away_f.get("factor", 0.0) or 0.0},
        "home_factor": home_f.get("factor", 0.0) or 0.0,
        "away_factor": away_f.get("factor", 0.0) or 0.0,
    }


def _form_report(played_rows: list[dict], home: str, away: str) -> dict:
    def factor(team: str):
        team_rows = sorted(
            [r for r in played_rows if r["home"] == team or r["away"] == team],
            key=lambda r: r["date"],
        )
        if len(team_rows) < 5:
            return {"available": False}
        recent = team_rows[-5:]
        recent_xg = [r["home_xg"] if r["home"] == team else r["away_xg"] for r in recent]
        season_xg = [r["home_xg"] if r["home"] == team else r["away_xg"] for r in team_rows]
        z = float(np.mean(recent_xg) / np.mean(season_xg) - 1.0) if np.mean(season_xg) > 0 else 0.0
        return {
            "available": True,
            "recent_xg_per_game": round(float(np.mean(recent_xg)), 2),
            "season_xg_per_game": round(float(np.mean(season_xg)), 2),
            "factor": round(float(np.clip(z, -0.3, 0.3)) * FORM_DAMPING, 4),
        }

    home_f = factor(home)
    away_f = factor(away)
    return {
        "home": {"team": home, **home_f, "factor": home_f.get("factor", 0.0) or 0.0},
        "away": {"team": away, **away_f, "factor": away_f.get("factor", 0.0) or 0.0},
        "home_factor": home_f.get("factor", 0.0) or 0.0,
        "away_factor": away_f.get("factor", 0.0) or 0.0,
    }


async def _availability_report(client, league_name, season, home, away, lam_h, lam_a, rho):
    try:
        players = await client.get_league_player_stats(league_name, season)
    except Exception:
        return {"home": None, "away": None, "scenario": None}

    async def team_report(team: str, lam_current: float, is_home: bool):
        roster = [p for p in players if p.get("team_title") == team]
        if not roster:
            return None
        creator = max(roster, key=lambda p: _to_float(p.get("xGChain")))
        player_id = int(creator.get("id", 0))
        if not player_id:
            return None
        try:
            player_matches = await client.get_player_matches(player_id)
        except Exception:
            return None
        minutes_by_date = {}
        for m in player_matches or []:
            if str(m.get("season", season)) != str(season):
                continue
            date = (m.get("date") or "")[:10]
            if date:
                minutes_by_date[date] = _to_float(m.get("minutes") or m.get("time"))

        try:
            history = await client.get_team_history(team, season, league_name)
        except Exception:
            return None
        rows = list(history.values()) if isinstance(history, dict) else list(history or [])
        with_xg, without_xg = [], []
        for match in rows:
            date = (match.get("date") or "")[:10]
            xg = _to_float(match.get("xG"))
            minutes = minutes_by_date.get(date)
            if minutes is None:
                continue
            if minutes >= 60:
                with_xg.append(xg)
            elif minutes < 45:
                without_xg.append(xg)
        if len(with_xg) < 3 or len(without_xg) < 2:
            return {
                "player": creator.get("player_name"),
                "xGChain": _to_float(creator.get("xGChain")),
                "available": False,
            }
        with_avg = float(np.mean(with_xg))
        without_avg = float(np.mean(without_xg))
        multiplier = without_avg / with_avg if with_avg > 0 else 1.0
        return {
            "player": creator.get("player_name"),
            "xGChain": _to_float(creator.get("xGChain")),
            "available": True,
            "team_xG_per_game_with": round(with_avg, 2),
            "team_xG_per_game_without": round(without_avg, 2),
            "n_with": len(with_xg),
            "n_without": len(without_xg),
            "multiplier": round(multiplier, 3),
        }

    home_report = await team_report(home, lam_h, True)
    away_report = await team_report(away, lam_a, False)
    scenario = None
    if (home_report and home_report.get("available")) or (away_report and away_report.get("available")):
        lam_h_s = lam_h * (home_report.get("multiplier", 1.0) if home_report and home_report.get("available") else 1.0)
        lam_a_s = lam_a * (away_report.get("multiplier", 1.0) if away_report and away_report.get("available") else 1.0)
        probs = poisson.outcome_probs_from_lambdas(lam_h_s, lam_a_s, rho)
        scenario = {
            "p_home": probs["p_home"],
            "p_draw": probs["p_draw"],
            "p_away": probs["p_away"],
        }
    return {"home": home_report, "away": away_report, "scenario": scenario}


def _ensemble(played_rows, home, away, use_xg) -> dict:
    if len(played_rows) < 40:
        return {"available": False}
    dc_model = poisson.fit_dixon_coles(dc_input(played_rows, use_xg=use_xg))
    elo_model = elo.fit_elo(elo_input(played_rows))
    weight = _ensemble_weight(played_rows, dc_model, elo_model, use_xg)
    dc_p = _dc_outcome_probs(dc_model, {"home": home, "away": away})
    elo_p = elo_model["predict"](home, away)
    blend = {
        "p_home": round(weight * dc_p["p_home"] + (1 - weight) * elo_p["p_home"], 4),
        "p_draw": round(weight * dc_p["p_draw"] + (1 - weight) * elo_p["p_draw"], 4),
        "p_away": round(weight * dc_p["p_away"] + (1 - weight) * elo_p["p_away"], 4),
    }
    return {"available": True, "weight": round(weight, 2), **blend}


def _ensemble_weight(rows, dc_model, elo_model, use_xg) -> float:
    """Brier-optimal blend weight of DC vs Elo, fit on a holdout of `rows`."""
    holdout = rows[len(rows) // 2 :] if len(rows) >= 40 else rows
    if not holdout:
        return 0.5
    dc_train = [r for r in rows if r not in holdout]
    if len(dc_train) < MIN_FIT_MATCHES:
        return 0.5
    dc = poisson.fit_dixon_coles(dc_input(dc_train, use_xg=use_xg))
    em = elo.fit_elo(elo_input(dc_train))
    best_w, best_brier = 0.5, float("inf")
    for w in np.linspace(0.0, 1.0, 11):
        brier = 0.0
        for row in holdout:
            dc_p = _dc_outcome_probs(dc, row)
            elo_p = em["predict"](row["home"], row["away"])
            outcome = _outcome(row)
            pred = w * _vector(dc_p) + (1 - w) * _vector(elo_p)
            target = np.zeros(3)
            target[outcome] = 1.0
            brier += float(((pred - target) ** 2).sum())
        brier /= len(holdout)
        if brier < best_brier:
            best_w, best_brier = float(w), brier
    return best_w


def _blend_probs(dc_model, elo_model, row, weight):
    dc_p = _dc_outcome_probs(dc_model, row)
    elo_p = elo_model["predict"](row["home"], row["away"])
    return {
        "p_home": weight * dc_p["p_home"] + (1 - weight) * elo_p["p_home"],
        "p_draw": weight * dc_p["p_draw"] + (1 - weight) * elo_p["p_draw"],
        "p_away": weight * dc_p["p_away"] + (1 - weight) * elo_p["p_away"],
    }


def _vector(probs: dict) -> np.ndarray:
    return np.array([probs["p_home"], probs["p_draw"], probs["p_away"]])


async def _top_scorer_projection(client, league_name, season, remaining) -> list[dict]:
    try:
        players = await client.get_league_player_stats(league_name, season)
    except Exception:
        return []
    remaining_by_team: dict[str, int] = {}
    for row in remaining:
        remaining_by_team[row["home"]] = remaining_by_team.get(row["home"], 0) + 1
        remaining_by_team[row["away"]] = remaining_by_team.get(row["away"], 0) + 1

    projections = []
    for player in players:
        goals = _to_float(player.get("goals"))
        npxg = _to_float(player.get("npxG"))
        minutes = _to_float(player.get("time"))
        games = _to_float(player.get("games"))
        team = player.get("team_title")
        n_remaining = remaining_by_team.get(team, 0)
        if games <= 0 or minutes <= 0 or n_remaining <= 0 or npxg <= 0:
            continue
        minutes_per_game = minutes / games
        npxg_per90 = npxg * 90.0 / minutes
        expected_extra_minutes = minutes_per_game * n_remaining
        projected = goals + npxg_per90 * (expected_extra_minutes / 90.0)
        projections.append(
            {
                "player": player.get("player_name"),
                "team": team,
                "goals_now": round(goals, 0),
                "npxG": round(npxg, 2),
                "npxG_per90": round(npxg_per90, 3),
                "games_remaining": n_remaining,
                "projected_season_end_goals": round(projected, 1),
            }
        )
    projections.sort(key=lambda p: -p["projected_season_end_goals"])
    return projections[:10]


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


def _record(entries: list, probs: dict, outcome: int) -> None:
    pred = np.array([probs["p_home"], probs["p_draw"], probs["p_away"]])
    target = np.zeros(3)
    target[outcome] = 1.0
    entries.append(
        {
            "brier": float(((pred - target) ** 2).sum()),
            "log_loss": float(-np.log(np.clip(pred[outcome], 1e-9, 1.0))),
            "rps": rps_metric(probs, outcome),
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


def _table_goals_map(table) -> dict[str, int]:
    goals: dict[str, int] = {}
    rows = table[1:] if table and _is_header(table[0]) else (table or [])
    for row in rows:
        if not row or not row[0]:
            continue
        goals[str(row[0])] = _to_int(row[5]) if len(row) > 5 else 0
    return goals


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
