from __future__ import annotations

from ._helpers import fmt_num, sum_metric, player_summary, describe_timeframe


def player_overview(plan, data) -> dict:
    return _player_core(plan, data)


def player_shots(plan, data) -> dict:
    return _player_core(plan, data)


def player_compare(plan, data) -> dict:
    base = _player_core(plan, data)
    reasons = base["reasons"]
    direct_answer = base["direct_answer"]
    social_caption = base["social_caption"]

    if "comparison_player_data" in data:
        player_data = data.get("player_data", {})
        player_core = player_data.get("player", {})
        matches = data.get("player_matches") or data.get("player_matches_via_ajax") or []

        comparison_core = data["comparison_player_data"].get("player", {})
        comparison_matches = data.get("comparison_player_matches", [])
        base_summary = player_summary(matches)
        comparison_summary = player_summary(comparison_matches)
        direct_answer = (
            f"{player_core.get('name')} vs {comparison_core.get('name')} {describe_timeframe(plan)}: "
            f"{player_core.get('name')} has {base_summary['goals']} goals, {base_summary['xg']} xG, {base_summary['assists']} assists, "
            f"and {base_summary['goal_contrib_per90']} goal contributions per 90 in {base_summary['matches']} matches; "
            f"{comparison_core.get('name')} has {comparison_summary['goals']} goals, {comparison_summary['xg']} xG, "
            f"{comparison_summary['assists']} assists, and {comparison_summary['goal_contrib_per90']} goal contributions per 90 in {comparison_summary['matches']} matches."
        )
        reasons.append(
            f"{player_core.get('name')} goal-xG gap is {base_summary['goal_xg_gap']:+.2f}, while {comparison_core.get('name')} is at {comparison_summary['goal_xg_gap']:+.2f}."
        )
        reasons.append(
            f"{player_core.get('name')} average shot quality is {base_summary['xg_per_shot']}, while {comparison_core.get('name')} is at {comparison_summary['xg_per_shot']}."
        )
        social_caption = direct_answer

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def player_ranking(plan, data) -> dict:
    from ._helpers import rank_players

    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    ranking_rows = data["league_player_stats"]
    ranked = rank_players(ranking_rows, plan.metric)
    if ranked:
        top = ranked[0]
        metric_label = top["metric_label"]
        direct_answer = (
            f"The best {plan.metric and (plan.metric.replace('_', ' ')) or 'attacking'} profile {timeframe} is {top['player_name']} ({top['team_title']}), "
            f"leading the league on {metric_label}: {top['metric_value']}."
        )
        reasons.append(
            f"{top['player_name']} ranks first on {metric_label} among the fetched league player table."
        )
        if len(ranked) > 1:
            reasons.append(
                f"Next best is {ranked[1]['player_name']} at {ranked[1]['metric_value']}."
            )
        social_caption = (
            f"{top['player_name']} is leading the league for {metric_label} {timeframe} with {top['metric_value']}."
        )
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def _player_core(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    player_data = data.get("player_data", {})
    player_core = player_data.get("player", {})
    matches = data.get("player_matches") or data.get("player_matches_via_ajax") or []
    shots = data.get("player_shots", [])
    if player_core:
        reasons.append(
            f"{player_core.get('name')} is listed by Understat with favorite position {player_core.get('favorite_position')}."
        )
    if matches:
        reasons.append(f"The fetched match log includes {len(matches)} matches, giving us a usable sample size.")
    if shots:
        reasons.append(f"The shot map contains {len(shots)} shots, which supports finishing and chance-quality analysis.")
    if player_core:
        goals = sum_metric(matches, "goals")
        xg = sum_metric(matches, "xG")
        assists = sum_metric(matches, "assists")
        minutes = sum_metric(matches, "time")
        overperformance = None if xg is None or goals is None else round(goals - xg, 2)
        over_text = ""
        if overperformance is not None:
            if overperformance > 0:
                over_text = f" That is {overperformance} goals above xG."
            elif overperformance < 0:
                over_text = f" That is {abs(overperformance)} goals below xG."
            else:
                over_text = " Goals and xG are roughly level."
        direct_answer = (
            f"{player_core.get('name')} has {fmt_num(goals)} goals, {fmt_num(assists)} assists, "
            f"and {fmt_num(xg)} xG across {len(matches)} matches and {fmt_num(minutes, digits=0)} minutes {timeframe}."
            f"{over_text}"
        )
        social_caption = (
            f"{player_core.get('name')} {timeframe}: {fmt_num(goals)} goals, "
            f"{fmt_num(xg)} xG, {fmt_num(assists)} assists in {len(matches)} matches."
        )
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}
