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
    wins = to_float(team_row[2])
    draws = to_float(team_row[3])
    losses = to_float(team_row[4])
    goals = to_float(team_row[5])
    goals_against = to_float(team_row[6])
    points = to_float(team_row[7])
    xg = to_float(team_row[8])
    npxg = to_float(team_row[9])
    xga = to_float(team_row[10])
    npxga = to_float(team_row[11])
    npxgd = to_float(team_row[12])
    ppda = to_float(team_row[13])
    oppda = to_float(team_row[14])
    deep = to_float(team_row[15])
    deep_allowed = to_float(team_row[16])
    xpts = to_float(team_row[17])

    return {
        "team": team_row[0],
        "matches": int(matches),
        "wins": int(wins),
        "draws": int(draws),
        "losses": int(losses),
        "goals": int(goals),
        "goals_against": int(goals_against),
        "points": int(points),
        "xG": round_value(xg),
        "npxG": round_value(npxg),
        "xGA": round_value(xga),
        "npxGA": round_value(npxga),
        "xG_per_game": round_value(xg / matches if matches else 0),
        "xGA_per_game": round_value(xga / matches if matches else 0),
        "xG_diff_per_game": round_value((xg - xga) / matches if matches else 0),
        "npxGD": round_value(npxgd),
        "PPDA": round_value(ppda),
        "OPPDA": round_value(oppda),
        "deep_completions": int(deep),
        "deep_completions_allowed": int(deep_allowed),
        "xPTS": round_value(xpts),
        "xPTS_gap": round_value(points - xpts),
        "g_minus_xg": round_value(goals - xg),
        "xga_minus_ga": round_value(xga - goals_against),
        "goal_difference": int(goals - goals_against),
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
    league_histories: dict[str, list[dict]] | None = None,
) -> dict:
    history = team_history or []
    return {
        "style": style_profile(team_row),
        "ppda_home_away": ppda_home_away(history),
        "form_momentum": form_momentum(history, window=5),
        "situational_xg_share": situational_xg_share(team_shots or [], team_row[0]) if team_shots else None,
        "position_trend": position_trend(history, league_histories) if league_histories else None,
        "half_split": half_split(history),
        "home_away_splits": home_away_splits(history),
        "luck_curve": luck_curve(history),
        "strength_of_schedule": strength_of_schedule(history, league_histories) if league_histories else None,
        "metric_trends": metric_trends(history, window=5),
        "archetype": None,
        "limitations": HONEST_TEAM_LIMITATIONS,
    }


def position_trend(history: list[dict], league_histories: dict[str, list[dict]]) -> dict:
    """Matchday-by-matchday points, xPTS and league rank trajectory.

    Rebuilds the league table at every date from all teams' histories, so the
    rank is the honest table position after each of this team's matches.
    """
    ordered = sorted(history, key=lambda r: (r.get("date") or "", r.get("h_a") or ""))
    opponents = list(league_histories.keys())
    matchdays = []
    cumulative_pts = 0.0
    cumulative_xpts = 0.0
    for match in ordered:
        cumulative_pts += to_float(match.get("pts"))
        cumulative_xpts += to_float(match.get("xpts"))
        date = (match.get("date") or "")[:10]
        points_by_team = {}
        for team, history_rows in league_histories.items():
            points_by_team[team] = sum(
                to_float(row.get("pts")) for row in history_rows if (row.get("date") or "")[:10] <= date
            )
        rank = 1 + sum(1 for team in opponents if points_by_team.get(team, 0) > cumulative_pts)
        matchdays.append(
            {
                "date": date,
                "points": round_value(cumulative_pts),
                "xpts": round_value(cumulative_xpts),
                "rank": rank,
            }
        )
    return {"matchdays": matchdays, "n_teams": len(opponents) or 1}


def half_split(history: list[dict]) -> dict:
    """First half vs second half of the season: does the team improve or fade?"""
    ordered = sorted(history, key=lambda r: (r.get("date") or "", r.get("h_a") or ""))
    mid = len(ordered) // 2
    halves = {"first": ordered[:mid], "second": ordered[mid:]}

    def summarize(rows):
        n = len(rows) or 1
        return {
            "matches": len(rows),
            "wins": sum(to_float(r.get("wins")) for r in rows),
            "draws": sum(to_float(r.get("draws")) for r in rows),
            "loses": sum(to_float(r.get("loses")) for r in rows),
            "points": sum(to_float(r.get("pts")) for r in rows),
            "points_per_game": round_value(sum(to_float(r.get("pts")) for r in rows) / n),
            "xG_per_game": round_value(sum(to_float(r.get("xG")) for r in rows) / n, 3),
            "xGA_per_game": round_value(sum(to_float(r.get("xGA")) for r in rows) / n, 3),
            "npxGD_per_game": round_value(sum(to_float(r.get("npxGD")) for r in rows) / n, 3),
        }

    first, second = summarize(halves["first"]), summarize(halves["second"])
    delta = round_value(second["points_per_game"] - first["points_per_game"], 2)
    return {
        "first_half": first,
        "second_half": second,
        "points_per_game_delta": delta,
        "interpretation": (
            f"Second-half points per game change: {delta:+0.2f}. Positive = improving team, "
            "negative = fading team. Small samples; injuries and schedule strength confound it."
        ),
    }


