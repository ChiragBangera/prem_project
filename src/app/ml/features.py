from __future__ import annotations

"""Pre-match feature store for gradient-boosted models.

Every feature for match t is computed from information available BEFORE t:
rolling form buffers update only after a match, Elo/pi-ratings are taken from
their per-match pre-update histories, head-to-head and points/rank accumulate
from earlier matches only. Dixon-Coles features are added per walk-forward
block by the engine (they are block-train-fitted, never whole-season).
"""

import numpy as np

from . import elo, pi_ratings

ELO_K = 24.0
ELO_HOME_ADVANTAGE = 65.0
ELO_INITIAL = 1500.0


def build_sequential_features(
    rows: list[dict],
    creator_minutes: callable | None = None,
) -> dict:
    """Build leakage-free per-match features over dated `rows` (played only).

    Returns {"features": {name: np.array}, "names": [...], "targets": {...},
    "rows": rows, "team_ids": {...}}.
    """
    ordered = sorted(rows, key=lambda r: (r["date"], r["home"], r["away"]))
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    team_id = {team: i for i, team in enumerate(teams)}
    n = len(ordered)

    feat = {
        "team_h": np.zeros(n), "team_a": np.zeros(n),
        "elo_h": np.zeros(n), "elo_a": np.zeros(n),
        "pi_att_h": np.zeros(n), "pi_def_h": np.zeros(n),
        "pi_att_a": np.zeros(n), "pi_def_a": np.zeros(n),
        "xg_for_3_h": np.zeros(n), "xg_against_3_h": np.zeros(n),
        "xg_for_5_h": np.zeros(n), "xg_against_5_h": np.zeros(n),
        "goals_for_3_h": np.zeros(n), "goals_against_3_h": np.zeros(n),
        "xg_for_3_a": np.zeros(n), "xg_against_3_a": np.zeros(n),
        "xg_for_5_a": np.zeros(n), "xg_against_5_a": np.zeros(n),
        "goals_for_3_a": np.zeros(n), "goals_against_3_a": np.zeros(n),
        "ppda_5_h": np.zeros(n), "ppda_5_a": np.zeros(n),
        "deep_5_h": np.zeros(n), "deep_5_a": np.zeros(n),
        "xpts_5_h": np.zeros(n), "xpts_5_a": np.zeros(n),
        "points_h": np.zeros(n), "points_a": np.zeros(n),
        "rank_h": np.zeros(n), "rank_a": np.zeros(n),
        "rest_days_h": np.zeros(n), "rest_days_a": np.zeros(n),
        "h2h_home_wins": np.zeros(n), "h2h_draws": np.zeros(n),
        "h2h_away_wins": np.zeros(n), "h2h_xg_diff": np.zeros(n),
        "stage": np.zeros(n),
        "forecast_w": np.zeros(n), "forecast_d": np.zeros(n), "forecast_l": np.zeros(n),
        "creator_last_min_h": np.zeros(n), "creator_last_min_a": np.zeros(n),
    }
    names = list(feat.keys())

    elo_ratings: dict[str, float] = {}
    pi_fit = pi_ratings.fit_pi_ratings(rows)
    pi_history = {
        (entry["date"], entry["home"]): entry for entry in pi_fit["history"]
    }

    rolling: dict[str, dict] = {team: {
        "xg_for": [], "xg_against": [], "goals_for": [], "goals_against": [],
        "ppda": [], "deep": [], "xpts": [],
    } for team in teams}
    points = {team: 0 for team in teams}
    last_played = {team: None for team in teams}
    h2h: dict[tuple, dict] = {}

    for i, row in enumerate(ordered):
        h, a = row["home"], row["away"]
        date = row["date"]
        feat["team_h"][i] = team_id[h]
        feat["team_a"][i] = team_id[a]

        eh = elo_ratings.get(h, ELO_INITIAL)
        ea = elo_ratings.get(a, ELO_INITIAL)
        feat["elo_h"][i] = eh
        feat["elo_a"][i] = ea

        pi_entry = pi_history.get((date, h))
        if pi_entry is not None:
            feat["pi_att_h"][i] = pi_entry["attack_home"]
            feat["pi_def_h"][i] = pi_entry["defense_home"]
            feat["pi_att_a"][i] = pi_entry["attack_away"]
            feat["pi_def_a"][i] = pi_entry["defense_away"]

        def roll(team: str, side: str):
            buf = rolling[team]
            if buf["xg_for"]:
                feat[f"xg_for_3_{side}"][i] = float(np.mean(buf["xg_for"][-3:]))
                feat[f"xg_against_3_{side}"][i] = float(np.mean(buf["xg_against"][-3:]))
                feat[f"xg_for_5_{side}"][i] = float(np.mean(buf["xg_for"][-5:]))
                feat[f"xg_against_5_{side}"][i] = float(np.mean(buf["xg_against"][-5:]))
                feat[f"goals_for_3_{side}"][i] = float(np.mean(buf["goals_for"][-3:]))
                feat[f"goals_against_3_{side}"][i] = float(np.mean(buf["goals_against"][-3:]))
                feat[f"ppda_5_{side}"][i] = float(np.mean(buf["ppda"][-5:]))
                feat[f"deep_5_{side}"][i] = float(np.mean(buf["deep"][-5:]))
                feat[f"xpts_5_{side}"][i] = float(np.mean(buf["xpts"][-5:]))

        roll(h, "h")
        roll(a, "a")

        feat["points_h"][i] = points[h]
        feat["points_a"][i] = points[a]
        ranks = sorted(points, key=lambda t: -points[t])
        feat["rank_h"][i] = ranks.index(h) + 1
        feat["rank_a"][i] = ranks.index(a) + 1

        if last_played[h]:
            feat["rest_days_h"][i] = max(0, _days(date) - _days(last_played[h]))
        if last_played[a]:
            feat["rest_days_a"][i] = max(0, _days(date) - _days(last_played[a]))

        prior = h2h.get((h, a), {"hw": 0, "dr": 0, "aw": 0, "xgd": 0.0})
        feat["h2h_home_wins"][i] = prior["hw"]
        feat["h2h_draws"][i] = prior["dr"]
        feat["h2h_away_wins"][i] = prior["aw"]
        feat["h2h_xg_diff"][i] = prior["xgd"]

        feat["stage"][i] = i + 1
        forecast = row.get("forecast") or {}
        feat["forecast_w"][i] = _f(forecast.get("w")) or 0.333
        feat["forecast_d"][i] = _f(forecast.get("d")) or 0.333
        feat["forecast_l"][i] = _f(forecast.get("l")) or 0.333
        total = feat["forecast_w"][i] + feat["forecast_d"][i] + feat["forecast_l"][i]
        if total > 1.5:
            feat["forecast_w"][i] /= 100.0
            feat["forecast_d"][i] /= 100.0
            feat["forecast_l"][i] /= 100.0
        total = feat["forecast_w"][i] + feat["forecast_d"][i] + feat["forecast_l"][i]
        if total > 0:
            feat["forecast_w"][i] /= total
            feat["forecast_d"][i] /= total
            feat["forecast_l"][i] /= total

        if creator_minutes is not None:
            feat["creator_last_min_h"][i] = creator_minutes(h, date)
            feat["creator_last_min_a"][i] = creator_minutes(a, date)

        # ---- post-match updates (nothing after this line may inform row i) ----
        if not row.get("is_result", True):
            continue
        for team, xg_for, xg_against, goals_for, goals_against, ppda, deep, xpts in (
            (h, row["home_xg"], row["away_xg"], row["home_goals"], row["away_goals"], _ppda(row, "ppda"), row.get("deep_h", np.nan) or 0.0, row.get("xpts_h", np.nan) or 0.0),
            (a, row["away_xg"], row["home_xg"], row["away_goals"], row["home_goals"], _ppda(row, "ppda_allowed"), row.get("deep_a", np.nan) or 0.0, row.get("xpts_a", np.nan) or 0.0),
        ):
            buf = rolling[team]
            for key, value in (("xg_for", xg_for), ("xg_against", xg_against),
                               ("goals_for", goals_for), ("goals_against", goals_against),
                               ("ppda", ppda), ("deep", deep), ("xpts", xpts)):
                buf[key].append(value)
                if len(buf[key]) > 5:
                    buf[key].pop(0)

        points[h] += 3 if row["home_goals"] > row["away_goals"] else (1 if row["home_goals"] == row["away_goals"] else 0)
        points[a] += 3 if row["away_goals"] > row["home_goals"] else (1 if row["home_goals"] == row["away_goals"] else 0)
        last_played[h] = date
        last_played[a] = date

        prior = h2h.setdefault((h, a), {"hw": 0, "dr": 0, "aw": 0, "xgd": 0.0})
        prior["xgd"] += row["home_xg"] - row["away_xg"]
        if row["home_goals"] > row["away_goals"]:
            prior["hw"] += 1
        elif row["home_goals"] < row["away_goals"]:
            prior["aw"] += 1
        else:
            prior["dr"] += 1

        expected_h = elo.expected_share(eh + ELO_HOME_ADVANTAGE, ea)
        score = 1.0 if row["home_goals"] > row["away_goals"] else (0.5 if row["home_goals"] == row["away_goals"] else 0.0)
        elo_ratings[h] = eh + ELO_K * (score - expected_h)
        elo_ratings[a] = ea - ELO_K * (score - expected_h)

    return {
        "features": feat,
        "names": names,
        "rows": ordered,
        "team_ids": team_id,
        "targets": {
            "home_goals": np.array([r["home_goals"] for r in ordered], dtype=float),
            "away_goals": np.array([r["away_goals"] for r in ordered], dtype=float),
            "home_xg": np.array([r["home_xg"] for r in ordered], dtype=float),
            "away_xg": np.array([r["away_xg"] for r in ordered], dtype=float),
            "outcome": np.array([_outcome(r) for r in ordered], dtype=int),
        },
    }


