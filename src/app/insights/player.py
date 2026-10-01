"""What stands out about one player, and dataset-wide scouting highlights."""

from __future__ import annotations

import math
from typing import Sequence

from app.analytics.ages import sure_age
from app.analytics.metrics import EVENT_BY_KEY, EVENT_PROFILE, METRIC_BY_KEY, GROUP_LABELS

from .core import (
    Insight, clamp_score, confidence_from_minutes, ev, f1, f2, ordinal, plural, player_link, signed,
)

WORDS = {"ATT": "attackers", "MID": "midfielders", "DEF": "defenders", "GK": "goalkeepers"}
SHORT = {"npxg90": "non-penalty xG", "xa90": "xA", "kp90": "key passes", "shots90": "shots", "xgps": "shot quality",
         "xgchain90": "involvement in attacks (xGChain)", "xgbuildup90": "build-up play", "contrib90": "npxG + xA", "yellow90": "cards"}


EVENT_WORDS = {
    "def_duels90": "defensive duels", "def_duel_win": "winning defensive duels", "tackles90": "tackling", "interceptions90": "interceptions",
    "recoveries90": "ball recoveries", "aerial_win": "winning aerial duels", "fwd_pass_ratio": "forward passing", "prog_passes90": "progressive passing",
}
MIN_EVENT_PEERS = 15  # a rank among fewer role peers than this says little


def _event_value(key: str, value: float) -> str:
    m = EVENT_BY_KEY[key]
    return f"{round(100 * value)}%" if m.unit == "share" else f"{value:.{m.decimals}f} per 90"


def _event_insights(row: dict, ent: list[dict], link: dict) -> list[Insight]:
    """Strengths and a warning from the optional event data, only when enough role peers have it for a rank to mean something."""
    if row["group"] == "GK" or not row.get("ev_in_pool") or row.get("ev_pool_n", 0) < MIN_EVENT_PEERS:
        return []
    group, evpct, evrank, pool = row["group"], row["evpct"], row["evrank"], row["ev_pool_n"]
    confidence = confidence_from_minutes(row["ev_minutes"])
    out: list[Insight] = []
    ranked = sorted(((k, evpct[k]) for k in EVENT_PROFILE.get(group, ()) if k in evpct and k in EVENT_WORDS), key=lambda kv: -kv[1])
    if ranked and ranked[0][1] >= 85:
        key, p = ranked[0]
        out.append(Insight(
            f"player.{row['id']}.event_strength", "profile",
            f"{'Elite' if p >= 92 else 'Very strong'} for {EVENT_WORDS[key]}: {ordinal(evrank[key])} of {pool} {WORDS[group]} with event data ({_event_value(key, row[key])}).",
            "From WhoScored event data, ranked among players in the same role who have it.",
            tone="positive", score=clamp_score(46 + 0.45 * (p - 85) + 10), confidence=confidence,
            evidence=[ev(EVENT_BY_KEY[key].short, _event_value(key, row[key])), ev("Percentile", f"{round(p)}"), ev("Event minutes", row["ev_minutes"])],
            entities=ent, link=link))
    duels = (row.get("def_duels90") or 0) * row["ev_minutes"] / 90
    if group in ("DEF", "MID") and duels >= 25 and evpct.get("def_duel_win", 100) <= 15:
        out.append(Insight(
            f"player.{row['id']}.event_duels", "profile",
            f"Loses most of his defensive duels: wins only {round(100 * row['def_duel_win'])}% of {round(duels)}, bottom {max(1, round(evpct['def_duel_win']))}% of {WORDS[group]} with event data.",
            "A duel is a tackle, a challenge or an aerial duel as the defending side; being dribbled past or losing in the air is a loss.",
            tone="negative", score=38, confidence=confidence,
            evidence=[ev("Duel win rate", f"{round(100 * row['def_duel_win'])}%"), ev("Duels", round(duels)), ev("Event minutes", row["ev_minutes"])],
            entities=ent, link=link))
    return out


def _rate(row: dict, key: str) -> str:
    return f2(row[key]) if key != "shots90" and key != "kp90" else f1(row[key])


