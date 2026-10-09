"""Every player of one match with every metric of the registry, for that match alone.

It is the player trend's arithmetic (:func:`app.analytics.player_trend._match_row` and the registry over one frame), run for the twenty-odd people who
played, so a number here is what the Scout table would show for a season made of just this match. Nothing is estimated: the Understat line and shots of the
match, and, where event data is stored for it, the event counters.

The percentile of a rate or a ratio says where this match's number would sit among the **season** numbers of the players in the same role who have played
enough (the Scout pool). Counts (goals, shots) have no percentile: a total from one match and a total from a season are not on one scale. A cameo is not
ranked at all; its numbers are shown dim.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from app.data.models import Fixture, MatchPage, RosterEntry
from app.events import schema as ES
from app.metrics.player import PLAYER_METRICS
from app.metrics.registry import SEASON_LONG, percentile_of

from .player_trend import _match_row
from .players import Merged, applies, raw_frame

MIN_RANKED = 30          # minutes in the match before a number is ranked against season numbers; fewer is a cameo
MIN_PEERS = 8            # role peers needed for a percentile to mean anything
PER_MATCH_METRICS = [m for m in PLAYER_METRICS if m.key not in SEASON_LONG]


def _group_of(entry: RosterEntry, season_rows: dict[int, dict]) -> str:
    """The role group the season dataset gives him, else the one his position in this match implies."""
    row = season_rows.get(entry.player_id)
    if row is not None:
        return row["group"]
    code = ES.POSITION_CODE.get((entry.position or "").upper())
    return ES.POSITION_GROUP.get(code, "MID") if code else "MID"


def _round(metric, v: float) -> float | None:
    return round(float(v), max(3, metric.decimals + 1)) if np.isfinite(v) else None


def season_pools(rows: Sequence[dict], keys: Sequence[str]) -> dict[tuple[str, str], np.ndarray]:
    """``{(role group, metric): sorted season values of the players ranked in that group}`` for the metrics that can be compared with one match."""
    by_key = {m.key: m for m in PER_MATCH_METRICS}
    out: dict[tuple[str, str], np.ndarray] = {}
    for key in keys:
        metric = by_key[key]
        if metric.shape not in ("rate", "ratio"):
            continue
        pool_flag = "ev_in_pool" if metric.needs == "events" else "in_pool"
        for group in ("ATT", "MID", "DEF", "GK"):
            values = [r[key] for r in rows if r["group"] == group and r.get(pool_flag) and r.get(key) is not None]
            if len(values) >= MIN_PEERS:
                out[(group, key)] = np.sort(np.array(values, dtype=float))
    return out


def build_match_players(
    fixture: Fixture, page: MatchPage, season_rows: Sequence[dict], *, league: str, season: int,
    event_counters: Callable[[int], dict | None] | None = None,
) -> dict:
    """The payload: ``keys`` and, for each player who played, ``v`` and ``p`` aligned with them (the shape of a Scout row).

    ``event_counters(understat id)`` gives his event counters in this match, ``None`` when none are stored for it or he could not be linked.
    """
    by_id = {r["id"]: r for r in season_rows}
    entries = [(side, e) for side in ("h", "a") for e in page.rosters.get(side, []) if e.minutes > 0]
    keys = [m.key for m in PER_MATCH_METRICS]
    pools = season_pools(season_rows, keys)

    rows: list[Merged] = []
    groups: list[str] = []
    for _side, e in entries:
        proto = Merged(e.player_id, e.player, [fixture.home if _side == "h" else fixture.away], league, [season], e.position)
        events = event_counters(e.player_id) if event_counters else None
        rows.append(_match_row(proto, fixture, page, e, events))
        groups.append(_group_of(e, by_id))
    if not rows:
        return {"keys": [], "rows": [], "coverage": {"players": 0, "events": 0}}

    frame = raw_frame(rows)
    values: dict[str, np.ndarray] = {}
    for metric in PER_MATCH_METRICS:
        value, _num, _den = metric.compute(frame)
        applicable = np.array([applies(metric, g) for g in groups])
        values[metric.key] = np.where(applicable, value, np.nan)
    # a metric nobody has a value for (no event data, say) is left out rather than sent as a column of blanks
    shown = [k for k in keys if np.isfinite(values[k]).any()]

    out = []
    for i, (side, e) in enumerate(entries):
        known = by_id.get(e.player_id)
        group = groups[i]
        ev = rows[i].ev or {}
        has_events = ev.get("min", 0) > 0
        ranked = e.minutes >= MIN_RANKED
        ev_ranked = has_events and ev["min"] >= MIN_RANKED
        v, p = [], []
        for k in shown:
            metric = next(m for m in PER_MATCH_METRICS if m.key == k)
            x = values[k][i]
            v.append(_round(metric, x))
            pool = pools.get((group, k))
            usable = ev_ranked if metric.needs == "events" else ranked
            p.append(None if pool is None or not usable or not np.isfinite(x) else round(float(percentile_of(pool, np.array([x]), metric.hib)[0])))
        started = bool(e.position) and e.position != "Sub"
        out.append({
            "id": e.player_id, "name": e.player, "side": side, "team": fixture.home if side == "h" else fixture.away, "group": group,
            "pos": e.position, "pos2": (known or {}).get("pos2") or ES.POSITION_CODE.get((e.position or "").upper()), "started": started,
            "minutes": e.minutes, "league": league, "seasons": [season], "in_pool": ranked, "ev_in_pool": ev_ranked, "has_events": has_events,
            "v": v, "p": p,
        })
    return {"keys": shown, "rows": out, "coverage": {"players": len(out), "events": sum(1 for r in out if r["has_events"])}}
