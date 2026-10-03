"""The team "Chances" tab: Understat's breakdowns of chances created and allowed, made readable.

Three jobs, all pure functions over the raw ``groups`` of a team page:

* :func:`prepare_breakdowns` orders rows sensibly, names them, adds the derived numbers the UI needs
  (per-game or per-90 rates, xG per shot, share of the total, goals minus xG) and the plain-language
  guide for each breakdown;
* :func:`league_baseline` / :func:`compare_to_league` put a team's rows next to every other team's, so
  "good" and "bad" mean something (rank and z-score against the league);
* :func:`chance_insights` turns the most unusual numbers into specific, evidence-backed findings.
"""

from __future__ import annotations

import math

from app.insights.core import Insight, ev, ordinal

MIN_LEAGUE_TEAMS = 8  # below this a rank or an average against "the league" is not meaningful
MIN_ROW_SHOTS = 15  # shots for + against; smaller rows are noise
MIN_FORMATION_MINUTES = 450
MIN_MINUTES = {"formation": MIN_FORMATION_MINUTES, "gameState": 150}  # rows measured per 90 need this many minutes behind them

# metric key -> (label, better) where better is "high", "low" or None (identity, not quality)
METRICS: dict[str, tuple[str, str | None]] = {
    "per_for": ("chances created", "high"),
    "per_against": ("chances allowed", "low"),
    "xg_shot": ("quality of shots taken", "high"),
    "a_xg_shot": ("quality of shots allowed", "low"),
    "share_for": ("share of the team's xG", None),
    "share_against": ("share of the xG it allows", None),
}

BREAKDOWNS: list[dict] = [
    {
        "key": "situation", "label": "Situation", "viz": "bars",
        "blurb": "How the move started: open play, corner, free kick or penalty.",
        "what": "Every shot is filed by the situation it came from. It answers: is this team's attack built on open play or on dead balls, and does it concede the same way?",
        "read": "Each row pairs the xG created (blue) with the xG allowed (orange). The tick marks the league average; the chip is the league rank, 1st being best.",
        "good": "Blue longer than orange in the big rows, especially open play, which is the most repeatable source.",
        "bad": "A lot of xG from penalties or set pieces makes an attack easier to shut down. Conceding heavily from corners points at set-piece defending.",
    },
    {
        "key": "shotZone", "label": "Shot zone", "viz": "pitch",
        "blurb": "Where on the pitch the shot was taken.",
        "what": "Shots are grouped by area: inside the six-yard box, the rest of the penalty area, and outside the box.",
        "read": "The stronger the colour, the more xG per game. The left pitch is where the team creates chances, the right is where it allows them. Hover a zone for shots, quality per shot and league rank.",
        "good": "Lots of xG from the six-yard box and penalty area, and few shots allowed there.",
        "bad": "Many shots from outside the box add up to little xG. Conceding a lot inside the six-yard box is the most dangerous leak.",
    },
    {
        "key": "timing", "label": "Timing", "viz": "columns",
        "blurb": "Which stretch of the match the shot came in.",
        "what": "Shots are grouped in 15-minute spells (the last group, 76+, includes stoppage time).",
        "read": "Read left to right as the match unfolds: blue is created, orange is allowed, the tick is the league average, and the number underneath is the net.",
        "good": "Positive net in the opening and closing spells: starting fast and finishing strong.",
        "bad": "A negative net late on can mean fading fitness or a defence that drops too deep once ahead.",
    },
    {
        "key": "gameState", "label": "Game state", "viz": "columns",
        "blurb": "The score at the time of the shot.",
        "what": "Shots are grouped by the goal difference when they were taken, so you can see how the team behaves when level, ahead or behind. Rates are per 90 minutes spent in that state.",
        "read": "Columns are per 90 minutes spent in that state, so a state the team rarely sees is not drowned out. Blue is created, orange is allowed, the tick is the league average.",
        "good": "Creating more when behind shows a team that keeps pushing; still creating when ahead shows it does not just park the bus.",
        "bad": "Allowing far more when ahead means a lead is hard to protect. Rows with only a few minutes are noise.",
    },
    {
        "key": "attackSpeed", "label": "Attack speed", "viz": "columns",
        "blurb": "How quickly the move built up.",
        "what": "Understat labels each shot by how quick the attack was (Slow, Standard, Normal, Fast). Understat does not publish the exact cut-offs.",
        "read": "Columns run from slowest to fastest build-up. Blue is created, orange is allowed, the tick is the league average, and the number underneath is the net.",
        "good": "High xG per shot in the speed the team uses most: it means that style produces good chances, not just shots.",
        "bad": "A lot of shots from one style with low xG per shot means that route is not creating much.",
    },
    {
        "key": "formation", "label": "Formation", "viz": "bars",
        "blurb": "The shape the team played in.",
        "what": "Chances created and allowed while the team lined up in each formation, with the minutes it played that way.",
        "read": "Minutes matter most: judge a formation only if it was used for a good stretch. Rates are per 90 minutes so formations of different lengths compare fairly.",
        "good": "A formation with a clearly higher net per 90 and plenty of minutes.",
        "bad": "Rows with under about 450 minutes are too short to trust and are dimmed.",
    },
    {
        "key": "result", "label": "Shot result", "viz": "outcome",
        "blurb": "What happened to the shot.",
        "what": "Every shot ends as a goal, a save, a block, a miss, or a hit on the post. The xG shown is the value of the shots that ended that way.",
        "read": "Each bar is every shot the team took (or faced), split by how it ended. The tiles beneath turn that into rates you can compare.",
        "good": "Many shots on target (goals and saves) and few blocked.",
        "bad": "A large blocked share means shooting from congested spots. Many misses with high xG are chances that should have been on target.",
    },
]
GROUP_KEYS = [b["key"] for b in BREAKDOWNS]

