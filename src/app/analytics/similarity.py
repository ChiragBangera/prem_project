"""Find players who play like a target player.

Similarity is measured in *percentile space* over the metrics that define the
target's role. That makes the number self-explanatory: ``avg_gap`` is the
average distance, in percentile points, between the two profiles - a candidate
with a gap of 8 is, on average, within 8 percentile points on every metric.
"""

from __future__ import annotations

import math
from typing import Sequence

from .metrics import METRIC_BY_KEY, PROFILE_METRICS


def _label(key: str) -> str:
    return METRIC_BY_KEY[key].short if key in METRIC_BY_KEY else key


def similar_players(
    target: dict,
    rows: Sequence[dict],
    *,
    limit: int = 8,
    max_age: int | None = None,
    min_age: int | None = None,
    min_minutes: int | None = None,
    league: str | None = None,
    exclude_team: str | None = None,
    same_group: bool = True,
) -> list[dict]:
    group = target.get("group")
    keys = [k for k in PROFILE_METRICS.get(group, ()) if k != "yellow90" and k in target.get("pct", {})]
    if not keys:
        return []
    minutes_floor = min_minutes if min_minutes is not None else 0
    out = []
    for cand in rows:
        if cand["id"] == target["id"] or cand.get("group") == "GK":
            continue
        if same_group and cand.get("group") != group:
            continue
        if not cand.get("in_pool") or cand["minutes"] < minutes_floor:
            continue
        if league and cand["league"] != league:
            continue
        if exclude_team and exclude_team in cand["teams"]:
            continue
        if max_age is not None and (cand.get("age") is None or cand["age"] > max_age):
            continue
        if min_age is not None and (cand.get("age") is None or cand["age"] < min_age):
            continue
        shared = [k for k in keys if k in cand.get("pct", {})]
        if len(shared) < max(3, len(keys) - 1):
            continue
        gaps = {k: abs(target["pct"][k] - cand["pct"][k]) for k in shared}
        avg_gap = math.sqrt(sum(g * g for g in gaps.values()) / len(gaps))
        strong_together = sorted(
            (k for k in shared if min(target["pct"][k], cand["pct"][k]) >= 70),
            key=lambda k: -(target["pct"][k] + cand["pct"][k]),
        )
        out.append(
            {
                "id": cand["id"], "name": cand["name"], "team": cand["team"], "league": cand["league"],
                "age": cand.get("age"), "minutes": cand["minutes"], "group": cand["group"],
                "output": cand.get("output"), "tags": [t["label"] for t in cand.get("tags", [])],
                "similarity": round(max(0.0, 100.0 - avg_gap), 1),
                "avg_gap": round(avg_gap, 1),
                "shared_strengths": [_label(k) for k in strong_together[:3]],
                "biggest_difference": _label(max(gaps, key=gaps.get)) if gaps else None,
            }
        )
    out.sort(key=lambda r: (-r["similarity"], -r["minutes"]))
    return out[:limit]
