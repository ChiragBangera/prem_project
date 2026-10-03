"""What the shots say about a match."""

from __future__ import annotations

from .core import Insight, clamp_score, ev, f1, f2, match_link, pct


def match_insights(report: dict) -> list[Insight]:
    fx, dv, summary = report["fixture"], report["deserved"], report["summary"]
    home, away = fx["home"], fx["away"]
    hg, ag = fx["hg"], fx["ag"]
    hxg, axg = summary["home"]["xg"], summary["away"]["xg"]
    link = match_link(fx["id"])
    ent = [{"type": "team", "name": home}, {"type": "team", "name": away}]
    out: list[Insight] = []

    score = f"{home} {hg}–{ag} {away}"
    winner_side = dv["actual"]
    p_actual = dv["actual_probability"]
    if winner_side != "draw":
        winner = home if winner_side == "home" else away
        loser = away if winner_side == "home" else home
        if p_actual < 0.25:
            fav = home if dv["home"] > dv["away"] else away
            out.append(Insight(
                f"match.{fx['id']}.against", "match",
                f"{winner} won against the run of play: the chances give them a {pct(p_actual)} chance of winning, and {fav} a {pct(max(dv['home'], dv['away']))} one.",
                f"{score}, xG {f1(hxg)}–{f1(axg)}. Replay the same chances and this result is the exception.", tone="warning",
                score=clamp_score(70 + 60 * (0.25 - p_actual)), confidence="high",
                evidence=[ev("xG", f"{f1(hxg)}–{f1(axg)}"), ev(f"{winner} win prob.", pct(p_actual))], entities=ent, link=link))
        elif p_actual >= 0.6:
            out.append(Insight(
                f"match.{fx['id']}.deserved", "match",
                f"{winner} deserved it: they had a {pct(p_actual)} chance of winning from the chances created.",
                f"{score}, xG {f1(hxg)}–{f1(axg)}.", tone="neutral", score=40, confidence="high",
                evidence=[ev("xG", f"{f1(hxg)}–{f1(axg)}"), ev("Win prob.", pct(p_actual))], entities=ent, link=link))
        else:
            out.append(Insight(
                f"match.{fx['id']}.close", "match",
                f"{winner} edged a tight one: from the chances, {winner} win {pct(p_actual)} of the time, {loser} {pct(dv['home'] if loser == home else dv['away'])}.",
                f"{score}, xG {f1(hxg)}–{f1(axg)}.", tone="neutral", score=38, confidence="high",
                evidence=[ev("xG", f"{f1(hxg)}–{f1(axg)}")], entities=ent, link=link))
    else:
        better = home if dv["home"] > dv["away"] else away
        p_better = max(dv["home"], dv["away"])
        p_worse = min(dv["home"], dv["away"])
        if p_better >= 0.5:
            headline = f"{better} were the better side on chances and only drew: from these chances they win {pct(p_better)} of the time, {away if better == home else home} {pct(p_worse)}."
            score_value, tone = 58 + 40 * (p_better - 0.5), "warning"
        else:
            headline = f"A fair draw: {score}, with the chances almost level (xG {f1(hxg)}–{f1(axg)})."
            score_value, tone = 36, "neutral"
        out.append(Insight(
            f"match.{fx['id']}.draw", "match", headline,
            f"On the chances created: home win {pct(dv['home'])}, draw {pct(dv['draw'])}, away win {pct(dv['away'])}.", tone=tone,
            score=clamp_score(score_value), confidence="high", evidence=[ev("xG", f"{f1(hxg)}–{f1(axg)}")], entities=ent, link=link))

    # dominance of chance creation
    total = hxg + axg
    if total > 0.5 and abs(hxg - axg) / total >= 0.45:
        dom, dom_xg, other_xg = (home, hxg, axg) if hxg > axg else (away, axg, hxg)
        out.append(Insight(
            f"match.{fx['id']}.dominance", "match",
            f"{dom} created {round(100 * dom_xg / total)}% of the chances ({f1(dom_xg)} xG to {f1(other_xg)}).", "",
            tone="info", score=44, confidence="high", evidence=[ev("xG", f"{f1(hxg)}–{f1(axg)}")], entities=ent, link=link))

    # the moment
    key = report["key_chances"][0] if report["key_chances"] else None
    if key and key["xg"] >= 0.45:
        team = home if key["side"] == "h" else away
        outcome = "scored" if key["result"] == "Goal" else "missed" if key["result"] in ("MissedShots", "ShotOnPost") else "saw it saved" if key["result"] == "SavedShot" else "was blocked"
        out.append(Insight(
            f"match.{fx['id']}.moment", "match",
            f"Biggest chance: {key['player']} ({team}) {outcome} a {f2(key['xg'])} xG opportunity in minute {key['minute']}.",
            "A chance this good is converted about " + pct(key["xg"]) + " of the time.", tone="neutral", score=34, confidence="high",
            evidence=[ev("xG", f2(key["xg"])), ev("Minute", key["minute"])], entities=ent, link=link))

    # timing
    for side, name in (("home", home), ("away", away)):
        buckets = report["buckets"][side]
        total_side = sum(buckets) or 1
        late = sum(buckets[-2:]) / total_side
        if total_side > 1.0 and late >= 0.6:
            out.append(Insight(
                f"match.{fx['id']}.late.{side}", "match",
                f"{name} created {round(100 * late)}% of their xG after the 60th minute.", "A late surge, or the game opening up as it went on.",
                tone="info", score=30, confidence="medium", evidence=[ev("Late xG share", f"{round(100 * late)}%")], entities=ent, link=link))
    if report["own_goals"]["home"] or report["own_goals"]["away"]:
        og = "home" if report["own_goals"]["home"] else "away"
        beneficiary = home if og == "home" else away
        out.append(Insight(f"match.{fx['id']}.og", "match", f"An own goal helped {beneficiary}: the scoreline includes a goal that is not a shot.", "",
                           tone="info", score=26, confidence="high", entities=ent, link=link))
    return out