ROW_INFO: dict[str, dict[str, tuple[str, str]]] = {
    "situation": {
        "OpenPlay": ("Open play", "Shots from normal passages of play."),
        "FromCorner": ("Corners", "Shots that came from a corner."),
        "SetPiece": ("Set pieces", "Shots from other set-piece situations, such as indirect free kicks."),
        "DirectFreekick": ("Direct free kicks", "Shots taken straight from a free kick."),
        "Penalty": ("Penalties", "Penalty kicks. Each is worth about 0.76 xG."),
    },
    "shotZone": {
        "shotOboxTotal": ("Outside the box", "Shots from beyond the penalty area. Rarely good chances."),
        "shotPenaltyArea": ("Penalty area", "Shots inside the box but outside the six-yard box."),
        "shotSixYardBox": ("Six-yard box", "Shots from the small box right in front of goal. The best chances on the pitch."),
    },
    "timing": {
        "1-15": ("1–15 min", "The first quarter of an hour."),
        "16-30": ("16–30 min", "Minutes 16 to 30."),
        "31-45": ("31–45 min", "The end of the first half."),
        "46-60": ("46–60 min", "The start of the second half."),
        "61-75": ("61–75 min", "Minutes 61 to 75."),
        "76+": ("76+ min", "The closing stretch, including stoppage time."),
    },
    "gameState": {
        "Goal diff < -1": ("Behind by 2+", "Shots taken while trailing by two or more goals."),
        "Goal diff -1": ("Behind by 1", "Shots taken while trailing by one goal."),
        "Goal diff 0": ("Level", "Shots taken with the score level."),
        "Goal diff +1": ("Ahead by 1", "Shots taken while leading by one goal."),
        "Goal diff > +1": ("Ahead by 2+", "Shots taken while leading by two or more goals."),
    },
    "attackSpeed": {
        "Slow": ("Slow", "The slowest, most patient build-ups."),
        "Standard": ("Standard", "Understat's 'Standard' pace of attack."),
        "Normal": ("Normal", "Understat's 'Normal' pace of attack."),
        "Fast": ("Fast", "Quick attacks, such as counters."),
    },
    "result": {
        "Goal": ("Goals", "Shots that scored."),
        "SavedShot": ("Saved", "On target, stopped by the goalkeeper."),
        "ShotOnPost": ("Hit the post", "Shots that hit the woodwork."),
        "BlockedShot": ("Blocked", "Shots blocked by a defender."),
        "MissedShots": ("Off target", "Shots that missed the goal."),
    },
}
# how a row reads inside a sentence ("... from corners", "... in the 76+ min spell"); anything not listed reads "from <label>"
WHERE: dict[tuple[str, str], str] = {
    ("situation", "OpenPlay"): "in open play",
    ("shotZone", "shotPenaltyArea"): "from the penalty area",
    ("shotZone", "shotSixYardBox"): "from the six-yard box",
}


