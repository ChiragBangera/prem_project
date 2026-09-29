"""What stands out about one team."""

from __future__ import annotations

import math
from typing import Sequence

from .core import (
    Insight, clamp_score, confidence_from_matches, ev, f1, f2, ordinal, plural, player_link, match_link, signed, team_link,
)

DIMENSION_PHRASES = {
    "xg_pg": ("create more chances than anyone", "create very few chances", "chance creation"),
    "npxg_pg": ("carry the biggest open-play threat", "have little open-play threat", "open-play threat"),
    "xga_pg": ("allow the fewest chances", "allow a lot of chances", "chance prevention"),
    "ppda": ("press the hardest", "press very little", "pressing"),
    "deep_pg": ("get into dangerous territory more than anyone", "rarely reach dangerous territory", "territory"),
    "deep_allowed_pg": ("keep opponents out of dangerous areas best", "let opponents into dangerous areas", "territory conceded"),
    "xgd_pg": ("have the best underlying difference", "have among the worst underlying differences", "xG difference"),
    "pts_pg": ("collect the most points", "collect the fewest points", "results"),
}


def _fmt(key: str, value: float) -> str:
    if key == "ppda":
        return f"PPDA {f1(value)}"
    if key.endswith("_pg"):
        unit = {"xg_pg": "xG", "npxg_pg": "npxG", "xga_pg": "xGA", "deep_pg": "deep completions", "deep_allowed_pg": "deep completions allowed", "xgd_pg": "xGD", "pts_pg": "points"}[key]
        return f"{f2(value)} {unit} per game" if key not in ("deep_pg", "deep_allowed_pg") else f"{f1(value)} {unit} per game"
    return f2(value)


