"""What stands out in a league table right now."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .core import (
    Insight, clamp_score, confidence_from_matches, ev, f1, f2, ordinal, plural, signed, team_link,
)

MIN_ROUNDS = 6  # below this, table-vs-process gaps are mostly noise
PTS_SD_PER_MATCH = 1.15  # spread of (points - xPTS) per match, so the sd of a gap grows with sqrt(n)


def _gap_z(row: dict) -> float:
    n = max(1, row["played"])
    return row["xpts_gap"] / (PTS_SD_PER_MATCH * math.sqrt(n))


def _finishing_z(diff: float, xg: float) -> float:
    return diff / math.sqrt(max(0.9 * xg, 1.0))


def league_insights(table: Sequence[dict], context: dict, *, relegation_places: int = 3) -> list[Insight]:
    rows = [r for r in table if r["played"]]
    out: list[Insight] = []
    rounds = context.get("rounds_played", 0)
    if len(rows) < 4 or rounds < 3:
        return [
            Insight("league.early", "info", f"Only {plural(rounds, 'round')} played so far.",
                    "Table-versus-process comparisons need at least six matches per team to mean anything, so the sharper insights appear from round 6.",
                    tone="info", score=40, confidence="low")
        ]
    confidence = confidence_from_matches(rounds)
    solid = rounds >= MIN_ROUNDS

    # -- title race: does the process agree with the table?
    leader, second = rows[0], rows[1]
    lead = leader["pts"] - second["pts"]
    by_xgd = sorted(rows, key=lambda r: -r["xgd_pg"])
    if solid and not context.get("complete"):
        agree = by_xgd[0]["team"] == leader["team"]
        if agree:
            out.append(Insight(
                "league.title.agree", "table",
                f"{leader['team']} lead by {plural(lead, 'point')} and the underlying numbers back them.",
                f"They also have the best xG difference in the league ({signed(leader['xgd_pg'], 2)} per game).",
                tone="neutral", score=clamp_score(55 + 4 * min(lead, 8)), confidence=confidence,
                evidence=[ev("Points", leader["pts"]), ev("xGD/game", signed(leader["xgd_pg"], 2)), ev("Lead", f"{lead} pts")],
                entities=[{"type": "team", "name": leader["team"]}], link=team_link(leader["team"])))
        else:
            best = by_xgd[0]
            out.append(Insight(
                "league.title.split", "table",
                f"{leader['team']} lead the table, but {best['team']} have the best underlying numbers.",
                f"{best['team']} sit {ordinal(best['rank'])} on {best['pts']} points yet lead the league on xG difference ({signed(best['xgd_pg'], 2)} per game vs {signed(leader['xgd_pg'], 2)}).",
                tone="warning", score=clamp_score(70 + 3 * abs(best["xgd_pg"] - leader["xgd_pg"]) * 10), confidence=confidence,
                evidence=[ev(f"{best['team']} xGD/g", signed(best["xgd_pg"], 2)), ev(f"{leader['team']} xGD/g", signed(leader["xgd_pg"], 2))],
                entities=[{"type": "team", "name": best["team"]}, {"type": "team", "name": leader["team"]}], link=team_link(best["team"])))

    # -- the table lies: points vs expected points
    if solid:
        for row in sorted(rows, key=lambda r: -abs(_gap_z(r)))[:3]:
            z = _gap_z(row)
            if abs(z) < 1.2:
                continue
            lucky = row["xpts_gap"] > 0
            verb = "more" if lucky else "fewer"
            out.append(Insight(
                f"league.gap.{row['team']}", "table",
                f"{row['team']} have {f1(abs(row['xpts_gap']))} {verb} points than their chances deserve.",
                (f"{row['pts']} points against {f1(row['xpts'])} expected: they rank {ordinal(row['rank'])} but {ordinal(row['rank_xpts'])} on xPTS. Gaps this size tend to shrink over a season, so expect the results to drift toward the performances."
                 if lucky else
                 f"{row['pts']} points against {f1(row['xpts'])} expected: they rank {ordinal(row['rank'])} but {ordinal(row['rank_xpts'])} on xPTS. They are creating more than they are collecting, and that usually corrects."),
                tone="warning" if lucky else "positive", score=clamp_score(48 + 22 * min(abs(z), 3)), confidence=confidence,
                evidence=[ev("Points", row["pts"]), ev("xPTS", f1(row["xpts"])), ev("Gap", signed(row["xpts_gap"]) + " pts"), ev("Matches", row["played"])],
                entities=[{"type": "team", "name": row["team"]}], link=team_link(row["team"])))

    # -- finishing and defensive luck (team level)
    if solid:
        for row in rows:
            z = _finishing_z(row["g_xg"], row["xg"])
            if abs(z) >= 1.6:
                hot = row["g_xg"] > 0
                out.append(Insight(
                    f"league.finish.{row['team']}", "finishing",
                    f"{row['team']} have scored {f1(abs(row['g_xg']))} {'more' if hot else 'fewer'} goals than their chances suggest.",
                    ("A finishing run like this is rarely sustained; the attack itself is producing "
                     f"{f2(row['xg_pg'])} xG per game.") if hot else
                    (f"The attack is creating {f2(row['xg_pg'])} xG per game, so the goals should come."),
                    tone="warning" if hot else "positive", score=clamp_score(40 + 18 * min(abs(z), 3.2)), confidence=confidence,
                    evidence=[ev("Goals", row["gf"]), ev("xG", f1(row["xg"])), ev("z", signed(z, 1))],
                    entities=[{"type": "team", "name": row["team"]}], link=team_link(row["team"])))
            z_def = _finishing_z(row["xga_ga"], row["xga"])
            if abs(z_def) >= 1.7:
                good = row["xga_ga"] > 0
                out.append(Insight(
                    f"league.defluck.{row['team']}", "finishing",
                    f"{row['team']} have conceded {f1(abs(row['xga_ga']))} {'fewer' if good else 'more'} goals than the chances against them imply.",
                    "Good goalkeeping can be real, but over a season most of this gap is opposition finishing luck." if good else
                    "Conceding more than the chances imply points to poor goalkeeping or bad luck; both tend to regress.",
                    tone="warning" if good else "positive", score=clamp_score(36 + 16 * min(abs(z_def), 3.2)), confidence=confidence,
                    evidence=[ev("Conceded", row["ga"]), ev("xGA", f1(row["xga"])), ev("z", signed(z_def, 1))],
                    entities=[{"type": "team", "name": row["team"]}], link=team_link(row["team"])))

    # -- form swing: last six vs the season
    if rounds >= 10:
        for row in rows:
            trend = row.get("trend_xgd") or []
            if len(trend) < 6:
                continue
            recent = trend[-1]  # rolling 5-match xGD per game
            swing = recent - row["xgd_pg"]
            if abs(swing) >= 0.55:
                up = swing > 0
                out.append(Insight(
                    f"league.form.{row['team']}", "form",
                    f"{row['team']} {'are surging' if up else 'have lost their edge'}: xG difference {signed(recent, 2)} per game over the last five, against {signed(row['xgd_pg'], 2)} for the season.",
                    "Underlying form moves before results do." if up else "The dip is in the chances, not just the scorelines.",
                    tone="positive" if up else "negative", score=clamp_score(42 + 30 * min(abs(swing), 1.2)), confidence="medium",
                    evidence=[ev("Last 5 xGD/g", signed(recent, 2)), ev("Season xGD/g", signed(row["xgd_pg"], 2)), ev("Form", "".join(c.upper() for c in row["form"]))],
                    entities=[{"type": "team", "name": row["team"]}], link=team_link(row["team"])))

    # -- best underlying team outside the top places / relegation candidates who deserve better
    if solid:
        bottom_line = len(rows) - relegation_places
        for row in rows[bottom_line:]:
            if row["rank_xpts"] <= bottom_line - 1 and row["xpts_gap"] < -2:
                out.append(Insight(
                    f"league.escape.{row['team']}", "table",
                    f"{row['team']} are in the bottom three but rank {ordinal(row['rank_xpts'])} on expected points.",
                    f"{f1(abs(row['xpts_gap']))} points short of what their chances warrant; their performances are those of a mid-table side.",
                    tone="positive", score=clamp_score(62 + 4 * abs(row["xpts_gap"])), confidence=confidence,
                    evidence=[ev("Position", ordinal(row["rank"])), ev("xPTS rank", ordinal(row["rank_xpts"])), ev("Gap", signed(row["xpts_gap"]) + " pts")],
                    entities=[{"type": "team", "name": row["team"]}], link=team_link(row["team"])))

    # -- style outliers
    pressing = [r for r in rows if r["ppda"]]
    if pressing and solid:
        hardest = min(pressing, key=lambda r: r["ppda"])
        avg = sum(r["ppda"] for r in pressing) / len(pressing)
        if hardest["ppda"] < 0.8 * avg:
            out.append(Insight(
                "league.press", "style",
                f"{hardest['team']} press harder than anyone: PPDA {f1(hardest['ppda'])} against a league average of {f1(avg)}.",
                "Opponents get through only that many passes per defensive action before the press wins the ball or forces an error.",
                tone="info", score=55, confidence=confidence,
                evidence=[ev("PPDA", f1(hardest["ppda"])), ev("League avg", f1(avg))],
                entities=[{"type": "team", "name": hardest["team"]}], link=team_link(hardest["team"])))

    # -- venue splits are handled on team pages; league pace as context
    if context.get("matches_played", 0) >= 30:
        out.append(Insight(
            "league.pace", "info",
            f"{f2(context['goals_pg'])} goals per game, with home sides winning {round(100 * context['home_win'])}% of matches.",
            f"Expected goals average {f2(context['xg_pg'])} per game; draws are {round(100 * context['draw'])}%.",
            tone="info", score=20, confidence="high",
            evidence=[ev("Goals/game", f2(context["goals_pg"])), ev("xG/game", f2(context["xg_pg"])), ev("Home win", f"{round(100 * context['home_win'])}%")]))
    return out
