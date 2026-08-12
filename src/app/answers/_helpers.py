from __future__ import annotations


def fmt_num(value, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if digits == 0:
        return str(int(round(value)))
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.{digits}f}"


def safe_get_metric(payload, key):
    value = payload.get(key)
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def sum_metric(rows, key) -> float:
    if not rows:
        return 0
    total = 0.0
    for row in rows:
        try:
            total += float(row.get(key, 0))
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def sort_rows_by_date(rows, descending: bool = False):
    if not rows:
        return rows

    dated_rows = [row for row in rows if row_date_value(row)]
    undated_rows = [row for row in rows if not row_date_value(row)]

    if not dated_rows:
        return rows

    dated_rows = sorted(
        dated_rows,
        key=lambda row: row_date_value(row),
        reverse=descending,
    )
    return dated_rows + undated_rows


def row_date_value(row):
    value = row.get("date") or row.get("datetime") or ""
    return value[:19]


def filter_rows_by_date(rows, start_date=None, end_date=None):
    if not start_date and not end_date:
        return rows

    filtered = []
    for row in rows:
        row_date = row_date_value(row)
        if not row_date:
            filtered.append(row)
            continue

        current = row_date[:10]
        if start_date and current < start_date:
            continue
        if end_date and current > end_date:
            continue
        filtered.append(row)

    return filtered


def filter_player_rows(rows, season=None, start_date=None, end_date=None):
    filtered = rows
    if season is not None:
        filtered = [
            row for row in filtered
            if str(row.get("season", season)) == str(season)
        ]
    return filter_rows_by_date(filtered, start_date=start_date, end_date=end_date)


def team_result_points(row) -> int:
    if row.get("pts") is not None:
        return int(row.get("pts", 0))

    result = row.get("result")
    if result == "w":
        return 3
    if result == "d":
        return 1
    return 0


def team_result_scoreline(row):
    if row.get("scored") is not None or row.get("missed") is not None:
        return int(row.get("scored", 0)), int(row.get("missed", 0))

    goals = row.get("goals", {})
    side = row.get("side")
    if side == "h":
        return int(goals.get("h", 0)), int(goals.get("a", 0))
    if side == "a":
        return int(goals.get("a", 0)), int(goals.get("h", 0))
    return 0, 0


def team_results_summary(rows) -> dict:
    summary = {
        "points": 0,
        "goals_for": 0,
        "goals_against": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,
    }

    for row in rows:
        summary["points"] += team_result_points(row)
        goals_for, goals_against = team_result_scoreline(row)
        summary["goals_for"] += goals_for
        summary["goals_against"] += goals_against
        result = row.get("result")
        if result == "w":
            summary["wins"] += 1
        elif result == "d":
            summary["draws"] += 1
        elif result == "l":
            summary["losses"] += 1

    summary["xg"] = sum_team_result_xg(rows, for_team=True)
    summary["xga"] = sum_team_result_xg(rows, for_team=False)

    return summary


def team_results_window_summary(rows) -> dict:
    summary = team_results_summary(rows)
    matches = len(rows)
    xg = sum_team_result_xg(rows, for_team=True)
    xga = sum_team_result_xg(rows, for_team=False)
    shots_against = sum_team_result_shots(rows, for_team=False)
    return {
        **summary,
        "matches": matches,
        "ppg": 0 if matches == 0 else round(summary["points"] / matches, 2),
        "xg": xg,
        "xga": xga,
        "xg_per_game": 0 if matches == 0 else round(xg / matches, 2),
        "xga_per_game": 0 if matches == 0 else round(xga / matches, 2),
        "shots_against": shots_against,
    }


def sum_team_result_xg(rows, for_team: bool = True) -> float:
    total = 0.0
    for row in rows:
        xg = row.get("xG", {})
        side = row.get("side")
        if not isinstance(xg, dict) or side not in {"h", "a"}:
            continue
        key = side if for_team else ("a" if side == "h" else "h")
        total += float(xg.get(key, 0) or 0)
    return round(total, 2)


def sum_team_result_shots(rows, for_team: bool = True):
    total = 0
    found = False
    for row in rows:
        shots = row.get("shots", {})
        side = row.get("side")
        if not isinstance(shots, dict) or not shots or side not in {"h", "a"}:
            continue
        found = True
        key = side if for_team else ("a" if side == "h" else "h")
        total += int(shots.get(key, 0) or 0)
    return total if found else None


