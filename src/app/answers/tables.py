from __future__ import annotations

from ._helpers import describe_timeframe, league_process_vs_results_rows


def league_table(plan, data) -> dict:
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""

    table = data["league_table"]
    top_row = table[1] if len(table) > 1 else None
    if top_row:
        reasons.append(f"{top_row[0]} are top of the table on {top_row[7]} points in the selected view.")
        direct_answer = f"{top_row[0]} are top of the {plan.league_name or 'selected league'} table with {top_row[7]} points."
        social_caption = f"{top_row[0]} lead the table on {top_row[7]} points. Understat-backed snapshot."

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def league_overview(plan, data) -> dict:
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""

    if "league_table" in data and len(data["league_table"]) > 1:
        top_row = data["league_table"][1]
        reasons.append(f"{top_row[0]} lead the table with {top_row[7]} points.")
    if "league_player_stats" in data and data["league_player_stats"]:
        top_scorer = max(data["league_player_stats"], key=lambda row: float(row.get("goals", 0)))
        reasons.append(
            f"{top_scorer.get('player_name')} is the top scorer in the fetched player table with {top_scorer.get('goals')} goals."
        )
        if not direct_answer and top_row:
            direct_answer = (
                f"In {plan.league_name or 'the selected league'} {describe_timeframe(plan)}, "
                f"{top_row[0]} lead the table and {top_scorer.get('player_name')} leads the scoring chart with {top_scorer.get('goals')} goals."
            )
            social_caption = (
                f"{top_row[0]} on top. {top_scorer.get('player_name')} leading the scoring race with {top_scorer.get('goals')} goals. "
                f"Understat check."
            )

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def team_xpts_gap(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    table = data["league_table"]
    rows = table[1:] if len(table) > 1 else []
    if rows:
        enriched = []
        for row in rows:
            pts = float(row[7])
            xpts = float(row[17])
            enriched.append(
                {
                    "team": row[0],
                    "pts": pts,
                    "xpts": xpts,
                    "gap": round(pts - xpts, 2),
                }
            )
        if plan.team_name:
            matching = next((row for row in enriched if row["team"].lower() == plan.team_name.lower()), None)
            if matching:
                trend = "overperforming" if matching["gap"] > 0 else "underperforming" if matching["gap"] < 0 else "tracking xPTS almost exactly"
                direct_answer = (
                    f"{matching['team']} are {trend} {timeframe}: they have {int(matching['pts'])} points versus {matching['xpts']:.2f} xPTS, "
                    f"a gap of {matching['gap']:+.2f}."
                )
                reasons.append(
                    f"{matching['team']} have a points-minus-xPTS gap of {matching['gap']:+.2f}."
                )
                social_caption = (
                    f"{matching['team']} xPTS check {timeframe}: {int(matching['pts'])} points vs {matching['xpts']:.2f} xPTS "
                    f"({matching['gap']:+.2f})."
                )
        else:
            top_gap = max(enriched, key=lambda row: row["gap"])
            bottom_gap = min(enriched, key=lambda row: row["gap"])
            direct_answer = (
                f"The biggest xPTS overperformer {timeframe} is {top_gap['team']} at {top_gap['gap']:+.2f}, "
                f"while the biggest underperformer is {bottom_gap['team']} at {bottom_gap['gap']:+.2f}."
            )
            reasons.append(
                f"{top_gap['team']} lead the league in positive points-minus-xPTS gap at {top_gap['gap']:+.2f}."
            )
            reasons.append(
                f"{bottom_gap['team']} have the worst points-minus-xPTS gap at {bottom_gap['gap']:+.2f}."
            )
            social_caption = direct_answer

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def process_vs_results(plan, data) -> dict:
    timeframe = describe_timeframe(plan)
    reasons: list[str] = []
    direct_answer = ""
    social_caption = ""
    process_rows = league_process_vs_results_rows(data["league_table"])
    if process_rows:
        points_over = max(process_rows, key=lambda row: row["points_gap"])
        points_under = min(process_rows, key=lambda row: row["points_gap"])
        finishing_over = max(process_rows, key=lambda row: row["finishing_gap"])
        finishing_under = min(process_rows, key=lambda row: row["finishing_gap"])
        defensive_over = max(process_rows, key=lambda row: row["defensive_prevention_gap"])
        defensive_under = min(process_rows, key=lambda row: row["defensive_prevention_gap"])

        direct_answer = (
            f"Process vs results {timeframe}: {points_over['team']} are getting the biggest results boost "
            f"({points_over['points_gap']:+.2f} points vs xPTS), while {points_under['team']} are the biggest under-earners "
            f"({points_under['points_gap']:+.2f})."
        )
        reasons.append(
            f"Points vs process: {points_over['team']} lead points-minus-xPTS at {points_over['points_gap']:+.2f}; "
            f"{points_under['team']} are bottom at {points_under['points_gap']:+.2f}."
        )
        reasons.append(
            f"Finishing variance: {finishing_over['team']} are highest on goals-minus-xG at {finishing_over['finishing_gap']:+.2f}; "
            f"{finishing_under['team']} are lowest at {finishing_under['finishing_gap']:+.2f}."
        )
        reasons.append(
            f"Defensive/keeper variance: {defensive_over['team']} are {defensive_over['defensive_prevention_gap']:+.2f} on xGA minus goals against; "
            f"{defensive_under['team']} are lowest at {defensive_under['defensive_prevention_gap']:+.2f}."
        )
        social_caption = (
            f"Process vs results {timeframe}: {points_over['team']} are running hottest against xPTS "
            f"({points_over['points_gap']:+.2f}), while {points_under['team']} are the clearest under-earners "
            f"({points_under['points_gap']:+.2f})."
        )

    return {"direct_answer": direct_answer, "reasons": reasons, "social_caption": social_caption}


def overview(plan, data) -> dict:
    return {"direct_answer": "", "reasons": [], "social_caption": ""}