def dc_features(model: dict, rows: list[dict]) -> dict[str, np.ndarray]:
    """Dixon-Coles block features for rows, using a model fit on the block's train data."""
    teams = model["teams"]
    idx = {team: i for i, team in enumerate(teams)}
    n = len(rows)
    out = {
        "dc_att_h": np.zeros(n), "dc_def_h": np.zeros(n),
        "dc_att_a": np.zeros(n), "dc_def_a": np.zeros(n),
        "dc_lambda_h": np.zeros(n), "dc_lambda_a": np.zeros(n),
    }
    for k, row in enumerate(rows):
        i = idx.get(row["home"])
        j = idx.get(row["away"])
        if i is None or j is None:
            continue
        lam_h = float(np.exp(model["attack"][i] - model["defense"][j] + model["home_advantage"]))
        lam_a = float(np.exp(model["attack"][j] - model["defense"][i]))
        out["dc_att_h"][k] = model["attack"][i]
        out["dc_def_h"][k] = model["defense"][i]
        out["dc_att_a"][k] = model["attack"][j]
        out["dc_def_a"][k] = model["defense"][j]
        out["dc_lambda_h"][k] = lam_h
        out["dc_lambda_a"][k] = lam_a
    return out


FEATURE_EXPLANATIONS = {
    "team_h": ("Team (home)", "Team identity of the home side."),
    "team_a": ("Team (away)", "Team identity of the away side."),
    "elo_h": ("Elo (home)", "Home team's Elo rating before the match."),
    "elo_a": ("Elo (away)", "Away team's Elo rating before the match."),
    "pi_att_h": ("pi attack (home)", "Home team's pi-rating attack strength before the match."),
    "pi_def_h": ("pi defence (home)", "Home team's pi-rating defence strength before the match."),
    "pi_att_a": ("pi attack (away)", "Away team's pi-rating attack strength before the match."),
    "pi_def_a": ("pi defence (away)", "Away team's pi-rating defence strength before the match."),
    "xg_for_3_h": ("xG for, last 3 (home)", "Home team's mean xG per game over its previous 3 matches."),
    "xg_against_3_h": ("xG against, last 3 (home)", "Home team's mean xG conceded per game over its previous 3."),
    "xg_for_5_h": ("xG for, last 5 (home)", "Home team's mean xG per game over its previous 5 matches."),
    "xg_against_5_h": ("xG against, last 5 (home)", "Home team's mean xG conceded per game over its previous 5."),
    "goals_for_3_h": ("goals for, last 3 (home)", "Home team's mean goals per game over its previous 3."),
    "goals_against_3_h": ("goals against, last 3 (home)", "Home team's mean goals conceded per game over its previous 3."),
    "xg_for_3_a": ("xG for, last 3 (away)", "Away team's mean xG per game over its previous 3."),
    "xg_against_3_a": ("xG against, last 3 (away)", "Away team's mean xG conceded per game over its previous 3."),
    "xg_for_5_a": ("xG for, last 5 (away)", "Away team's mean xG per game over its previous 5."),
    "xg_against_5_a": ("xG against, last 5 (away)", "Away team's mean xG conceded per game over its previous 5."),
    "goals_for_3_a": ("goals for, last 3 (away)", "Away team's mean goals per game over its previous 3."),
    "goals_against_3_a": ("goals against, last 3 (away)", "Away team's mean goals conceded per game over its previous 3."),
    "ppda_5_h": ("PPDA, last 5 (home)", "Home team's mean PPDA over its previous 5 matches."),
    "ppda_5_a": ("PPDA, last 5 (away)", "Away team's mean PPDA over its previous 5 matches."),
    "deep_5_h": ("deep completions, last 5 (home)", "Home team's mean deep completions per game over its previous 5."),
    "deep_5_a": ("deep completions, last 5 (away)", "Away team's mean deep completions per game over its previous 5."),
    "xpts_5_h": ("xPTS, last 5 (home)", "Home team's mean expected points per game over its previous 5."),
    "xpts_5_a": ("xPTS, last 5 (away)", "Away team's mean expected points per game over its previous 5."),
    "points_h": ("points (home)", "Home team's points before the match."),
    "points_a": ("points (away)", "Away team's points before the match."),
    "rank_h": ("table rank (home)", "Home team's table position before the match."),
    "rank_a": ("table rank (away)", "Away team's table position before the match."),
    "rest_days_h": ("rest days (home)", "Days since the home team's previous match."),
    "rest_days_a": ("rest days (away)", "Days since the away team's previous match."),
    "h2h_home_wins": ("H2H home wins", "Home team's wins over this opponent in prior meetings this season."),
    "h2h_draws": ("H2H draws", "Draws between these teams in prior meetings this season."),
    "h2h_away_wins": ("H2H away wins", "Away team's wins over this opponent in prior meetings this season."),
    "h2h_xg_diff": ("H2H xG diff", "Cumulative xG difference in prior meetings between these teams."),
    "stage": ("season stage", "Match index within the season."),
    "forecast_w": ("Understat forecast (home win)", "Understat's published pre-match home-win probability for this fixture."),
    "forecast_d": ("Understat forecast (draw)", "Understat's published pre-match draw probability for this fixture."),
    "forecast_l": ("Understat forecast (away win)", "Understat's published pre-match away-win probability for this fixture."),
    "creator_last_min_h": ("key creator minutes (home)", "Minutes the home team's top xGChain creator played in their most recent match."),
    "creator_last_min_a": ("key creator minutes (away)", "Minutes the away team's top xGChain creator played in their most recent match."),
    "dc_att_h": ("DC attack (home)", "Dixon-Coles attack strength (block-fitted)."),
    "dc_def_h": ("DC defence (home)", "Dixon-Coles defence strength (block-fitted)."),
    "dc_att_a": ("DC attack (away)", "Dixon-Coles attack strength (block-fitted)."),
    "dc_def_a": ("DC defence (away)", "Dixon-Coles defence strength (block-fitted)."),
    "dc_lambda_h": ("DC lambda home", "Dixon-Coles expected goals for the home side."),
    "dc_lambda_a": ("DC lambda away", "Dixon-Coles expected goals for the away side."),
}


def _ppda(row: dict, key: str) -> float:
    value = row.get(key) or {}
    att = _f(value.get("att"))
    defn = _f(value.get("def"))
    if not defn:
        return 0.0
    return att / defn


def _outcome(row: dict) -> int:
    if row["home_goals"] > row["away_goals"]:
        return 0
    if row["home_goals"] < row["away_goals"]:
        return 2
    return 1


def _days(date: str) -> int:
    try:
        y, m, d = map(int, date.split("-")[:3])
        return y * 372 + m * 31 + d
    except (ValueError, AttributeError):
        return 0


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
