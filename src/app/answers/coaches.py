from __future__ import annotations

from app.coach_eras import default_coach_season

from ._helpers import fmt_num, team_bundle_summary, format_window


def coach_timeline(plan, data) -> dict:
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    coach_payload = data.get("coach_era", {})
    season_payloads = coach_payload.get("seasons", {})
    season_summaries = []
    for season_key, bundle in sorted(season_payloads.items()):
        summary = team_bundle_summary(bundle, plan.team_name)
        if summary:
            summary["season"] = season_key
            summary["window"] = bundle.get("window")
            season_summaries.append(summary)

    if season_summaries:
        latest_summary = season_summaries[-1]
        direct_answer = (
            f"{plan.team_name} under {plan.coach_name} {format_window(latest_summary.get('window'))}: "
            f"{latest_summary['points']} points from {latest_summary['matches']} league matches, "
            f"{latest_summary['goals_for']}-{latest_summary['goals_against']} goals, xG {fmt_num(latest_summary['xg'])}, "
            f"xGA {fmt_num(latest_summary['xga'])}."
        )
        if latest_summary.get("top_scorer"):
            reasons.append(
                f"{latest_summary['top_scorer']} leads the scoring in that coach window with {latest_summary['top_scorer_goals']} goals."
            )
        if latest_summary.get("top_creator"):
            reasons.append(
                f"{latest_summary['top_creator']} leads chance creation in that coach window with {latest_summary['top_creator_xa']} xA."
            )
        if len(season_summaries) > 1:
            timeline_text = "; ".join(
                f"{item['season']}/{item['season'] + 1}: {item['points']} pts from {item['matches']} matches"
                for item in season_summaries
            )
            reasons.append(f"Coach timeline by Understat season: {timeline_text}.")
        social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def coach_compare(plan, data) -> dict:
    _ = default_coach_season
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    coach_payload = data.get("coach_era", {})
    primary_bundle = coach_payload.get("primary")
    comparison_bundle = coach_payload.get("comparison")
    if primary_bundle and comparison_bundle:
        primary_summary = team_bundle_summary(primary_bundle, plan.team_name)
        comparison_summary = team_bundle_summary(comparison_bundle, plan.comparison_team_name or plan.team_name)
        if primary_summary and comparison_summary:
            direct_answer = (
                f"{plan.coach_name} vs {plan.comparison_coach_name} in the {coach_payload.get('season')}/{coach_payload.get('season', 0) + 1} Understat season: "
                f"{plan.coach_name} posted {primary_summary['ppg']} points per game with xG {fmt_num(primary_summary['xg'])} and xGA {fmt_num(primary_summary['xga'])}; "
                f"{plan.comparison_coach_name} posted {comparison_summary['ppg']} points per game with xG {fmt_num(comparison_summary['xg'])} and xGA {fmt_num(comparison_summary['xga'])}."
            )
            reasons.append(
                f"{plan.coach_name}'s window ran {format_window(coach_payload.get('primary_window'))} and {plan.comparison_coach_name}'s ran {format_window(coach_payload.get('comparison_window'))}."
            )
            reasons.append(
                f"Goal output comparison: {plan.coach_name} {primary_summary['goals_for']}-{primary_summary['goals_against']}, "
                f"{plan.comparison_coach_name} {comparison_summary['goals_for']}-{comparison_summary['goals_against']}."
            )
            social_caption = direct_answer
    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}
