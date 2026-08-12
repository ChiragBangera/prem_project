from __future__ import annotations

from ._helpers import (
    fmt_num,
    sum_metric,
    sort_rows_by_date,
    find_team_table_row,
    team_table_profile,
    team_results_summary,
    team_results_window_summary,
    rank_players,
    team_position_progression,
    team_chance_profile as compute_chance_profile,
    describe_timeframe,
    recent_window_from_metric,
    window_compare_size,
    trend_label,
    humanize_metric,
    safe_get_metric,
)


def team_compare(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""

    left_row = find_team_table_row(data["league_table"], plan.team_name)
    right_row = find_team_table_row(data["league_table"], plan.comparison_team_name)
    left_results = sort_rows_by_date(data.get("team_results", []), descending=True)[:5]
    right_results = sort_rows_by_date(data.get("comparison_team_results", []), descending=True)[:5]
    if left_row and right_row:
        left_profile = team_table_profile(left_row)
        right_profile = team_table_profile(right_row)
        left_recent = team_results_summary(left_results)
        right_recent = team_results_summary(right_results)
        attack_winner = left_profile["team"] if left_profile["xg"] > right_profile["xg"] else right_profile["team"]
        defense_winner = left_profile["team"] if left_profile["xga"] < right_profile["xga"] else right_profile["team"]
        direct_answer = (
            f"{left_profile['team']} vs {right_profile['team']} {timeframe}: "
            f"{attack_winner} have the stronger attacking process on xG ({left_profile['team']} {fmt_num(left_profile['xg'])}, "
            f"{right_profile['team']} {fmt_num(right_profile['xg'])}), while {defense_winner} have the better defensive process on xGA "
            f"({left_profile['team']} {fmt_num(left_profile['xga'])}, {right_profile['team']} {fmt_num(right_profile['xga'])})."
        )
        reasons.append(
            f"{left_profile['team']} carry a non-penalty xG difference of {fmt_num(left_profile['npxgd'])}, compared with {right_profile['team']} at {fmt_num(right_profile['npxgd'])}."
        )
        reasons.append(
            f"Recent five-match output: {left_profile['team']} have {left_recent['points']} points and {left_recent['goals_for']}-{left_recent['goals_against']} goals; "
            f"{right_profile['team']} have {right_recent['points']} points and {right_recent['goals_for']}-{right_recent['goals_against']}."
        )
        reasons.append(
            f"W-D-L form over the same stretch: {left_profile['team']} {left_recent['wins']}-{left_recent['draws']}-{left_recent['losses']}, "
            f"{right_profile['team']} {right_recent['wins']}-{right_recent['draws']}-{right_recent['losses']}."
        )
        social_caption = direct_answer

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_overview(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""

    team_stats = data.get("team_stats", {})
    team_players = data.get("team_player_stats", [])
    if team_stats:
        for stat_name in ("xG", "xGA", "ppda"):
            if stat_name in team_stats:
                reasons.append(f"{plan.team_name} has {stat_name} data available for evidence-backed analysis.")
                break
    if team_players:
        top_scorer = max(team_players, key=lambda row: float(row.get("goals", 0)))
        reasons.append(
            f"{top_scorer.get('player_name')} leads {plan.team_name} in the filtered player table with {top_scorer.get('goals')} goals."
        )
        xg_for = safe_get_metric(team_stats, "xG")
        xg_against = safe_get_metric(team_stats, "xGA")
        direct_answer = (
            f"{plan.team_name} look analyzable {timeframe}: they have team-level Understat data"
            f"{f' with xG {xg_for}' if xg_for is not None else ''}"
            f"{f' and xGA {xg_against}' if xg_against is not None else ''}, "
            f"and {top_scorer.get('player_name')} leads the squad on {top_scorer.get('goals')} goals."
        )
        social_caption = (
            f"{plan.team_name} snapshot {timeframe}: "
            f"{top_scorer.get('player_name')} leads the team with {top_scorer.get('goals')} goals."
        )

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_recent_form(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    team_results = data.get("team_results", [])
    team_players = data.get("team_player_stats", [])
    match_limit = recent_window_from_metric(plan.metric)
    ordered_results = sort_rows_by_date(team_results, descending=True)
    sliced_results = ordered_results[:match_limit] if match_limit else ordered_results
    recent_summary = team_results_summary(sliced_results)
    points = recent_summary["points"]
    goals_for = recent_summary["goals_for"]
    goals_against = recent_summary["goals_against"]
    top_scorer = None
    if team_players:
        top_scorer = max(team_players, key=lambda row: float(row.get("goals", 0)))
    direct_answer = (
        f"{plan.team_name} over their last {len(sliced_results)} matches: "
        f"{points} points, {goals_for} goals scored, {goals_against} conceded."
    )
    if top_scorer:
        direct_answer += f" The top scorer in the filtered team player table is {top_scorer.get('player_name')} with {top_scorer.get('goals')} goals."
        reasons.append(
            f"{top_scorer.get('player_name')} leads the team scoring output in the current filtered window."
        )
    reasons.append(
        f"The recent-form sample contains {len(sliced_results)} team results."
    )
    social_caption = direct_answer

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_window_compare(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    team_results = sort_rows_by_date(data.get("team_results", []), descending=False)
    window_size = window_compare_size(plan.metric)
    if window_size and len(team_results) >= window_size * 2:
        first_window = team_results[:window_size]
        last_window = team_results[-window_size:]
        first_summary = team_results_window_summary(first_window)
        last_summary = team_results_window_summary(last_window)
        direct_answer = (
            f"{plan.team_name} first {window_size} vs last {window_size} league matches {timeframe}: "
            f"points per game moved from {fmt_num(first_summary['ppg'])} to {fmt_num(last_summary['ppg'])}, "
            f"xG per game from {fmt_num(first_summary['xg_per_game'])} to {fmt_num(last_summary['xg_per_game'])}, "
            f"and xGA per game from {fmt_num(first_summary['xga_per_game'])} to {fmt_num(last_summary['xga_per_game'])}."
        )
        reasons.append(
            f"Goal difference shifted from {first_summary['goals_for']}-{first_summary['goals_against']} in the first window to {last_summary['goals_for']}-{last_summary['goals_against']} in the last window."
        )
        reasons.append(
            f"That is a {trend_label(last_summary['xga_per_game'], first_summary['xga_per_game'], lower_is_better=True)} defensive process on xGA per game."
        )
        social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_defensive_trend(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    team_results = sort_rows_by_date(data.get("team_results", []), descending=False)
    if len(team_results) >= 10:
        recent_window = team_results[-5:]
        previous_window = team_results[-10:-5]
        recent_summary = team_results_window_summary(recent_window)
        previous_summary = team_results_window_summary(previous_window)
        direct_answer = (
            f"{plan.team_name}'s defensive trend {timeframe}: over the latest 5 league matches they have conceded "
            f"{recent_summary['goals_against']} goals with xGA {fmt_num(recent_summary['xga'])} "
            f"({fmt_num(recent_summary['xga_per_game'])} per game), compared with "
            f"{previous_summary['goals_against']} goals and xGA {fmt_num(previous_summary['xga'])} "
            f"({fmt_num(previous_summary['xga_per_game'])} per game) in the prior 5."
        )
        reasons.append(
            f"The defensive process is {trend_label(recent_summary['xga_per_game'], previous_summary['xga_per_game'], lower_is_better=True)} on xGA per game."
        )
        if recent_summary["shots_against"] is not None and previous_summary["shots_against"] is not None:
            reasons.append(
                f"Shots allowed moved from {previous_summary['shots_against']} in the prior 5 to {recent_summary['shots_against']} in the latest 5."
            )
        social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_chance_profile(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    team_stats = data.get("team_stats", {})
    chance_profile = compute_chance_profile(team_stats)
    if chance_profile:
        direct_answer = (
            f"{plan.team_name}'s chance-creation profile {timeframe}: their biggest xG source is {chance_profile['top_situation']['label']} "
            f"({fmt_num(chance_profile['top_situation']['xg'])} xG), while their highest-volume shooting zone is "
            f"{chance_profile['top_zone']['label']} ({chance_profile['top_zone']['shots']} shots, {fmt_num(chance_profile['top_zone']['xg'])} xG)."
        )
        reasons.append(
            f"Best attacking speed bucket by xG is {chance_profile['top_speed']['label']} at {fmt_num(chance_profile['top_speed']['xg'])}."
        )
        reasons.append(
            f"Peak scoring window is {chance_profile['top_timing']['label']} with {fmt_num(chance_profile['top_timing']['xg'])} xG created."
        )
        social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_player_ranking(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    ranking_rows = data["team_player_stats"]
    ranked = rank_players(ranking_rows, plan.metric)
    if ranked:
        top = ranked[0]
        metric_label = top["metric_label"]
        direct_answer = (
            f"{top['player_name']} has been {plan.team_name}'s standout for {metric_label} {timeframe}, "
            f"leading the squad with {top['metric_value']}."
        )
        reasons.append(
            f"{top['player_name']} ranks first in the filtered {plan.team_name} player table on {metric_label}."
        )
        if len(ranked) > 1:
            reasons.append(
                f"The next-best squad mark belongs to {ranked[1]['player_name']} at {ranked[1]['metric_value']}."
            )
        social_caption = (
            f"{plan.team_name} leader for {metric_label} {timeframe}: "
            f"{top['player_name']} on {top['metric_value']}."
        )
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_attack_defense(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    league_table = data.get("league_table", [])
    team_results = data.get("team_results", [])
    team_players = data.get("team_player_stats", [])
    table_row = find_team_table_row(league_table, plan.team_name)
    xg_for = None
    xg_against = None
    xg_diff = None
    npxgd = None
    if table_row:
        xg_for = float(table_row[8])
        xg_against = float(table_row[10])
        npxgd = round(float(table_row[12]), 2)
    if xg_for is not None and xg_against is not None:
        xg_diff = round(xg_for - xg_against, 2)

    attacking_leader = rank_players(team_players, "goals")
    creative_leader = rank_players(team_players, "creativity")
    recent_results = sort_rows_by_date(team_results, descending=True)[:5]
    recent_summary = team_results_summary(recent_results)
    recent_points = recent_summary["points"]
    recent_scored = recent_summary["goals_for"]
    recent_conceded = recent_summary["goals_against"]

    if xg_for is not None or xg_against is not None:
        direct_answer = (
            f"{plan.team_name}'s attack-defense profile {timeframe}: "
            f"{f'xG {fmt_num(xg_for)}' if xg_for is not None else 'xG unavailable'}"
            f"{f', xGA {fmt_num(xg_against)}' if xg_against is not None else ''}"
            f"{f', xG difference {fmt_num(xg_diff)}' if xg_diff is not None else ''}. "
            f"Across their latest {len(recent_results)} team results, they scored {recent_scored} and conceded {recent_conceded} for {recent_points} points."
        )
        reasons.append(
            f"{plan.team_name}'s league-table row gives us attack/defense anchors through xG and xGA."
        )
        if xg_diff is not None:
            trend_lbl = "positive" if xg_diff > 0 else "negative" if xg_diff < 0 else "neutral"
            reasons.append(
                f"The club's xG difference is {trend_lbl} at {fmt_num(xg_diff)}."
            )
        if npxgd is not None:
            reasons.append(
                f"The club's non-penalty xG difference sits at {fmt_num(npxgd)}."
            )
        if attacking_leader:
            reasons.append(
                f"{attacking_leader[0]['player_name']} is the leading scorer in the filtered squad table with {attacking_leader[0]['metric_value']} goals."
            )
        if creative_leader:
            reasons.append(
                f"{creative_leader[0]['player_name']} leads the squad for xA with {creative_leader[0]['metric_value']}."
            )
        social_caption = (
            f"{plan.team_name} attack/defense snapshot {timeframe}: "
            f"{f'xG {fmt_num(xg_for)}, ' if xg_for is not None else ''}"
            f"{f'xGA {fmt_num(xg_against)}, ' if xg_against is not None else ''}"
            f"{recent_scored}-{recent_conceded} goals across the latest {len(recent_results)} results."
        )
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_position_trend(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    season_summaries = []
    for season_key, league_data in data["league_data"].items():
        progression = team_position_progression(
            league_data=league_data,
            team_name=plan.team_name,
        )
        if progression:
            season_summaries.append(
                {
                    "season": season_key,
                    "progression": progression,
                    "start_position": progression[0]["position"],
                    "end_position": progression[-1]["position"],
                    "best_position": min(item["position"] for item in progression),
                    "worst_position": max(item["position"] for item in progression),
                }
            )

    if season_summaries:
        latest = sorted(season_summaries, key=lambda item: item["season"], reverse=True)[0]
        direct_answer = (
            f"{plan.team_name}'s weekly table-position trend is available. "
            f"In {latest['season']}/{latest['season'] + 1}, they moved from {latest['start_position']} to {latest['end_position']}, "
            f"with a best position of {latest['best_position']} and worst of {latest['worst_position']}."
        )
        if len(season_summaries) > 1:
            comparison_text = "; ".join(
                f"{item['season']}: start {item['start_position']}, finish {item['end_position']}"
                for item in sorted(season_summaries, key=lambda x: x["season"], reverse=True)
            )
            reasons.append(f"Season-over-season weekly table position summaries: {comparison_text}.")
        reasons.append(
            f"Weekly position progression was derived from Understat league histories for {plan.team_name}."
        )
        social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}
