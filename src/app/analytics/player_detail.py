"""Everything about one player: profile blocks, shot-level finishing, career, context."""

from __future__ import annotations

import math
from datetime import date
from collections.abc import Sequence

from app.data.models import CareerSeason, PlayerPage, Shot
from app.stats import per90, safe_div, shot_luck

from app.metrics.player import GROUPS, PLAYER_METRICS, PROFILE, PROFILE_FULL

from .metrics import GROUP_LABELS

PITCH_L, PITCH_W = 105.0, 68.0
_BY_KEY = {m.key: m for m in PLAYER_METRICS}


def metric_blocks(row: dict, pools: dict | None = None) -> list[dict]:
    """Every metric he has a value for, grouped as in the registry, each with its percentile among role peers and how many peers that is."""
    pools = pools or {}
    pct, rank = row.get("full_pct", {}), row.get("full_rank", {})
    blocks = []
    for group in GROUPS:
        items = []
        for metric in PLAYER_METRICS:
            if metric.group != group.key:
                continue
            value = row.get(metric.key)
            if value is None:
                continue
            items.append({
                "key": metric.key, "label": metric.label, "short": metric.short, "unit": metric.unit, "decimals": metric.decimals, "value": value,
                "pct": pct.get(metric.key), "rank": rank.get(metric.key), "pool_n": pools.get(row["group"], {}).get(metric.key),
                "higher_is_better": metric.hib is not False, "hib": metric.hib, "what": metric.what, "read": metric.read, "needs": metric.needs, "source": metric.source,
                "formula": metric.formula,
            })
        if items:
            blocks.append({"group": group.key, "category": group.label, "blurb": group.blurb, "items": items})
    return blocks


def event_summary(row: dict, pools: dict | None = None) -> dict:
    """How much event data stands behind his event metrics, so the page can say so."""
    if not row.get("ev_minutes"):
        return {"available": False}
    return {"available": True, "minutes": row["ev_minutes"], "matches": row["ev_matches"], "in_pool": row["ev_in_pool"],
            "pool_n": (pools or {}).get(row["group"], {}).get("tackles90", row.get("ev_pool_n", 0)), "pool_minutes": row["ev_pool_minutes"]}


def profile(row: dict) -> list[dict]:
    """The role's key metrics in display order, each with its percentile (the wider all-data set when event data exists)."""
    out = []
    pct, rank = row.get("full_pct", {}), row.get("full_rank", {})
    use_full = row.get("score_full") is not None
    keys = (PROFILE_FULL if use_full else PROFILE).get(row["group"], ())
    for key in keys:
        if key not in pct:
            continue
        metric = _BY_KEY[key]
        out.append({
            "key": key, "label": metric.label, "short": metric.short, "category": metric.group, "value": row.get(key), "pct": pct[key], "rank": rank.get(key),
            "decimals": metric.decimals, "unit": metric.unit, "higher_is_better": metric.hib is not False,
        })
    return out


# ---------------------------------------------------------------------- shots


def _geometry(s: Shot) -> tuple[float, float]:
    dx = (1.0 - s.x) * PITCH_L
    dy = (s.y - 0.5) * PITCH_W
    return dx, dy


def zone_of(s: Shot) -> str:
    dx, dy = _geometry(s)
    dy = abs(dy)
    if dx <= 5.5 and dy <= 9.16:
        return "Six-yard box"
    if dx <= 16.5 and dy <= 20.16:
        return "Penalty area"
    return "Outside the box"


def _group(shots: Sequence[Shot], key) -> list[dict]:
    rows: dict[str, dict] = {}
    for s in shots:
        name = key(s)
        r = rows.setdefault(name, {"name": name, "shots": 0, "goals": 0, "xg": 0.0})
        r["shots"] += 1
        r["goals"] += int(s.is_goal)
        r["xg"] += s.xg
    return sorted(({**r, "xg": round(r["xg"], 2)} for r in rows.values()), key=lambda r: -r["xg"])


FOOT = {"RightFoot": "Right foot", "LeftFoot": "Left foot", "Head": "Header", "OtherBodyPart": "Other"}