def where(group: str, row: dict) -> str:
    label = row["label"].lower()
    if (group, row["name"]) in WHERE:
        return WHERE[(group, row["name"])]
    return {"timing": f"in the {row['label']} spell", "gameState": f"when {label}", "attackSpeed": f"from {label} attacks"}.get(group, f"from {label}")


ORDER: dict[str, list[str]] = {g: list(rows) for g, rows in ((g, ROW_INFO[g]) for g in ROW_INFO)}


def _pretty(group: str, name: str) -> tuple[str, str]:
    return ROW_INFO.get(group, {}).get(name, (name, ""))


def _ordered(group: str, rows: list[dict]) -> list[dict]:
    if group == "formation":
        return sorted(rows, key=lambda r: -(r.get("time") or 0))
    order = ORDER.get(group, [])
    index = {n: i for i, n in enumerate(order)}
    return sorted(rows, key=lambda r: index.get(r["name"], len(order)))


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def prepare_breakdowns(groups: dict[str, list[dict]], games: int) -> list[dict]:
    """The raw team-page groups, ordered and enriched. Groups Understat did not return are left out."""
    out = []
    for info in BREAKDOWNS:
        key = info["key"]
        raw = list(groups.get(key) or [])
        note = None
        if key == "shotZone":
            own = [r for r in raw if r["name"] == "ownGoals"]
            raw = [r for r in raw if r["name"] != "ownGoals"]
            if own and (own[0]["goals"] or own[0]["against"]["goals"]):
                note = (
                    f"Own goals are not a zone and are left out here: opponents put {own[0]['goals']} into their own net "
                    f"and this team put {own[0]['against']['goals']} into its own."
                )
        raw = [r for r in raw if r["shots"] or r["against"]["shots"] or r["xg"]]
        if not raw:
            continue
        raw = _ordered(key, raw)
        per_90 = all((r.get("time") or 0) > 0 for r in raw)
        total_for = sum(r["xg"] for r in raw) or 0.0
        total_against = sum(r["against"]["xg"] for r in raw) or 0.0
        rows = []
        for r in raw:
            a = r["against"]
            label, hint = _pretty(key, r["name"])
            scale = (90.0 / r["time"]) if per_90 else _div(1.0, games)
            per_for, per_against = r["xg"] * scale, a["xg"] * scale
            rows.append({
                "name": r["name"], "label": label, "hint": hint, "time": r.get("time"),
                "shots": r["shots"], "goals": r["goals"], "xg": round(r["xg"], 2),
                "a_shots": a["shots"], "a_goals": a["goals"], "a_xg": round(a["xg"], 2),
                "per_for": round(per_for, 3), "per_against": round(per_against, 3), "per_net": round(per_for - per_against, 3),
                "xg_shot": round(_div(r["xg"], r["shots"]), 3), "a_xg_shot": round(_div(a["xg"], a["shots"]), 3),
                "share_for": round(_div(r["xg"], total_for), 4), "share_against": round(_div(a["xg"], total_against), 4),
                "g_xg": round(r["goals"] - r["xg"], 2), "a_g_xg": round(a["goals"] - a["xg"], 2),
                "small": (per_90 and (r.get("time") or 0) < MIN_MINUTES.get(key, 0)) or (r["shots"] + a["shots"] < MIN_ROW_SHOTS),
            })
        out.append({
            "key": key, "label": info["label"], "viz": info["viz"], "blurb": info["blurb"],
            "guide": {k: info[k] for k in ("what", "read", "good", "bad")},
            "unit": "90" if per_90 else "game", "note": note, "rows": rows,
            "totals": {"xg": round(total_for, 2), "a_xg": round(total_against, 2)},
        })
    return out


