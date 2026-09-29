"""Side-by-side comparison of players or teams."""

from __future__ import annotations

from typing import Sequence

from app.data.models import LeagueSeason
from app.errors import BadRequest

from .metrics import METRIC_BY_KEY, PROFILE_METRICS
from .table import compute_table, team_percentiles
from .team import find_team

SHARED_PLAYER_METRICS = ("npxg90", "shots90", "xgps", "xa90", "kp90", "xgchain90", "xgbuildup90")
MAX_PLAYERS = 6


def compare_players(rows: Sequence[dict]) -> dict:
    if len(rows) < 2:
        raise BadRequest("Pick at least two players to compare.")
    if len(rows) > MAX_PLAYERS:
        raise BadRequest(f"Compare at most {MAX_PLAYERS} players at once.")
    groups = {r["group"] for r in rows}
    mixed = len(groups) > 1
    keys = SHARED_PLAYER_METRICS if mixed else tuple(k for k in PROFILE_METRICS.get(rows[0]["group"], SHARED_PLAYER_METRICS) if k != "yellow90")
    if "GK" in groups:
        raise BadRequest("Goalkeepers cannot be compared: Understat has no goalkeeping data.")

    metrics = []
    for key in keys:
        m = METRIC_BY_KEY[key]
        values = [r.get(key) for r in rows]
        eligible = [(v, i) for i, v in enumerate(values) if v is not None and rows[i]["minutes"] >= 270]
        best = None
        if len(eligible) >= 2:
            best = (max(eligible) if m.higher_is_better else min(eligible))[1]
        metrics.append(
            {
                "key": key, "label": m.label, "short": m.short, "decimals": m.decimals, "higher_is_better": m.higher_is_better,
                "values": values, "pct": [r["pct"].get(key) for r in rows], "best": best,
            }
        )
    return {
        "players": [
            {k: r.get(k) for k in ("id", "name", "team", "league", "age", "group", "minutes", "games", "output", "tags", "sample", "pool_n",
                                    "goals", "xg", "assists", "xa", "shots", "g_xg", "g_xg_z", "npxg", "group_source")}
            for r in rows
        ],
        "metrics": metrics,
        "mixed_groups": mixed,
        "note": "Players come from different role groups; percentiles are each measured against their own peers." if mixed else None,
    }


def player_comparison_facts(rows: Sequence[dict], min_gap: float = 0.25) -> list[dict]:
    """The three biggest relative differences between the first two players."""
    a, b = rows[0], rows[1]
    if a["minutes"] < 450 or b["minutes"] < 450:
        return []
    facts = []
    for key in SHARED_PLAYER_METRICS + ("contrib90",):
        va, vb = a.get(key) or 0.0, b.get(key) or 0.0
        base = min(va, vb)
        if base <= 0.02:
            continue
        diff = max(va, vb) / base - 1
        if diff >= min_gap:
            leader, trailer = (a, b) if va > vb else (b, a)
            facts.append({"key": key, "leader": leader["name"], "trailer": trailer["name"], "relative": round(diff, 2),
                          "leader_value": max(va, vb), "trailer_value": min(va, vb)})
    facts.sort(key=lambda f: -f["relative"])
    return facts[:3]


TEAM_COMPARE_KEYS = (
    ("pts_pg", "Points per game", True), ("xpts_pg", "xPTS per game", True), ("xg_pg", "xG per game", True), ("xga_pg", "xGA per game", False),
    ("xgd_pg", "xG difference per game", True), ("gf_pg", "Goals per game", True), ("ga_pg", "Goals against per game", False),
    ("ppda", "PPDA (pressing)", False), ("oppda", "Opponent PPDA", True), ("deep_pg", "Deep completions", True), ("deep_allowed_pg", "Deep completions allowed", False),
)


def compare_teams(ls: LeagueSeason, name_a: str, name_b: str) -> dict:
    a, b = find_team(ls, name_a), find_team(ls, name_b)
    if a.name == b.name:
        raise BadRequest("Pick two different teams.")
    table = compute_table(ls)
    ra = next(r for r in table if r["team"] == a.name)
    rb = next(r for r in table if r["team"] == b.name)
    metrics = []
    for key, label, hib in TEAM_COMPARE_KEYS:
        va, vb = ra.get(key), rb.get(key)
        best = None
        if va is not None and vb is not None and abs(va - vb) > 1e-9:
            best = 0 if (va > vb) == hib else 1
        metrics.append({"key": key, "label": label, "a": va, "b": vb, "best": best, "higher_is_better": hib})

    meetings = []
    for f in sorted(ls.fixtures, key=lambda f: f.dt):
        if {f.home, f.away} == {a.name, b.name}:
            meetings.append({"id": f.id, "date": f.date, "home": f.home, "away": f.away, "played": f.played, "hg": f.hg, "ag": f.ag,
                             "hxg": f.hxg, "axg": f.axg,
                             "forecast": None if f.forecast is None else dict(zip(("home", "draw", "away"), f.forecast))})

    def series(team):
        return [round(m.xgd, 3) for m in team.history]

    return {
        "a": {"team": a.name, "short": a.short, "row": ra, "percentiles": team_percentiles(table, a.name)},
        "b": {"team": b.name, "short": b.short, "row": rb, "percentiles": team_percentiles(table, b.name)},
        "metrics": metrics,
        "meetings": meetings,
        "xgd_by_match": {"a": series(a), "b": series(b)},
    }
