from __future__ import annotations

from typing import Iterable

from .percentiles import to_float
from ._shared import HONEST_TEAM_LIMITATIONS, round_value, ppda_ratio


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round_value(sum(values) / len(values))


def style_profile(team_row: list) -> dict:
    """PPDA + xG/xGA + deeps from a league_table team row.

    team_row column layout (matches get_league_table):
      [Team, M, W, D, L, G, GA, PTS, xG, NPxG, xGA, NPxGA, NPxGD, PPDA, OPPDA, DC, ODC, xPTS]
    """
    matches = to_float(team_row[1])
    xg = to_float(team_row[8])
    xga = to_float(team_row[10])
    npxgd = to_float(team_row[12])
    ppda = to_float(team_row[13])
    oppda = to_float(team_row[14])
    deep = to_float(team_row[15])
    deep_allowed = to_float(team_row[16])
    xpts = to_float(team_row[17])

    return {
        "team": team_row[0],
        "matches": int(matches),
        "xG_per_game": round_value(xg / matches if matches else 0),
        "xGA_per_game": round_value(xga / matches if matches else 0),
        "xG_diff_per_game": round_value((xg - xga) / matches if matches else 0),
        "npxGD": round_value(npxgd),
        "PPDA": round_value(ppda),
        "OPPDA": round_value(oppda),
        "deep_completions": int(deep),
        "deep_completions_allowed": int(deep_allowed),
        "xPTS": round_value(xpts),
        "interpretation": (
            "PPDA/OPPDA: passes per defensive action for and against — lower PPDA = more intense "
            "press. xG/xGA per game are the canonical attacking/defending process. deep_completions "
            "proxy final-third penetration (no locations are available, so no penetration map)."
        ),
        "limitations": HONEST_TEAM_LIMITATIONS,
    }


def ppda_home_away(team_history: list[dict]) -> dict:
    """Split pressing intensity by home/away, mirroring the canonical KU Leuven view.

    Consumes the `history` list from get_league_data teams[team].history — these
    rows carry `ppda` {att, def} and `h_a` ('h'/'a') per match.
    """
    home_ppdas = []
    away_ppdas = []
    for m in team_history or []:
        ppda = m.get("ppda", {})
        if not isinstance(ppda, dict):
            continue
        side = m.get("h_a")
        if side == "h":
            home_ppdas.append(ppda_ratio(ppda))
        elif side == "a":
            away_ppdas.append(ppda_ratio(ppda))

    return {
        "ppda_home": average(home_ppdas),
        "ppda_away": average(away_ppdas),
        "matches_home": len(home_ppdas),
        "matches_away": len(away_ppdas),
        "interpretation": (
            "Home vs away PPDA reveals whether a team presses higher up at home. "
            "Understat `ppda` is game-state-dependent; compare to season baseline, not in isolation."
        ),
        "limitations": HONEST_TEAM_LIMITATIONS,
    }


def form_momentum(team_history: list[dict], window: int = 5) -> dict:
    """Rolling xGD and momentum from per-match league history rows.

    `team_history` rows are the per-match history entries from get_league_data
    (carry `xG`, `xGA`, `ppda`, `date`). This is the honest form metric — xGD
    strips scoreline noise and predicts future points better than goals.
    """
    rows = sorted(
        [r for r in (team_history or []) if r.get("xG") is not None and r.get("xGA") is not None],
        key=lambda r: (r.get("date") or "")[:19],
    )

    per_match_xgd: list[float] = [
        round_value(to_float(m.get("xG", 0)) - to_float(m.get("xGA", 0))) for m in rows
    ]

    if not per_match_xgd:
        return {"rolling_xgd": [], "momentum": [], "season_mean_xGD": None, "recent_xGD": None}

    rolling = []
    n = len(per_match_xgd)
    for i in range(n):
        start = max(0, i - window + 1)
        rolling.append({
            "match_index": i + 1,
            "date": (rows[i].get("date") or "")[:10],
            "rolling_xGD": round_value(sum(per_match_xgd[start:i + 1]) / (i - start + 1)),
        })

    season_mean = sum(per_match_xgd) / n
    momentum = 0.0
    momentum_series = []
    for i, value in enumerate(per_match_xgd):
        momentum += value - season_mean
        momentum_series.append({"match_index": i + 1, "date": (rows[i].get("date") or "")[:10], "momentum": round_value(momentum)})

    return {
        "rolling_xgd": rolling,
        "momentum": momentum_series,
        "season_mean_xGD": round_value(season_mean),
        "recent_xGD": rolling[-1]["rolling_xGD"] if rolling else None,
        "interpretation": (
            "Rolling xG-minus-xGA over the last N matches is the honest form signal — it strips "
            "scoreline noise. Momentum is a CUSUM of per-match xGD above season mean; positive "
            "stretches = running hot."
        ),
    }


def situational_xg_share(team_shots: list[dict], team_name: str) -> dict:
    """Share of team xG coming from each `situation` (OpenPlay/FromCorner/SetPiece/...)."""
    own_shots = [s for s in team_shots if s.get("h_team") == team_name or s.get("a_team") == team_name]
    by_situation: dict[str, float] = {}
    for s in own_shots:
        situation = s.get("situation", "Unknown")
        by_situation[situation] = round_value(by_situation.get(situation, 0.0) + to_float(s.get("xG", 0)))

    total = sum(by_situation.values())
    shares = {
        situation: {
            "xG": val,
            "share": round_value(val / total if total else 0),
        }
        for situation, val in sorted(by_situation.items(), key=lambda kv: -kv[1])
    }
    return {
        "team": team_name,
        "own_shots": len(own_shots),
        "by_situation": shares,
        "set_piece_xG_share": round_value(
            (by_situation.get("FromCorner", 0) + by_situation.get("SetPiece", 0) + by_situation.get("DirectFreekick", 0)) / total
            if total else 0
        ),
        "interpretation": (
            "Fraction of team xG by situation reveals set-piece dependency vs open-play identity. "
            "Useful for scouting style; set-piece specialists matter, but set-piece shares are also "
            "opponent-dependent."
        ),
    }


def team_report(
    team_row: list,
    team_history: list[dict] | None = None,
    team_shots: list[dict] | None = None,
) -> dict:
    return {
        "style": style_profile(team_row),
        "ppda_home_away": ppda_home_away(team_history or []),
        "form_momentum": form_momentum(team_history or [], window=5),
        "situational_xg_share": situational_xg_share(team_shots or [], team_row[0]) if team_shots else None,
        "limitations": HONEST_TEAM_LIMITATIONS,
    }