# ---------------------------------------------------------------------------- league context


def _table(prepared: list[dict]) -> dict[tuple[str, str], dict]:
    return {(b["key"], r["name"]): r for b in prepared for r in b["rows"]}


def league_baseline(prepared_by_team: dict[str, list[dict]]) -> dict[tuple[str, str, str], dict[str, float]]:
    """(group, row, metric) -> {team: value}, over every team that has the row."""
    base: dict[tuple[str, str, str], dict[str, float]] = {}
    for team, prepared in prepared_by_team.items():
        for (group, name), row in _table(prepared).items():
            if group == "formation" or row["small"]:
                continue  # formation names do not line up across teams; tiny rows are noise
            for metric in METRICS:
                base.setdefault((group, name, metric), {})[team] = row[metric]
    return base


def compare_to_league(team: str, prepared: list[dict], baseline: dict) -> dict[str, dict[str, dict[str, dict]]]:
    """{group: {row: {metric: {avg, rank, of, z}}}} for one team. Rank 1 is best (or highest for identity metrics)."""
    out: dict[str, dict[str, dict[str, dict]]] = {}
    for group, name in _table(prepared):
        for metric, (_label, better) in METRICS.items():
            values = baseline.get((group, name, metric))
            if not values or team not in values or len(values) < MIN_LEAGUE_TEAMS:
                continue
            xs = list(values.values())
            mean = sum(xs) / len(xs)
            sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
            mine = values[team]
            ahead = sum(1 for x in xs if (x < mine if better == "low" else x > mine))
            out.setdefault(group, {}).setdefault(name, {})[metric] = {
                "avg": round(mean, 4), "rank": ahead + 1, "of": len(xs), "z": round((mine - mean) / sd, 2) if sd > 1e-9 else 0.0,
            }
    return out


# ---------------------------------------------------------------------------- insights


def _rank_phrase(metric: str, rank: int, of: int) -> str:
    better = METRICS[metric][1]
    if rank == 1:
        return {"high": f"the most in the league (1st of {of})", "low": f"the fewest in the league (1st of {of})"}.get(better or "", f"the highest in the league (1st of {of})")
    if rank == of:
        return {"high": f"the least in the league ({ordinal(rank)} of {of})", "low": f"the most in the league ({ordinal(rank)} of {of})"}.get(better or "", f"the lowest in the league ({ordinal(rank)} of {of})")
    return f"{ordinal(rank)} of {of}"


def _confidence(row: dict) -> str:
    n = row["shots"] + row["a_shots"]
    return "high" if n >= 120 else "medium" if n >= 45 else "low"


def _fmt(metric: str, value: float, unit: str) -> str:
    if metric in ("share_for", "share_against"):
        return f"{100 * value:.0f}%"
    if metric in ("xg_shot", "a_xg_shot"):
        return f"{value:.2f}"
    return f"{value:.2f} xG" + (" per 90" if unit == "90" else " per game")