def player_insights(row: dict, *, finishing: dict | None = None, career: Sequence[dict] = (), similar: Sequence[dict] = (),
                    team_context: dict | None = None) -> list[Insight]:
    name, group = row["name"], row["group"]
    minutes, pct = row["minutes"], row["pct"]
    confidence = confidence_from_minutes(minutes)
    link = player_link(row["id"])
    ent = [{"type": "player", "id": row["id"], "name": name}]
    out: list[Insight] = []
    if group == "GK":
        return [Insight(f"player.{row['id']}.gk", "info", f"{name} is a goalkeeper: Understat has no goalkeeping data.",
                        "There are no shot-stopping or distribution metrics in this dataset, so this page can only describe appearances and discipline.",
                        tone="info", score=30, confidence="low")]

    # -- how good, relative to role peers
    ranked = sorted(((k, v) for k, v in pct.items() if k in ("npxg90", "xa90", "kp90", "xgbuildup90", "xgchain90", "contrib90", "shots90", "xgps")), key=lambda kv: -kv[1])
    if ranked and row.get("in_pool"):
        top_key, top_pct = ranked[0]
        rank = row["rank"].get(top_key)
        if top_pct >= 80:
            out.append(Insight(
                f"player.{row['id']}.standout", "profile",
                f"{'Elite' if top_pct >= 92 else 'Very strong'} for {SHORT[top_key]}: {ordinal(rank)} of {row['pool_n']} {WORDS[group]} ({_rate(row, top_key)} per 90).",
                f"That puts him in the top {max(1, round(100 - top_pct))}% of {WORDS[group]} with enough minutes to count.",
                tone="positive", score=clamp_score(50 + 0.45 * (top_pct - 80) + 12), confidence=confidence,
                evidence=[ev(METRIC_BY_KEY[top_key].short, _rate(row, top_key)), ev("Percentile", f"{round(top_pct)}"), ev("Minutes", minutes)],
                entities=ent, link=link))
        elif ranked[0][1] < 60:
            out.append(Insight(
                f"player.{row['id']}.average", "profile",
                f"No standout strength: his best measure ({SHORT[top_key]}) is only {ordinal(round(top_pct))} percentile among {WORDS[group]}.",
                "Understat measures attacking output; a player can contribute in ways it does not capture.", tone="neutral", score=28, confidence=confidence,
                evidence=[ev(METRIC_BY_KEY[top_key].short, _rate(row, top_key))], entities=ent, link=link))
        weak = [(k, v) for k, v in ranked if v <= 20 and k not in ("xgps",)]
        if weak and group != "DEF":
            k, v = weak[-1]
            out.append(Insight(
                f"player.{row['id']}.gap", "profile",
                f"Weakest area: {SHORT[k]} ({_rate(row, k)} per 90, bottom {max(1, round(v))}% of {WORDS[group]}).", "",
                tone="negative", score=36, confidence=confidence, evidence=[ev(METRIC_BY_KEY[k].short, _rate(row, k))], entities=ent, link=link))

    # -- defending and passing (optional event data)
    out += _event_insights(row, ent, link)

    # -- luck and sustainability (shot-level when we have the shots)
    if finishing and finishing["np_shots"] >= 20:
        luck = finishing["luck_np"]
        diff = finishing["np_goals"] - finishing["np_xg"]
        z = luck["z"]
        if abs(z) >= 1.5:
            hot = diff > 0
            prob = luck["p_at_least"] if hot else luck["p_at_most"]
            out.append(Insight(
                f"player.{row['id']}.luck", "finishing",
                f"{'Scoring' if hot else 'Scoring only'} {finishing['np_goals']} non-penalty goals from {f1(finishing['np_xg'])} xG ({signed(diff)}): a player scoring at this level or better {'happens only' if hot else 'or worse happens'} about {round(100 * prob)}% of the time on chances like these.",
                ("Some of this may be genuine finishing skill, but most seasons-long overperformance regresses: plan for fewer goals."
                 if hot else "The chances are there; the goals should follow. One of the more buyable profiles if the shot quality is real."),
                tone="warning" if hot else "positive", score=clamp_score(46 + 14 * min(abs(z), 3.5)), confidence="medium" if finishing["np_shots"] < 60 else "high",
                evidence=[ev("Goals (np)", finishing["np_goals"]), ev("xG (np)", f1(finishing["np_xg"])), ev("Shots", finishing["np_shots"]), ev("z", signed(z, 1))],
                entities=ent, link=link))
        elif finishing["np_shots"] >= 40:
            out.append(Insight(
                f"player.{row['id']}.luck", "finishing",
                f"Finishing is in line with the chances: {finishing['np_goals']} goals from {f1(finishing['np_xg'])} xG.",
                "Nothing here suggests the goal tally is inflated or suppressed.", tone="neutral", score=30, confidence="medium",
                evidence=[ev("Goals (np)", finishing["np_goals"]), ev("xG (np)", f1(finishing["np_xg"]))], entities=ent, link=link))
    elif abs(row["g_xg_z"]) >= 1.8 and row["shots"] >= 20:
        hot = row["g_xg"] > 0
        out.append(Insight(
            f"player.{row['id']}.luck", "finishing",
            f"{row['goals']} goals from {f1(row['xg'])} xG ({signed(row['g_xg'])}): {'overperforming' if hot else 'underperforming'} his chances.",
            "Based on season totals; open the shot map for the penalty-free picture.", tone="warning" if hot else "positive",
            score=clamp_score(42 + 12 * min(abs(row["g_xg_z"]), 3.5)), confidence="medium",
            evidence=[ev("Goals", row["goals"]), ev("xG", f1(row["xg"])), ev("z", signed(row["g_xg_z"], 1))], entities=ent, link=link))

    # -- age in context
    if sure_age(row) is not None and row.get("output") is not None and row.get("in_pool"):
        age, out_idx = sure_age(row), row["output"]
        if age <= 21 and out_idx >= 60:
            out.append(Insight(
                f"player.{row['id']}.young", "youth",
                f"At {age}, his all-round output ranks in the top {max(1, round(100 - out_idx))}% of {WORDS[group]}: an unusually productive young player.",
                "Role score averages his percentile across the metrics that define his role.", tone="positive",
                score=clamp_score(56 + 0.5 * (out_idx - 60) + (21 - age) * 3), confidence=confidence,
                evidence=[ev("Age", age), ev("Role score", f1(out_idx)), ev("Minutes", minutes)], entities=ent, link=link))
        elif age >= 31 and out_idx >= 75:
            out.append(Insight(
                f"player.{row['id']}.veteran", "profile",
                f"Still elite at {age}: top {max(1, round(100 - out_idx))}% of {WORDS[group]} on output.", "",
                tone="neutral", score=40, confidence=confidence, evidence=[ev("Age", age), ev("Role score", f1(out_idx))], entities=ent, link=link))

    # -- role security and minutes
    share = row["minutes_share"]
    if row["games"] >= 4:
        if share >= 0.85:
            out.append(Insight(f"player.{row['id']}.minutes", "minutes", f"Automatic starter: {round(100 * share)}% of his team's minutes.",
                               "Rates are built on a large, stable sample.", tone="neutral", score=24, confidence="high",
                               evidence=[ev("Minutes", minutes), ev("Share", f"{round(100 * share)}%")], entities=ent, link=link))
        elif row["mins_per_app"] < 45 and row["games"] >= 6:
            out.append(Insight(
                f"player.{row['id']}.impact", "minutes",
                f"Mostly used as a substitute: {row['mins_per_app']} minutes per appearance.",
                "Per-90 rates from short cameos are unreliable, and ranking treats them cautiously." + (" His rates are strong enough to deserve a longer look." if row["output"] and row["output"] >= 70 else ""),
                tone="info", score=44 if row["output"] and row["output"] >= 70 else 26, confidence="low",
                evidence=[ev("Minutes/app", row["mins_per_app"]), ev("Appearances", row["games"])], entities=ent, link=link))

    # -- trend versus previous season
    seasons = [c for c in career if c["minutes"] >= 600]
    if len(seasons) >= 2:
        prev, cur = seasons[-2], seasons[-1]
        key = "npxg90" if group == "ATT" else "xa90" if group == "MID" else "xgbuildup90"
        if prev[key] > 0.02:
            change = cur[key] / prev[key] - 1
            if abs(change) >= 0.3:
                out.append(Insight(
                    f"player.{row['id']}.trend", "trend",
                    f"{SHORT[key].capitalize()} per 90 is {'up' if change > 0 else 'down'} {round(100 * abs(change))}% on {prev['season']}/{str(prev['season'] + 1)[-2:]}: {f2(prev[key])} → {f2(cur[key])}.",
                    "", tone="positive" if change > 0 else "negative", score=clamp_score(40 + 30 * min(abs(change), 1.0)), confidence="medium",
                    evidence=[ev("Previous", f2(prev[key])), ev("Latest", f2(cur[key]))], entities=ent, link=link))

    # -- team role
    if team_context and team_context.get("chain_share", 0) >= 0.45:
        out.append(Insight(
            f"player.{row['id']}.central", "squad",
            f"Involved in {round(100 * team_context['chain_share'])}% of {team_context['team']}'s attacking chances (xGChain share).", "",
            tone="info", score=34, confidence=confidence, evidence=[ev("xGChain share", f"{round(100 * team_context['chain_share'])}%")], entities=ent, link=link))

    if similar:
        top = similar[0]
        out.append(Insight(
            f"player.{row['id']}.similar", "profile",
            f"Closest statistical match: {top['name']} ({top['team']}, similarity {round(top['similarity'])}).",
            (f"Both are strong on {', '.join(top['shared_strengths'])}." if top["shared_strengths"] else "Their profiles differ mostly in " + str(top["biggest_difference"]) + "."),
            tone="info", score=38, confidence=confidence, evidence=[ev("Similarity", round(top["similarity"])), ev("Avg gap", f"{top['avg_gap']} pct pts")],
            entities=ent + [{"type": "player", "id": top["id"], "name": top["name"]}], link=player_link(top["id"])))

    if minutes < 450:
        out.append(Insight(f"player.{row['id']}.sample", "info", f"Small sample: only {minutes} minutes.",
                           "Per-90 rates and percentiles below about 450 minutes swing wildly; treat every number here as provisional.",
                           tone="warning", score=70, confidence="low", evidence=[ev("Minutes", minutes)], entities=ent, link=link))
    return out