def finishing(shots: Sequence[Shot]) -> dict:
    """Shot-level finishing with exact significance (Poisson-binomial over each shot's xG)."""
    open_shots = [s for s in shots if s.situation != "Penalty"]
    pens = [s for s in shots if s.situation == "Penalty"]
    goals = sum(s.is_goal for s in shots)
    np_goals = sum(s.is_goal for s in open_shots)
    distances = [math.hypot(*_geometry(s)) for s in open_shots]
    luck_all = shot_luck(goals, [s.xg for s in shots])
    luck_np = shot_luck(np_goals, [s.xg for s in open_shots])
    return {
        "shots": len(shots),
        "goals": goals,
        "xg": round(sum(s.xg for s in shots), 2),
        "np_shots": len(open_shots),
        "np_goals": np_goals,
        "np_xg": round(sum(s.xg for s in open_shots), 2),
        "penalties": {"taken": len(pens), "scored": sum(s.is_goal for s in pens)},
        "on_target": sum(1 for s in shots if s.result in ("Goal", "SavedShot")),
        "xg_per_shot": round(safe_div(sum(s.xg for s in shots), len(shots)), 3),
        "np_xg_per_shot": round(safe_div(sum(s.xg for s in open_shots), len(open_shots)), 3),
        "avg_distance_m": round(sum(distances) / len(distances), 1) if distances else None,
        "big_chances": sum(1 for s in shots if s.xg >= 0.30),
        "luck_all": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in luck_all.items()},
        "luck_np": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in luck_np.items()},
        "by_situation": _group(shots, lambda s: s.situation or "Other"),
        "by_foot": _group(shots, lambda s: FOOT.get(s.shot_type, s.shot_type or "Other")),
        "by_zone": _group(shots, zone_of),
    }


def shot_rows(shots: Sequence[Shot]) -> list[dict]:
    return [
        {
            "id": s.id, "minute": s.minute, "x": round(s.x, 4), "y": round(s.y, 4), "xg": round(s.xg, 3),
            "result": s.result, "situation": s.situation, "type": s.shot_type, "last_action": s.last_action,
            "date": s.date, "season": s.season, "match_id": s.match_id,
            "opponent": s.away if s.venue == "h" else s.home, "venue": s.venue, "assisted_by": s.assisted_by,
        }
        for s in shots
    ]


# ---------------------------------------------------------------------- career


def _age_on(dob: str | None, day: date) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


def career_rows(career: Sequence[CareerSeason], dob: str | None = None) -> list[dict]:
    rows = []
    for c in career:
        rows.append(
            {
                "season": c.season, "team": c.team, "position": c.position, "age": _age_on(dob, date(c.season + 1, 1, 1)),
                "games": c.games, "minutes": c.minutes, "goals": c.goals, "npg": c.npg, "assists": c.assists,
                "xg": round(c.xg, 2), "npxg": round(c.npxg, 2), "xa": round(c.xa, 2), "shots": c.shots,
                "npxg90": round(per90(c.npxg, c.minutes), 3), "xa90": round(per90(c.xa, c.minutes), 3),
                "kp90": round(per90(c.key_passes, c.minutes), 3), "shots90": round(per90(c.shots, c.minutes), 3),
                "xgchain90": round(per90(c.xgchain, c.minutes), 3), "xgbuildup90": round(per90(c.xgbuildup, c.minutes), 3),
                "goals90": round(per90(c.goals, c.minutes), 3), "g_xg": round(c.goals - c.xg, 2),
                "contrib90": round(per90(c.npxg + c.xa, c.minutes), 3),
            }
        )
    return rows


def player_detail(row: dict, page: PlayerPage | None, seasons: Sequence[int], team_context: dict | None = None, pools: dict | None = None) -> dict:
    shots = [s for s in (page.shots if page else []) if not seasons or s.season in seasons]
    return {
        "player": {k: row[k] for k in (
            "id", "name", "team", "teams", "league", "seasons", "pos", "group", "group_source", "group_conf",
            "favorite", "dob", "dob_basis", "age", "minutes", "games", "sample", "in_pool", "tags", "output", "score_full", "pool_n", "pos2", "pos_min",
        )},
        "group_label": GROUP_LABELS.get(row["group"], row["group"]),
        "profile": profile(row),
        "blocks": metric_blocks(row, pools),
        "events": event_summary(row, pools),
        "totals": {k: row[k] for k in ("goals", "npg", "assists", "shots", "kp", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup", "g_xg", "a_xa", "g_xg_z")},
        "finishing": finishing(shots) if shots else None,
        "shots": shot_rows(shots),
        "career": career_rows(page.career, row.get("dob")) if page else [],
        "team_context": team_context,
        "positions_minutes": page.positions_minutes if page else {},
    }