def _league_insight(team: str, group: dict, row: dict, metric: str, stat: dict) -> Insight | None:
    _label, better = METRICS[metric]
    key = group["key"]
    if key == "result" and metric != "share_for":
        return None  # a league rank of "xG of blocked shots" says little; only the share of xG per outcome does
    if key == "gameState" and metric.startswith("share"):
        return None  # how much xG falls in a game state mostly reflects how long the team spent there
    if (metric == "xg_shot" and row["shots"] < 25) or (metric == "a_xg_shot" and row["a_shots"] < 25):
        return None  # xG per shot from a handful of shots is noise
    z = stat["z"]
    unit = group["unit"]
    value = row[metric]
    phrase = _rank_phrase(metric, stat["rank"], stat["of"])
    lower = row["label"].lower()
    place = where(key, row)
    good = None if better is None else (z > 0) == (better == "high")
    tone = "neutral" if good is None else "positive" if good else "negative"
    if metric == "per_for":
        head = f"{team} create {'more' if z > 0 else 'fewer'} chances than most {place}: {_fmt(metric, value, unit)}, {phrase}."
    elif metric == "per_against":
        head = f"{team} allow {'more' if z > 0 else 'fewer'} chances than most {place}: {_fmt(metric, value, unit)}, {phrase}."
    elif metric == "xg_shot":
        head = f"Their shots {place} are {'better' if z > 0 else 'poorer'} than most: {value:.2f} xG a shot, {phrase}."
    elif metric == "a_xg_shot":
        head = f"Opponents' shots {place} are {'better' if z > 0 else 'poorer'} than most: {value:.2f} xG a shot, {phrase}."
    elif metric == "share_for" and key == "result":
        head = f"{_fmt(metric, value, unit)} of their xG came in shots that ended as {lower}, {'more' if z > 0 else 'less'} than most teams."
    elif metric == "share_for":
        head = f"{_fmt(metric, value, unit)} of their xG comes {place}, {'more' if z > 0 else 'less'} than most teams."
    else:
        head = f"{_fmt(metric, value, unit)} of the xG they allow comes {place}, {'more' if z > 0 else 'less'} than most teams."
    detail = {
        "per_for": "Compared with every team's rate for the same kind of chance.",
        "per_against": "Lower is better here: it is chances the team gives away.",
        "xg_shot": "xG per shot shows whether a route produces good chances or just volume.",
        "a_xg_shot": "Lower is better: it is how good the shots the team lets opponents take are.",
        "share_for": "This describes the team's style rather than its quality.",
        "share_against": "This describes how the team leaks rather than how much.",
    }[metric]
    return Insight(
        id=f"chances.{group['key']}.{row['name']}.{metric}", kind="chances", tone=tone, score=min(95.0, 40 + 12 * abs(z)),
        confidence=_confidence(row), headline=head, detail=detail,
        evidence=[ev("This team", _fmt(metric, value, unit)), ev("League average", _fmt(metric, stat["avg"], unit)), ev("Rank", f"{stat['rank']} of {stat['of']}")],
    )


def _finishing_insight(team: str, group: dict, row: dict) -> Insight | None:
    gap = row["g_xg"]
    if row["shots"] < 20 or abs(gap) < max(3.0, 0.3 * row["xg"]):
        return None
    over = gap > 0
    return Insight(
        id=f"chances.{group['key']}.{row['name']}.finishing", kind="chances", tone="warning" if over else "info",
        score=min(90.0, 45 + 4 * abs(gap)), confidence=_confidence(row),
        headline=f"{where(group['key'], row).capitalize()} {team} scored {row['goals']} from {row['xg']:.1f} xG, {abs(gap):.1f} {'above' if over else 'below'} what the chances were worth.",
        detail="A run this far from xG is mostly finishing luck, so expect it to drift back." if over else "Under-performing the chances often corrects itself if the chances keep coming.",
        evidence=[ev("Goals", str(row["goals"])), ev("xG", f"{row['xg']:.1f}"), ev("Difference", f"{gap:+.1f}")],
    )