def home_away_splits(history: list[dict]) -> dict:
    """Points, xG and win rates split by venue."""

    def summarize(rows):
        n = len(rows) or 1
        return {
            "matches": len(rows),
            "points_per_game": round_value(sum(to_float(r.get("pts")) for r in rows) / n),
            "xG_per_game": round_value(sum(to_float(r.get("xG")) for r in rows) / n, 3),
            "xGA_per_game": round_value(sum(to_float(r.get("xGA")) for r in rows) / n, 3),
            "win_rate": round_value(sum(to_float(r.get("wins")) for r in rows) / n, 3),
        }

    home_rows = [r for r in history if r.get("h_a") == "h"]
    away_rows = [r for r in history if r.get("h_a") == "a"]
    return {
        "home": summarize(home_rows),
        "away": summarize(away_rows),
        "interpretation": "Home/away performance split: some teams are venue-dependent; a wide gap flags travel/form issues.",
    }


def luck_curve(history: list[dict]) -> dict:
    """Cumulative goals minus xG across the season (the luck trajectory)."""
    ordered = sorted(history, key=lambda r: (r.get("date") or "", r.get("h_a") or ""))
    points = []
    cumulative = 0.0
    for row in ordered:
        cumulative += to_float(row.get("scored")) - to_float(row.get("xG"))
        points.append({"date": (row.get("date") or "")[:10], "cumulative_g_minus_xg": round_value(cumulative, 2)})
    return {
        "points": points,
        "final": round_value(cumulative, 2),
        "interpretation": (
            f"Cumulative goals minus xG ends at {cumulative:+.1f}: positive means the season's "
            "results were kinder than the chances, negative the reverse."
        ),
    }


def strength_of_schedule(history: list[dict], league_histories: dict[str, list[dict]]) -> dict:
    """How strong were the opponents faced, using each opponent's season xGD per game.

    Understat history rows carry no opponent name, so opponents are matched by
    match date across all teams' histories.
    """
    team_xgd = {}
    dates_by_team = {}
    for team, rows in league_histories.items():
        n = len(rows) or 1
        team_xgd[team] = sum(to_float(r.get("npxGD")) for r in rows) / n
        dates_by_team[team] = {(r.get("date") or "")[:10] for r in rows}

    played = sorted(history, key=lambda r: (r.get("date") or ""))
    vs_top, vs_bottom = [], []
    for row in played:
        date = (row.get("date") or "")[:10]
        opponents = [
            team for team in league_histories
            if date in dates_by_team.get(team, set()) and team != _own_team(league_histories, history)
        ]
        if not opponents:
            continue
        opponent_xgd = team_xgd.get(opponents[0], 0.0)
        entry = {
            "points": to_float(row.get("pts")),
            "xG": to_float(row.get("xG")),
            "xGA": to_float(row.get("xGA")),
        }
        (vs_top if opponent_xgd > 0 else vs_bottom).append(entry)
    if not vs_top or not vs_bottom:
        return {"available": False}

    def summarize(rows):
        n = len(rows) or 1
        return {
            "matches": len(rows),
            "points_per_game": round_value(sum(r["points"] for r in rows) / n),
            "xGD_per_game": round_value(sum(r["xG"] - r["xGA"] for r in rows) / n, 3),
        }

    return {
        "available": True,
        "vs_stronger_opponents": summarize(vs_top),
        "vs_weaker_opponents": summarize(vs_bottom),
        "interpretation": (
            "Record against opponents with positive vs negative season npxGD per game: "
            "the classic flat-track-bully check."
        ),
    }


def _own_team(league_histories: dict[str, list[dict]], own_history: list[dict]) -> str | None:
    """Identify which league team this history belongs to by date overlap."""
    own_dates = {(r.get("date") or "")[:10] for r in own_history}
    best_team, best_overlap = None, 0
    for team, rows in league_histories.items():
        overlap = len(own_dates & {(r.get("date") or "")[:10] for r in rows})
        if overlap > best_overlap:
            best_team, best_overlap = team, overlap
    return best_team


def metric_trends(history: list[dict], window: int = 5) -> dict:
    """Rolling per-game averages for selectable metrics across the season."""
    ordered = sorted(history, key=lambda r: (r.get("date") or "", r.get("h_a") or ""))

    def roll(key, transform=lambda v: v):
        values = [to_float(transform(r.get(key))) for r in ordered]
        out = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            out.append(round_value(sum(values[start : i + 1]) / (i - start + 1), 3))
        return out

    dates = [(r.get("date") or "")[:10] for r in ordered]
    return {
        "dates": dates,
        "xG_for": roll("xG"),
        "xG_against": roll("xGA"),
        "goals_for": roll("scored"),
        "goals_against": roll("missed"),
        "npxGD": roll("npxGD"),
        "xPTS": roll("xpts"),
        "PPDA": roll("ppda", transform=lambda r: ppda_ratio(r.get("ppda") or {})),
        "deep_for": roll("deep"),
        "deep_against": roll("deep_allowed"),
        "window": window,
    }