# ---------------------------------------------------------------------- scouting highlights


def scouting_highlights(rows: Sequence[dict], *, limit_each: int = 3) -> list[Insight]:
    """Dataset-wide: who is worth a look, and who is riding luck."""
    pool = [r for r in rows if r.get("in_pool") and r["group"] != "GK"]
    out: list[Insight] = []

    def add(insight: Insight):
        out.append(insight)

    young = sorted((r for r in pool if sure_age(r) is not None and sure_age(r) <= 21 and (r.get("output") or 0) >= 65), key=lambda r: -(r["output"] or 0))
    for r in young[:limit_each]:
        add(Insight(
            f"scout.young.{r['id']}", "youth",
            f"{r['name']} ({r['team']}), {r['age']}: top {max(1, round(100 - r['output']))}% of {WORDS[r['group']]} on output.",
            f"{f2(r['contrib90'])} npxG + xA per 90 over {r['minutes']} minutes.", tone="positive", score=clamp_score(60 + 0.4 * (r["output"] - 65)),
            confidence=confidence_from_minutes(r["minutes"]), evidence=[ev("Age", r["age"]), ev("Role score", f1(r["output"])), ev("Min", r["minutes"])],
            entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))

    hot = sorted((r for r in pool if r["shots"] >= 30 and r["g_xg_z"] >= 1.8), key=lambda r: -r["g_xg_z"])
    for r in hot[:limit_each]:
        add(Insight(
            f"scout.hot.{r['id']}", "hot",
            f"{r['name']} ({r['team']}) has {r['goals']} goals from {f1(r['xg'])} xG: expect a slowdown.",
            f"{signed(r['g_xg'])} over expectation on {r['shots']} shots.", tone="warning", score=clamp_score(46 + 12 * min(r["g_xg_z"], 3.5)),
            confidence="medium", evidence=[ev("Goals", r["goals"]), ev("xG", f1(r["xg"])), ev("z", signed(r["g_xg_z"], 1))],
            entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))

    cold = sorted((r for r in pool if r["shots"] >= 30 and r["g_xg_z"] <= -1.8), key=lambda r: r["g_xg_z"])
    for r in cold[:limit_each]:
        add(Insight(
            f"scout.cold.{r['id']}", "cold",
            f"{r['name']} ({r['team']}) has only {r['goals']} goals from {f1(r['xg'])} xG: the chances are there.",
            f"{signed(r['g_xg'])} against expectation on {r['shots']} shots; a rebound is likelier than not.", tone="positive",
            score=clamp_score(44 + 12 * min(abs(r["g_xg_z"]), 3.5)), confidence="medium",
            evidence=[ev("Goals", r["goals"]), ev("xG", f1(r["xg"])), ev("z", signed(r["g_xg_z"], 1))],
            entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))

    gems = sorted((r for r in pool if r["minutes_share"] < 0.5 and (r.get("output") or 0) >= 78 and r["minutes"] >= 270), key=lambda r: -(r["output"] or 0))
    for r in gems[:limit_each]:
        add(Insight(
            f"scout.gem.{r['id']}", "minutes",
            f"{r['name']} ({r['team']}) is top {max(1, round(100 - r['output']))}% among {WORDS[r['group']]} on output but plays only {round(100 * r['minutes_share'])}% of his team's minutes.",
            "Strong rates on limited minutes: either an unjustly used player or a small-sample mirage. Check the sample before getting excited.",
            tone="info", score=clamp_score(52 + 0.3 * (r["output"] - 78)), confidence="low" if r["minutes"] < 900 else "medium",
            evidence=[ev("Role score", f1(r["output"])), ev("Minutes", r["minutes"]), ev("Share", f"{round(100 * r['minutes_share'])}%")],
            entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))

    for group, key, label, floor in (("MID", "xgbuildup90", "build-up play", 85), ("DEF", "xgbuildup90", "build-up play", 88)):
        best = sorted((r for r in pool if r["group"] == group and r["pct"].get(key, 0) >= floor), key=lambda r: -r["pct"][key])
        for r in best[:1]:
            add(Insight(
                f"scout.builder.{group}.{r['id']}", "profile",
                f"{r['name']} ({r['team']}) is the standout {WORDS[group][:-1]} for {label}: {f2(r[key])} xGBuildup per 90.",
                f"Top {max(1, round(100 - r['pct'][key]))}% of {WORDS[group]}.", tone="positive", score=48, confidence=confidence_from_minutes(r["minutes"]),
                evidence=[ev("Buildup/90", f2(r[key])), ev("Percentile", round(r["pct"][key]))],
                entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))

    # optional event data: only players with solid minutes, ranked against enough role peers who have it
    solid = [r for r in pool if r.get("ev_in_pool") and r.get("ev_pool_n", 0) >= MIN_EVENT_PEERS and r.get("ev_minutes", 0) >= 270 and r["group"] in ("DEF", "MID")]
    for group in ("DEF", "MID"):
        winners = sorted((r for r in solid if r["group"] == group and r["evpct"].get("def_duel_win", 0) >= 85 and r["evpct"].get("def_duels90", 0) >= 60),
                         key=lambda r: -r["evpct"]["def_duel_win"])
        for r in winners[:1]:
            add(Insight(
                f"scout.winner.{group}.{r['id']}", "events",
                f"{r['name']} ({r['team']}) wins {round(100 * r['def_duel_win'])}% of his defensive duels, with {f1(r['def_duels90'])} a game: top {max(1, round(100 - r['evpct']['def_duel_win']))}% of {WORDS[group]} with event data.",
                "A duel is a tackle, a challenge or an aerial duel as the defending side. From WhoScored event data.",
                tone="positive", score=47, confidence=confidence_from_minutes(r["ev_minutes"]),
                evidence=[ev("Duel win rate", f"{round(100 * r['def_duel_win'])}%"), ev("Duels/90", f1(r["def_duels90"])), ev("Event min", r["ev_minutes"])],
                entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))
        movers = sorted((r for r in solid if r["group"] == group and r["evpct"].get("prog_passes90", 0) >= 90 and r["evpct"].get("pass_acc", 0) >= 50),
                        key=lambda r: -r["evpct"]["prog_passes90"])
        for r in movers[:1]:
            add(Insight(
                f"scout.progressor.{group}.{r['id']}", "events",
                f"{r['name']} ({r['team']}) moves the ball up the pitch more than almost any {WORDS[group][:-1]}: {f1(r['prog_passes90'])} progressive passes per 90 at {round(100 * r['pass_acc'])}% accuracy.",
                f"Top {max(1, round(100 - r['evpct']['prog_passes90']))}% of {WORDS[group]} with event data, without giving the ball away more than average.",
                tone="positive", score=46, confidence=confidence_from_minutes(r["ev_minutes"]),
                evidence=[ev("Prog/90", f1(r["prog_passes90"])), ev("Pass %", f"{round(100 * r['pass_acc'])}%"), ev("Event min", r["ev_minutes"])],
                entities=[{"type": "player", "id": r["id"], "name": r["name"]}], link=player_link(r["id"])))
    return out