def _own_insights(team: str, group: dict) -> list[Insight]:
    """Findings that need no league: the team against itself."""
    key, rows = group["key"], [r for r in group["rows"] if not r["small"]]
    found: list[Insight] = []
    if not rows:
        return found
    if key == "timing":
        best = max(rows, key=lambda r: r["per_net"])
        worst = min(rows, key=lambda r: r["per_net"])
        if best["per_net"] - worst["per_net"] >= 0.15:
            found.append(Insight(
                id="chances.timing.spells", kind="chances", tone="neutral", score=55, confidence=_confidence(best),
                headline=f"{team} are strongest in the {best['label']} spell ({best['per_net']:+.2f} xG a game) and weakest in {worst['label']} ({worst['per_net']:+.2f}).",
                detail="Net is chances created minus chances allowed in that spell.",
                evidence=[ev("Best spell", f"{best['label']} {best['per_net']:+.2f}"), ev("Worst spell", f"{worst['label']} {worst['per_net']:+.2f}")],
            ))
    if key == "formation":
        used = [r for r in rows if (r["time"] or 0) >= MIN_FORMATION_MINUTES]
        if len(used) >= 2:
            best = max(used, key=lambda r: r["per_net"])
            worst = min(used, key=lambda r: r["per_net"])
            if best["per_net"] - worst["per_net"] >= 0.3:
                found.append(Insight(
                    id="chances.formation.better", kind="chances", tone="neutral", score=60, confidence="medium",
                    headline=f"{team} create more than they allow in a {best['label']} ({best['per_net']:+.2f} xG per 90) than in a {worst['label']} ({worst['per_net']:+.2f}).",
                    detail="Formations are used against different opponents and game states, so treat this as a hint.",
                    evidence=[ev(best["label"], f"{best['per_net']:+.2f} per 90, {best['time']} min"), ev(worst["label"], f"{worst['per_net']:+.2f} per 90, {worst['time']} min")],
                ))
    if key == "result":
        shots = sum(r["shots"] for r in group["rows"])
        by = {r["name"]: r for r in group["rows"]}
        blocked = by.get("BlockedShot", {}).get("shots", 0)
        on_target = by.get("Goal", {}).get("shots", 0) + by.get("SavedShot", {}).get("shots", 0)
        if shots >= 60:
            found.append(Insight(
                id="chances.result.mix", kind="chances", tone="neutral", score=48, confidence="medium",
                headline=f"{100 * on_target / shots:.0f}% of {team}'s shots were on target and {100 * blocked / shots:.0f}% were blocked.",
                detail="On target counts goals and saves. Blocked shots are hit into defenders before they reach the goal.",
                evidence=[ev("Shots", str(shots)), ev("On target", str(on_target)), ev("Blocked", str(blocked))],
            ))
    if key in ("situation", "attackSpeed", "shotZone"):
        top = max(rows, key=lambda r: r["share_for"])
        if top["share_for"] >= 0.3:
            found.append(Insight(
                id=f"chances.{key}.main", kind="chances", tone="neutral", score=46, confidence=_confidence(top),
                headline=f"{100 * top['share_for']:.0f}% of {team}'s xG comes {where(key, top)}.",
                detail="The biggest single source of the team's chances.",
                evidence=[ev("xG from it", f"{top['xg']:.1f}"), ev("Team total", f"{group['totals']['xg']:.1f}")],
            ))
    return found


def chance_insights(team: str, prepared: list[dict], comparison: dict | None = None) -> dict[str, list[dict]]:
    """Up to three findings per breakdown. With a league comparison they say how a number ranks; without, only what needs none."""
    out: dict[str, list[dict]] = {}
    for group in prepared:
        found: list[Insight] = _own_insights(team, group)
        for row in group["rows"]:
            if row["small"]:
                continue
            f = _finishing_insight(team, group, row) if group["key"] in ("situation", "shotZone", "attackSpeed") else None
            if f:
                found.append(f)
            for metric, stat in ((comparison or {}).get(group["key"], {}).get(row["name"], {})).items():
                if abs(stat["z"]) >= 1.0:
                    ins = _league_insight(team, group, row, metric, stat)
                    if ins:
                        found.append(ins)
        found.sort(key=lambda i: -i.score)
        seen, picked = set(), []
        for ins in found:
            marker = ins.id.rsplit(".", 1)[0]  # one finding per row, so three rows are covered rather than one row three times
            if marker in seen:
                continue
            seen.add(marker)
            picked.append(ins.to_dict())
            if len(picked) == 3:
                break
        out[group["key"]] = picked
    return out