def trend_label(current, previous, lower_is_better: bool = False) -> str:
    if current == previous:
        return "stable"
    if lower_is_better:
        return "improving" if current < previous else "regressing"
    return "improving" if current > previous else "regressing"


def find_team_table_row(table, team_name: str | None):
    if not table or not team_name:
        return None

    for row in table[1:]:
        if str(row[0]).lower() == team_name.lower():
            return row
    return None


def team_table_profile(row) -> dict:
    return {
        "team": row[0],
        "xg": float(row[8]),
        "xga": float(row[10]),
        "npxgd": float(row[12]),
        "points": float(row[7]),
        "xpts": float(row[17]),
    }


def rank_players(rows, metric) -> list[dict]:
    ranked = []
    for row in rows:
        minutes = float(row.get("time", 0) or 0)
        if minutes < 450:
            continue

        if metric == "finishing":
            value = round(float(row.get("goals", 0)) - float(row.get("xG", 0) or 0), 2)
            label = "goals minus xG"
        elif metric == "creativity":
            value = round(float(row.get("xA", 0) or 0), 2)
            label = "xA"
        elif metric == "shot_quality":
            shots = float(row.get("shots", 0) or 0)
            xg = float(row.get("xG", 0) or 0)
            value = round(0 if shots == 0 else xg / shots, 3)
            label = "xG per shot"
        else:
            value = round(float(row.get("goals", 0) or 0), 2)
            label = "goals"

        ranked.append(
            {
                "player_name": row.get("player_name"),
                "team_title": row.get("team_title"),
                "metric_value": value,
                "metric_label": label,
            }
        )

    return sorted(ranked, key=lambda item: item["metric_value"], reverse=True)


def player_summary(matches) -> dict:
    goals = sum_metric(matches, "goals")
    xg = sum_metric(matches, "xG")
    assists = sum_metric(matches, "assists")
    minutes = sum_metric(matches, "time")
    shots = sum_metric(matches, "shots")
    goal_contrib = goals + assists
    goal_contrib_per90 = 0 if minutes == 0 else round(goal_contrib * 90 / minutes, 2)
    xg_per_shot = 0 if shots == 0 else round(xg / shots, 3)
    return {
        "goals": fmt_num(goals),
        "xg": fmt_num(xg),
        "assists": fmt_num(assists),
        "matches": len(matches),
        "goal_xg_gap": round(goals - xg, 2),
        "goal_contrib_per90": fmt_num(goal_contrib_per90),
        "xg_per_shot": fmt_num(xg_per_shot, digits=3),
    }


def league_process_vs_results_rows(table) -> list[dict]:
    if not table or len(table) <= 1:
        return []

    rows = []
    for row in table[1:]:
        try:
            goals_for = float(row[5])
            goals_against = float(row[6])
            points = float(row[7])
            xg = float(row[8])
            xga = float(row[10])
            xpts = float(row[17])
        except (TypeError, ValueError, IndexError):
            continue

        rows.append(
            {
                "team": row[0],
                "points": points,
                "xpts": xpts,
                "points_gap": round(points - xpts, 2),
                "goals": goals_for,
                "xg": xg,
                "finishing_gap": round(goals_for - xg, 2),
                "goals_against": goals_against,
                "xga": xga,
                "defensive_prevention_gap": round(xga - goals_against, 2),
            }
        )

    return rows


def team_position_progression(league_data: dict, team_name: str) -> list[dict]:
    teams = league_data.get("teams", {})
    histories = {
        team_data.get("title"): team_data.get("history", [])
        for team_data in teams.values()
    }
    if team_name not in histories:
        return []

    max_week = max((len(history) for history in histories.values()), default=0)
    progression = []

    for week in range(1, max_week + 1):
        rows = []
        for current_team, history in histories.items():
            slice_history = history[:week]
            pts = sum(match.get("pts", 0) for match in slice_history)
            goals_for = sum(match.get("scored", 0) for match in slice_history)
            goals_against = sum(match.get("missed", 0) for match in slice_history)
            rows.append(
                {
                    "team": current_team,
                    "pts": pts,
                    "gd": goals_for - goals_against,
                    "gf": goals_for,
                }
            )

        ranked = sorted(
            rows,
            key=lambda row: (-row["pts"], -row["gd"], -row["gf"], row["team"]),
        )
        for position, row in enumerate(ranked, start=1):
            if row["team"] == team_name:
                progression.append({"week": week, "position": position, "points": row["pts"]})
                break

    return progression


