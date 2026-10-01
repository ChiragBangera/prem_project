"""Everything about one player: profile blocks, shot-level finishing, career, context."""

from __future__ import annotations

import math
from datetime import date
from typing import Sequence

from app.data.models import CareerSeason, PlayerPage, Shot
from app.stats import per90, safe_div, shot_luck

from .metrics import EVENT_BY_KEY, EVENT_PROFILE, GROUP_LABELS, METRIC_BY_KEY, PROFILE_METRICS

PITCH_L, PITCH_W = 105.0, 68.0

BLOCKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Shooting", ("npxg90", "shots90", "xgps", "goals90")),
    ("Creation", ("xa90", "kp90", "contrib90")),
    ("Involvement", ("xgchain90", "xgbuildup90", "buildup_share")),
    ("Availability", ("minutes", "games", "mins_per_app", "minutes_share")),
    ("Discipline", ("yellow90",)),
)


def metric_blocks(row: dict) -> list[dict]:
    blocks = []
    for category, keys in BLOCKS:
        items = []
        for key in keys:
            metric = METRIC_BY_KEY[key]
            value = row.get(key)
            if value is None:
                continue
            items.append(
                {
                    "key": key, "label": metric.label, "short": metric.short, "unit": metric.unit,
                    "decimals": metric.decimals, "value": value,
                    "pct": row["pct"].get(key), "rank": row["rank"].get(key), "pool_n": row.get("pool_n"),
                    "higher_is_better": metric.higher_is_better, "what": metric.what, "read": metric.read,
                }
            )
        if items:
            blocks.append({"category": category, "items": items})
    return blocks


def event_card(row: dict) -> dict:
    """The "defending and passing" card: every event metric he has, role-relevant ones first, each with its percentile among role peers."""
    if not row.get("ev_minutes"):
        return {"available": False}
    focus = EVENT_PROFILE.get(row["group"], ())
    items = []
    for key in (*focus, *(k for k in EVENT_BY_KEY if k not in focus)):
        value = row.get(key)
        if value is None:
            continue
        m = EVENT_BY_KEY[key]
        items.append({
            "key": key, "label": m.label, "short": m.short, "category": m.category, "unit": m.unit, "decimals": m.decimals, "value": value,
            "pct": row["evpct"].get(key), "rank": row["evrank"].get(key), "higher_is_better": m.higher_is_better, "what": m.what, "read": m.read,
            "focus": key in focus,
        })
    return {
        "available": True, "minutes": row["ev_minutes"], "matches": row["ev_matches"], "in_pool": row["ev_in_pool"],
        "pool_n": row["ev_pool_n"], "pool_minutes": row["ev_pool_minutes"], "items": items,
    }


def profile(row: dict) -> list[dict]:
    """The role's key metrics in display order, each with its percentile."""
    out = []
    for key in PROFILE_METRICS.get(row["group"], ()):
        if key not in row["pct"]:
            continue
        metric = METRIC_BY_KEY[key]
        out.append(
            {
                "key": key, "label": metric.label, "short": metric.short, "category": metric.category,
                "value": row[key], "pct": row["pct"][key], "rank": row["rank"].get(key),
                "decimals": metric.decimals, "higher_is_better": metric.higher_is_better,
            }
        )
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


def player_detail(row: dict, page: PlayerPage | None, seasons: Sequence[int], team_context: dict | None = None) -> dict:
    shots = [s for s in (page.shots if page else []) if not seasons or s.season in seasons]
    return {
        "player": {k: row[k] for k in (
            "id", "name", "team", "teams", "league", "seasons", "pos", "group", "group_source", "group_conf",
            "favorite", "dob", "dob_basis", "age", "minutes", "games", "sample", "in_pool", "tags", "output", "pool_n",
        )},
        "group_label": GROUP_LABELS.get(row["group"], row["group"]),
        "profile": profile(row),
        "blocks": metric_blocks(row),
        "events": event_card(row),
        "totals": {k: row[k] for k in ("goals", "npg", "assists", "shots", "kp", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup", "g_xg", "a_xa", "g_xg_z")},
        "finishing": finishing(shots) if shots else None,
        "shots": shot_rows(shots),
        "career": career_rows(page.career, row.get("dob")) if page else [],
        "team_context": team_context,
        "positions_minutes": page.positions_minutes if page else {},
    }