def team_insights(profile: dict, *, ucl_places: int = 4, relegation_places: int = 3) -> list[Insight]:
    team = profile["team"]
    name, played = team["team"], team["played"]
    out: list[Insight] = []
    if played < 3:
        return [Insight(f"team.{name}.early", "info", f"{name} have played {plural(played, 'match')}: too early for meaningful patterns.", tone="info", score=30, confidence="low")]
    confidence = confidence_from_matches(played)
    link = team_link(name)
    ent = [{"type": "team", "name": name}]

    # -- table position versus process
    gap = team["rank"] - team["rank_xpts"]
    if played >= 6:
        if abs(gap) >= 3 or abs(team["xpts_gap"]) >= 1.6 * math.sqrt(played) * 0.7:
            flattered = team["xpts_gap"] > 0
            out.append(Insight(
                f"team.{name}.standing", "table",
                f"{name} are {ordinal(team['rank'])} in the table but {ordinal(team['rank_xpts'])} on expected points.",
                (f"They have {f1(team['xpts_gap'])} more points than their chances deserve, so the position flatters them." if flattered
                 else f"They have {f1(abs(team['xpts_gap']))} fewer points than their chances deserve, so the position undersells them."),
                tone="warning" if flattered else "positive", score=clamp_score(60 + 5 * min(abs(gap), 6)), confidence=confidence,
                evidence=[ev("Points", team["pts"]), ev("xPTS", f1(team["xpts"])), ev("Table rank", ordinal(team["rank"])), ev("xPTS rank", ordinal(team["rank_xpts"]))],
                entities=ent, link=link))
        else:
            out.append(Insight(
                f"team.{name}.standing", "table",
                f"{name}'s position matches their performances: {ordinal(team['rank'])} in the table, {ordinal(team['rank_xpts'])} on expected points.",
                "There is little luck to unwind, so the current level is a fair guide to what comes next.",
                tone="neutral", score=42, confidence=confidence,
                evidence=[ev("Points", team["pts"]), ev("xPTS", f1(team["xpts"]))], entities=ent, link=link))

    # -- identity: what they are best and worst at
    pcts = sorted(profile["percentiles"], key=lambda p: -p["percentile"])
    strengths = [p for p in pcts if p["percentile"] >= 85][:2]
    weaknesses = [p for p in reversed(pcts) if p["percentile"] <= 20][:2]
    for p in strengths:
        good, _bad, label = DIMENSION_PHRASES[p["key"]]
        out.append(Insight(
            f"team.{name}.strength.{p['key']}", "style",
            f"They {good}: {_fmt(p['key'], p['value'])} (top {max(1, round(100 - p['percentile']))}% of the league).",
            f"League average is {_fmt(p['key'], p['league_average'])}.",
            tone="positive", score=clamp_score(46 + 0.4 * (p["percentile"] - 80)), confidence=confidence,
            evidence=[ev(label.capitalize(), _fmt(p["key"], p["value"])), ev("League avg", _fmt(p["key"], p["league_average"]))], entities=ent, link=link))
    for p in weaknesses:
        _good, bad, label = DIMENSION_PHRASES[p["key"]]
        out.append(Insight(
            f"team.{name}.weakness.{p['key']}", "style",
            f"They {bad}: {_fmt(p['key'], p['value'])} (bottom {max(1, round(p['percentile']))}% of the league).",
            f"League average is {_fmt(p['key'], p['league_average'])}.",
            tone="negative", score=clamp_score(44 + 0.4 * (20 - p["percentile"])), confidence=confidence,
            evidence=[ev(label.capitalize(), _fmt(p["key"], p["value"])), ev("League avg", _fmt(p["key"], p["league_average"]))], entities=ent, link=link))

    # -- recent form vs season
    last6 = profile["splits"].get("last6")
    if last6 and played >= 10:
        swing = last6["xgd_pg"] - team["xgd_pg"]
        if abs(swing) >= 0.45:
            up = swing > 0
            out.append(Insight(
                f"team.{name}.form", "form",
                f"Their last six games ({signed(last6['xgd_pg'], 2)} xGD per game) are {'much better' if up else 'well below'} their season ({signed(team['xgd_pg'], 2)}).",
                f"{last6['pts']} points from six ({f2(last6['pts_pg'])} per game), against {f2(team['pts_pg'])} per game overall.",
                tone="positive" if up else "negative", score=clamp_score(48 + 35 * min(abs(swing), 1.3)), confidence="medium",
                evidence=[ev("Last 6 xGD/g", signed(last6["xgd_pg"], 2)), ev("Season xGD/g", signed(team["xgd_pg"], 2)), ev("Last 6 pts", last6["pts"])], entities=ent, link=link))

    # -- home versus away
    home, away = profile["splits"]["home"], profile["splits"]["away"]
    if home["played"] >= 5 and away["played"] >= 5:
        gap_xgd = home["xgd_pg"] - away["xgd_pg"]
        gap_pts = home["pts_pg"] - away["pts_pg"]
        if abs(gap_xgd) >= 0.7:
            better = "home" if gap_xgd > 0 else "away"
            agrees = (gap_pts > 0) == (gap_xgd > 0) and abs(gap_pts) >= 0.5
            if agrees:
                headline = (f"{name} are a {'fortress at home' if better == 'home' else 'better side away than at home'}: "
                            f"xGD {signed(home['xgd_pg'], 2)} per game at home, {signed(away['xgd_pg'], 2)} away.")
                detail = f"{f2(home['pts_pg'])} points per game at home against {f2(away['pts_pg'])} on the road."
            else:
                headline = (f"{name}'s underlying numbers are far stronger {'at home' if better == 'home' else 'away'} "
                            f"(xGD {signed(home['xgd_pg'], 2)} home, {signed(away['xgd_pg'], 2)} away), but the points have not followed.")
                detail = f"{f2(home['pts_pg'])} points per game at home against {f2(away['pts_pg'])} away, so results in one venue are running behind the performances."
            out.append(Insight(
                f"team.{name}.venue", "style", headline, detail,
                tone="neutral", score=clamp_score(38 + 22 * min(abs(gap_xgd), 1.6)), confidence=confidence,
                evidence=[ev("Home xGD/g", signed(home["xgd_pg"], 2)), ev("Away xGD/g", signed(away["xgd_pg"], 2)), ev("Home pts/g", f2(home["pts_pg"])), ev("Away pts/g", f2(away["pts_pg"]))],
                entities=ent, link=link))

    # -- trajectory across the season
    first, second = profile["splits"].get("first_half"), profile["splits"].get("second_half")
    if first and second and first["played"] >= 8 and second["played"] >= 8:
        delta = second["xgd_pg"] - first["xgd_pg"]
        if abs(delta) >= 0.5:
            out.append(Insight(
                f"team.{name}.trajectory", "form",
                f"{name} have {'improved' if delta > 0 else 'faded'} through the season: xGD {signed(first['xgd_pg'], 2)} per game in the first half, {signed(second['xgd_pg'], 2)} since.",
                f"Points per game went from {f2(first['pts_pg'])} to {f2(second['pts_pg'])}.",
                tone="positive" if delta > 0 else "negative", score=clamp_score(40 + 26 * min(abs(delta), 1.5)), confidence=confidence,
                evidence=[ev("First half xGD/g", signed(first["xgd_pg"], 2)), ev("Second half xGD/g", signed(second["xgd_pg"], 2))], entities=ent, link=link))

    # -- opposition quality
    strong, weak = profile["splits"].get("vs_stronger"), profile["splits"].get("vs_weaker")
    if strong and weak and strong["played"] >= 6 and weak["played"] >= 6:
        diff = weak["pts_pg"] - strong["pts_pg"]
        if diff >= 1.3:
            out.append(Insight(
                f"team.{name}.bully", "style",
                f"They take {f2(weak['pts_pg'])} points per game against weaker sides but only {f2(strong['pts_pg'])} against stronger ones.",
                "Results against top opposition are the better guide to a team's ceiling.",
                tone="neutral", score=clamp_score(36 + 10 * min(diff, 2.5)), confidence=confidence,
                evidence=[ev("Vs weaker", f2(weak["pts_pg"])), ev("Vs stronger", f2(strong["pts_pg"]))], entities=ent, link=link))

    # -- luckiest / unluckiest single result
    matches = profile["matches"]
    if len(matches) >= 6:
        robbed = min(matches, key=lambda m: m["luck"])
        if robbed["luck"] <= -1.6 and robbed["match_id"]:
            out.append(Insight(
                f"team.{name}.robbed", "match",
                f"Their most unlucky result: {robbed['gf']}–{robbed['ga']} {'vs' if robbed['venue'] == 'h' else 'at'} {robbed['opponent']}, despite {f1(robbed['xg'])}–{f1(robbed['xga'])} on xG.",
                f"Expected points {f1(robbed['xpts'])}, got {robbed['pts']}.", tone="neutral", score=32, confidence="high",
                evidence=[ev("xG", f"{f1(robbed['xg'])}–{f1(robbed['xga'])}"), ev("Points", f"{robbed['pts']} vs {f1(robbed['xpts'])} xPTS")],
                entities=ent + [{"type": "match", "id": robbed["match_id"]}], link=match_link(robbed["match_id"])))

    # -- what is left
    schedule = profile["schedule"]
    if schedule["remaining"] >= 4 and schedule["remaining_avg_opp"] is not None:
        rem = schedule["remaining_avg_opp"]
        if abs(rem) >= 0.18:
            tough = rem > 0
            out.append(Insight(
                f"team.{name}.run_in", "schedule",
                f"{name}'s {plural(schedule['remaining'], 'remaining game')} are {'tougher' if tough else 'easier'} than average: opponents average {signed(rem, 2)} xGD per game.",
                "Measured by each opponent's underlying xG difference so far this season.", tone="warning" if tough else "positive",
                score=clamp_score(36 + 60 * min(abs(rem), 0.5)), confidence="medium",
                evidence=[ev("Games left", schedule["remaining"]), ev("Avg opponent xGD/g", signed(rem, 2))], entities=ent, link=link))

    # -- squad
    conc = profile.get("concentration")
    if conc and played >= 8 and conc["top1_share"] >= 0.22:
        out.append(Insight(
            f"team.{name}.dependence", "squad",
            f"{conc['top_player']} accounts for {round(100 * conc['top1_share'])}% of the team's attacking output (npxG + xA); the top three account for {round(100 * conc['top3_share'])}%.",
            "A high share means the attack is exposed to one injury or one bad month.", tone="warning",
            score=clamp_score(34 + 60 * conc["top1_share"]), confidence=confidence,
            evidence=[ev("Top player share", f"{round(100 * conc['top1_share'])}%"), ev("Top three", f"{round(100 * conc['top3_share'])}%")], entities=ent, link=link))

    for row in profile.get("squad", [])[:14]:
        if row["shots"] >= 25 and row["xg"] > 1:
            p = row["xg"] / row["shots"]
            sd = math.sqrt(row["shots"] * p * (1 - p))
            z = row["g_xg"] / sd if sd else 0.0
            if z >= 1.8:
                out.append(Insight(
                    f"team.{name}.hot.{row['id']}", "finishing",
                    f"{row['name']} has {row['goals']} goals from {f1(row['xg'])} xG: a finishing run that is unlikely to last.",
                    f"{signed(row['g_xg'])} against expectation on {row['shots']} shots (z {signed(z, 1)}).",
                    tone="warning", score=clamp_score(38 + 15 * min(z, 3.5)), confidence="medium",
                    evidence=[ev("Goals", row["goals"]), ev("xG", f1(row["xg"])), ev("Shots", row["shots"])],
                    entities=ent + [{"type": "player", "id": row["id"], "name": row["name"]}], link=player_link(row["id"])))
                break

    # -- managers (user-maintained eras)
    eras = profile.get("eras") or []
    if len(eras) >= 2:
        best = max(eras, key=lambda e: e["pts_pg"] if e["played"] >= 5 else -1)
        if best["played"] >= 5:
            out.append(Insight(
                f"team.{name}.eras", "history",
                f"Under {best['manager']}, {name} average {f2(best['pts_pg'])} points and {signed(best['xgd_pg'], 2)} xGD per game ({best['played']} matches).",
                "Compare the manager windows in the table below; small windows are noisy.", tone="info", score=30, confidence="medium",
                evidence=[ev("Manager", best["manager"]), ev("Matches", best["played"])], entities=ent, link=link))
    return out
