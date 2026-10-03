"""One match, explained by its shots."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.data.models import Fixture, MatchPage, RosterEntry, Shot
from app.stats import outcome_probs, poisson_binomial, safe_div

BIG_CHANCE = 0.30
ON_TARGET = {"Goal", "SavedShot"}
BUCKETS = ((0, 15), (16, 30), (31, 45), (46, 60), (61, 75), (76, 130))


def _shot(s: Shot) -> dict:
    return {
        "id": s.id, "minute": s.minute, "x": round(s.x, 4), "y": round(s.y, 4), "xg": round(s.xg, 3),
        "result": s.result, "situation": s.situation, "type": s.shot_type, "last_action": s.last_action,
        "player": s.player, "player_id": s.player_id, "assisted_by": s.assisted_by,
    }


def _side_summary(shots: Sequence[Shot]) -> dict:
    n = len(shots)
    xg = sum(s.xg for s in shots)
    return {
        "shots": n,
        "on_target": sum(1 for s in shots if s.result in ON_TARGET),
        "goals": sum(1 for s in shots if s.is_goal),
        "xg": round(xg, 2),
        "xg_per_shot": round(safe_div(xg, n), 3),
        "big_chances": sum(1 for s in shots if s.xg >= BIG_CHANCE),
        "np_xg": round(sum(s.xg for s in shots if s.situation != "Penalty"), 2),
    }


def _timeline(shots: Sequence[Shot]) -> list[dict]:
    total = 0.0
    points: list[dict[str, Any]] = [{"minute": 0, "xg": 0.0, "goal": None}]
    for s in sorted(shots, key=lambda s: (s.minute, s.id)):
        total += s.xg
        points.append(
            {
                "minute": s.minute,
                "xg": round(total, 3),
                "goal": {"player": s.player, "xg": round(s.xg, 2), "situation": s.situation} if s.is_goal else None,
            }
        )
    return points


def _buckets(shots: Sequence[Shot]) -> list[float]:
    return [round(sum(s.xg for s in shots if lo <= s.minute <= hi), 3) for lo, hi in BUCKETS]


def _situations(shots: Sequence[Shot]) -> list[dict]:
    rows: dict[str, dict] = {}
    for s in shots:
        row = rows.setdefault(s.situation or "Other", {"situation": s.situation or "Other", "shots": 0, "goals": 0, "xg": 0.0})
        row["shots"] += 1
        row["goals"] += int(s.is_goal)
        row["xg"] += s.xg
    return sorted(({**r, "xg": round(r["xg"], 2)} for r in rows.values()), key=lambda r: -r["xg"])


def _roster(entries: Sequence[RosterEntry]) -> list[dict]:
    return [
        {
            "id": e.player_id, "name": e.player, "position": e.position, "minutes": e.minutes,
            "goals": e.goals, "assists": e.assists, "shots": e.shots, "xg": round(e.xg, 2), "xa": round(e.xa, 2),
            "kp": e.key_passes, "xgchain": round(e.xgchain, 2), "xgbuildup": round(e.xgbuildup, 2),
            "yellow": e.yellow, "red": e.red,
        }
        for e in entries
        if e.minutes > 0
    ]


def deserved(home_shots: Sequence[Shot], away_shots: Sequence[Shot]) -> dict:
    """How often each result would occur if these exact chances were replayed."""
    pmf_h = poisson_binomial(s.xg for s in home_shots)
    pmf_a = poisson_binomial(s.xg for s in away_shots)
    p_home, p_draw, p_away = outcome_probs(pmf_h, pmf_a)
    return {
        "home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4),
        "home_expected": round(sum(s.xg for s in home_shots), 2),
        "away_expected": round(sum(s.xg for s in away_shots), 2),
        "home_pmf": [round(float(p), 4) for p in pmf_h[:7]],
        "away_pmf": [round(float(p), 4) for p in pmf_a[:7]],
    }


def match_report(fixture: Fixture, page: MatchPage) -> dict:
    home, away = page.shots["h"], page.shots["a"]
    dv = deserved(home, away)
    hg, ag = fixture.hg or 0, fixture.ag or 0
    actual = "home" if hg > ag else "away" if ag > hg else "draw"
    winner_prob = dv[actual]
    biggest = sorted([("h", s) for s in home] + [("a", s) for s in away], key=lambda t: -t[1].xg)[:6]
    return {
        "fixture": {
            "id": fixture.id, "date": fixture.date, "dt": fixture.dt, "round": fixture.round,
            "home": fixture.home, "away": fixture.away,
            "home_short": fixture.home_short, "away_short": fixture.away_short,
            "hg": hg, "ag": ag, "hxg": fixture.hxg, "axg": fixture.axg,
        },
        "own_goals": {"home": max(0, hg - sum(s.is_goal for s in home)), "away": max(0, ag - sum(s.is_goal for s in away))},
        "summary": {"home": _side_summary(home), "away": _side_summary(away)},
        "deserved": {**dv, "actual": actual, "actual_probability": round(winner_prob, 4)},
        "shots": {"home": [_shot(s) for s in home], "away": [_shot(s) for s in away]},
        "timeline": {"home": _timeline(home), "away": _timeline(away)},
        "buckets": {"labels": ["0-15", "16-30", "31-45", "46-60", "61-75", "76+"], "home": _buckets(home), "away": _buckets(away)},
        "situations": {"home": _situations(home), "away": _situations(away)},
        "key_chances": [{"side": side, **_shot(s)} for side, s in biggest],
        "players": {"home": _roster(page.rosters.get("h", [])), "away": _roster(page.rosters.get("a", []))},
    }