def team_bundle_summary(bundle: dict, team_name: str | None) -> dict | None:
    table_row = find_team_table_row(bundle.get("league_table", []), team_name)
    if not table_row:
        return None

    results = bundle.get("team_results", [])
    summary = team_results_summary(results)
    player_rows = bundle.get("team_player_stats", [])
    top_scorer = max(player_rows, key=lambda row: float(row.get("goals", 0))) if player_rows else None
    top_creator = max(player_rows, key=lambda row: float(row.get("xA", 0) or 0)) if player_rows else None
    matches = len(results)
    ppg = 0 if matches == 0 else round(summary["points"] / matches, 2)

    return {
        "matches": matches,
        "points": summary["points"],
        "ppg": fmt_num(ppg),
        "goals_for": summary["goals_for"],
        "goals_against": summary["goals_against"],
        "xg": float(table_row[8]),
        "xga": float(table_row[10]),
        "top_scorer": top_scorer.get("player_name") if top_scorer else None,
        "top_scorer_goals": fmt_num(float(top_scorer.get("goals", 0))) if top_scorer else None,
        "top_creator": top_creator.get("player_name") if top_creator else None,
        "top_creator_xa": fmt_num(float(top_creator.get("xA", 0) or 0)) if top_creator else None,
    }


def team_chance_profile(team_stats: dict) -> dict | None:
    if not team_stats:
        return None

    situation = top_team_stats_entry(team_stats.get("situation", {}), metric_key="xG")
    zone = top_team_stats_entry(team_stats.get("shotZone", {}), metric_key="shots")
    speed = top_team_stats_entry(team_stats.get("attackSpeed", {}), metric_key="xG")
    timing = top_team_stats_entry(team_stats.get("timing", {}), metric_key="xG")
    if not all((situation, zone, speed, timing)):
        return None
    return {
        "top_situation": situation,
        "top_zone": zone,
        "top_speed": speed,
        "top_timing": timing,
    }


def top_team_stats_entry(category_stats: dict, metric_key: str):
    if not category_stats:
        return None
    ranked = []
    for label, payload in category_stats.items():
        try:
            ranked.append(
                {
                    "label": label,
                    "shots": int(payload.get("shots", 0) or 0),
                    "goals": int(payload.get("goals", 0) or 0),
                    "xg": float(payload.get("xG", 0) or 0),
                    "metric": float(payload.get(metric_key, 0) or 0),
                }
            )
        except (TypeError, ValueError, AttributeError):
            continue
    if not ranked:
        return None
    return max(ranked, key=lambda item: item["metric"])


def describe_timeframe(plan) -> str:
    if plan.start_date and plan.end_date:
        return f"from {plan.start_date} to {plan.end_date}"
    if plan.start_date:
        return f"since {plan.start_date}"
    if plan.season:
        return f"in the {plan.season}/{plan.season + 1} Understat season"
    return "in the selected timeframe"


def format_window(window) -> str:
    if not window:
        return "in the selected window"
    return f"from {window[0]} to {window[1]}"


def recent_window_from_metric(metric) -> int | None:
    if not metric or not metric.startswith("recent_"):
        return None
    try:
        return int(metric.split("_", 1)[1])
    except (TypeError, ValueError):
        return None


def window_compare_size(metric: str | None) -> int | None:
    if not metric or not metric.startswith("window_compare_"):
        return None
    try:
        return int(metric.split("_")[-1])
    except (TypeError, ValueError):
        return None


def humanize_metric(metric: str | None):
    if metric is None:
        return None
    return {
        "xpts_gap": "xPTS gap",
        "table_position": "table position",
        "finishing": "finishing",
        "creativity": "creativity",
        "shot_quality": "shot quality",
        "attack_defense": "attack and defense",
        "goals": "goals",
        "xg": "xG",
        "process_vs_results": "process vs results",
    }.get(metric, metric.replace("_", " "))
