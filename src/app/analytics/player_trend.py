"""One player's season, match by match.

Every metric of the registry is computed three ways over the same counters, so that the last point of each line is the number on his profile:

* ``m``: for each match alone, what he did that day (blank in a match he did not play);
* ``c``: the season to date, as it stood after each match (his profile number is the last point);
* ``r``: over his last few appearances, his recent form.

Each match carries who he played (the opponent's strength this season, home or away, the result, his minutes), so a high number can be read against
the team it came against. The same metrics are also pooled by opponent strength and by venue.

Nothing here is estimated: a match is read from the stored Understat match page (his line in the roster and his shots) and, where it exists, from
the event data of that match. A match with no stored page is shown as such and left out of every line, never counted as zero.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from app.data.models import Fixture, LeagueSeason, MatchPage, RosterEntry
from app.metrics.player import PLAYER_METRICS
from app.metrics.registry import SEASON_LONG, Metric

from .matchsum import player_shots
from .players import SHOT_FIELDS, Merged, applies, raw_frame
from .table import compute_table

FORM_WINDOW = 5                 # appearances behind the "form" line
TIER_SHARE = 0.3                # the top and the bottom 30% of the table are the "top" and "bottom" opponents


def tier_bounds(n_teams: int) -> dict[str, tuple[int, int]]:
    """Table positions that make a top, a middle and a bottom opponent, for a league of this many teams."""
    edge = max(1, round(n_teams * TIER_SHARE))
    return {"top": (1, edge), "mid": (edge + 1, n_teams - edge), "bottom": (n_teams - edge + 1, n_teams)}


def opponent_context(ls: LeagueSeason) -> dict[str, dict]:
    """Per club: where it stands this season (by expected points and by points), and how good its attack and its defence are, as ranks."""
    table = compute_table(ls)
    n = len(table)
    bounds = tier_bounds(n)
    by_attack = {r["team"]: i for i, r in enumerate(sorted(table, key=lambda r: (-r["xg_pg"], r["team"])), start=1)}
    by_defence = {r["team"]: i for i, r in enumerate(sorted(table, key=lambda r: (r["xga_pg"], r["team"])), start=1)}
    out = {}
    for r in table:
        rank = r["rank_xpts"]
        tier = next(name for name, (lo, hi) in bounds.items() if lo <= rank <= hi)
        out[r["team"]] = {"rank": r["rank"], "rank_xpts": rank, "tier": tier, "n_teams": n, "xg_pg": round(r["xg_pg"], 2), "xga_pg": round(r["xga_pg"], 2),
                          "attack_rank": by_attack[r["team"]], "defence_rank": by_defence[r["team"]]}
    return out


# ---------------------------------------------------------------------- his matches


def _appearance(page: MatchPage | None, player_id: int) -> tuple[str, RosterEntry] | None:
    if page is None:
        return None
    for side in ("h", "a"):
        for r in page.rosters.get(side, []):
            if r.player_id == player_id and r.minutes > 0:
                return side, r
    return None


def his_matches(player_id: int, ls: LeagueSeason, pages: dict[int, MatchPage]) -> list[tuple[Fixture, str, MatchPage | None, RosterEntry | None]]:
    """Every played match of the club (or clubs) he was at, oldest first: ``(fixture, his side, its stored page or None, his roster line or None)``.

    His clubs are read from where he actually appeared. A club he moved to counts from his first appearance for it and the one he left up to his last,
    since from the data alone nobody can say when a man who never played was at which club.
    """
    played = sorted((f for f in ls.fixtures if f.played), key=lambda f: (f.dt, f.id))
    appearances = [(f, *found) for f in played if (found := _appearance(pages.get(f.id), player_id))]
    clubs: list[str] = []
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    for f, side, _entry in appearances:
        club = f.home if side == "h" else f.away
        if club not in first:
            clubs.append(club)
            first[club] = f.dt
        last[club] = f.dt
    out = []
    for f in played:
        for i, club in enumerate(clubs):
            at = "h" if f.home == club else "a" if f.away == club else None
            if at is None:
                continue
            lower = first[club] if i > 0 else ""
            upper = last[club] if i < len(clubs) - 1 else "9999"
            if lower <= f.dt <= upper:
                page = pages.get(f.id)
                found = _appearance(page, player_id)
                out.append((f, at, page, found[1] if found else None))
                break
    return out


# ---------------------------------------------------------------------- counters of one match, and sums of them


def _match_row(base: Merged, fixture: Fixture, page: MatchPage | None, entry: RosterEntry | None, events: dict | None) -> Merged:
    """The counters of one match in the shape the season dataset adds up, so the same frame and the same formulas apply."""
    row = Merged(base.id, base.name, list(base.teams), base.league, [base.seasons[0]], base.position, available=90, shots=None, starts=0)
    if page is None:
        return row                                    # nothing stored for this match: unknown, which is not zero
    row.shots = dict.fromkeys(SHOT_FIELDS, 0.0)
    if entry is not None:
        found = player_shots([page]).get(base.id)
        row.shots = {k: float(found.get(k, 0)) for k in SHOT_FIELDS} if found else row.shots
        pen_goals = row.shots["pen_goals"]
        pen_xg = row.shots["pen_xg"]
        row.c = {"games": 1, "minutes": entry.minutes, "goals": entry.goals, "npg": entry.goals - pen_goals, "assists": entry.assists, "shots": entry.shots,
                 "key_passes": entry.key_passes, "yellow": entry.yellow, "red": entry.red, "xg": entry.xg, "npxg": entry.xg - pen_xg, "xa": entry.xa,
                 "xgchain": entry.xgchain, "xgbuildup": entry.xgbuildup}
        started = bool(entry.position) and entry.position != "Sub"
        row.starts = int(started)
        row.pos_min = {entry.position: float(entry.minutes)} if started else {}
    row.ev = events
    row.ev_matches = int(bool(events and events.get("min", 0) > 0))
    return row


def _sum(rows: Sequence[Merged], proto: Merged) -> Merged:
    """Add matches up. A source that none of them has stays unknown; one that only some have is the sum of those that do."""
    out = Merged(proto.id, proto.name, list(proto.teams), proto.league, list(proto.seasons), proto.position, shots=None, starts=0)
    counters: dict[str, float] = defaultdict(float)
    for r in rows:
        for k, v in r.c.items():
            counters[k] += v
        out.available += r.available
        out.starts = (out.starts or 0) + (r.starts or 0)
        for code, minutes in r.pos_min.items():
            out.pos_min[code] = out.pos_min.get(code, 0) + minutes
        if r.shots is not None:
            out.shots = out.shots or dict.fromkeys(SHOT_FIELDS, 0.0)
            for k in SHOT_FIELDS:
                out.shots[k] += r.shots[k]
        if r.ev is not None:
            out.ev = out.ev or {}
            for k, v in r.ev.items():
                out.ev[k] = out.ev.get(k, 0) + v
            out.ev_matches += r.ev_matches
    out.c = dict(counters)
    return out


# ---------------------------------------------------------------------- metrics over frames


def _values(metrics: Sequence[Metric], rows: Sequence[Merged], group: str) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
    """``{metric: (value for each row, the denominator behind it or None)}``, blank where a metric means nothing for his role."""
    frame = raw_frame(rows)
    out = {}
    for metric in metrics:
        value, _num, den = metric.compute(frame)
        out[metric.key] = (value if applies(metric, group) else np.full(len(rows), np.nan), den)
    return out


def _round(metric: Metric, v: float) -> float | None:
    return round(float(v), max(3, metric.decimals + 1)) if np.isfinite(v) else None


def role_reference(rows: Sequence[dict], group: str, keys: Sequence[str], *, minimum: int = 8) -> dict[str, dict]:
    """What is typical for his role, per metric: the middle half (25th to 75th percentile), the median and the 90th percentile of the season values of
    the peers who have played enough (the same pool his percentiles are ranked in). Left out where fewer than ``minimum`` peers have a value."""
    by_key = {m.key: m for m in PLAYER_METRICS}
    pool = [r for r in rows if r["group"] == group and r["in_pool"]]
    out: dict[str, dict] = {}
    for key in keys:
        values = [r[key] for r in pool if r.get(key) is not None]
        if len(values) < minimum:
            continue
        p25, p50, p75, p90 = (_round(by_key[key], v) for v in np.percentile(values, (25, 50, 75, 90)))
        out[key] = {"n": len(values), "p25": p25, "p50": p50, "p75": p75, "p90": p90}
    return out


def build_trend(
    player_id: int, ls: LeagueSeason, pages: dict[int, MatchPage], *, group: str, name: str = "", team: str = "",
    event_counters: Callable[[int], dict | None] | None = None, window: int = FORM_WINDOW,
) -> dict:
    """The trend payload for one player and league season. ``event_counters(fixture id)`` gives his event counters in that match, ``None`` when
    no event data is stored for the match (and ``{}`` when it is but he is not in it)."""
    mine = his_matches(player_id, ls, pages)
    if not any(entry is not None for *_x, entry in mine):
        return {"available": False, "matches": [], "reason": "No stored match page has him in it yet, so there is nothing to draw: the Data page shows which match pages are missing."}
    context = opponent_context(ls)
    proto = Merged(player_id, name, [team] if team else [], ls.league, [ls.season], "")
    metrics = [m for m in PLAYER_METRICS if m.key not in SEASON_LONG and applies(m, group)]

    rows: list[Merged] = []
    played: list[bool] = []
    meta: list[dict[str, Any]] = []
    for i, (f, side, page, entry) in enumerate(mine):
        events = event_counters(f.id) if (event_counters and entry is not None) else None
        rows.append(_match_row(proto, f, page, entry, events))
        played.append(entry is not None)
        opp = f.away if side == "h" else f.home
        gf, ga = (f.hg, f.ag) if side == "h" else (f.ag, f.hg)
        ctx = context.get(opp, {})
        meta.append({
            "i": i, "round": f.round, "date": f.date, "match_id": f.id, "opp": opp, "opp_short": f.away_short if side == "h" else f.home_short, "home": side == "h",
            "gf": gf, "ga": ga, "result": None if gf is None or ga is None else "w" if gf > ga else "l" if gf < ga else "d",
            "played": entry is not None, "minutes": entry.minutes if entry else 0, "started": (bool(entry.position) and entry.position != "Sub") if entry else None,
            "page": page is not None, "events": bool(entry is not None and events is not None and events.get("min", 0) > 0), "opp_ctx": ctx or None,
        })

    # the three frames: each match alone, the season so far, the last few appearances
    each = _values(metrics, rows, group)
    cum_rows = [_sum(rows[: k + 1], proto) for k in range(len(rows))]
    season = _values(metrics, cum_rows, group)
    form_rows = []
    for k in range(len(rows)):
        recent = [rows[j] for j in range(k + 1) if played[j]][-window:]
        form_rows.append(_sum(recent, proto))
    form = _values(metrics, form_rows, group)
    seen = np.cumsum(played) > 0        # from his first appearance on

    series: dict[str, dict] = {}
    for metric in metrics:
        m_val, m_den = each[metric.key]
        c_val, _ = season[metric.key]
        r_val, _ = form[metric.key]
        m = [(_round(metric, v) if played[i] and mine[i][2] is not None else None) for i, v in enumerate(m_val)]
        c = [(_round(metric, v) if seen[i] else None) for i, v in enumerate(c_val)]
        r = [(_round(metric, v) if seen[i] else None) for i, v in enumerate(r_val)]
        if not any(v is not None for v in (*m, *c, *r)):
            continue                                   # nothing stored behind this metric for him: leave it out, rather than send blanks
        n = None if m_den is None else [round(float(d), 1) if (played[i] and np.isfinite(d)) else None for i, d in enumerate(m_den)]
        series[metric.key] = {"m": m, "c": c, "r": r, **({"n": n} if n is not None else {})}

    # pooled by opponent strength and by venue: the same formulas over the matches in each group
    groups = {
        "tier": {t: [i for i, x in enumerate(meta) if x["played"] and x["page"] and (x["opp_ctx"] or {}).get("tier") == t] for t in ("top", "mid", "bottom")},
        "venue": {"home": [i for i, x in enumerate(meta) if x["played"] and x["page"] and x["home"]], "away": [i for i, x in enumerate(meta) if x["played"] and x["page"] and not x["home"]]},
    }
    splits: dict[str, dict] = {}
    for kind, parts in groups.items():
        names = list(parts)
        pooled = [_sum([rows[i] for i in parts[nm]], proto) for nm in names]
        values = _values(metrics, pooled, group)
        splits[kind] = {nm: {"matches": len(parts[nm]), "minutes": int(sum(meta[i]["minutes"] for i in parts[nm])),
                             "v": {m.key: _round(m, values[m.key][0][j]) for m in metrics if m.key in series}} for j, nm in enumerate(names)}

    n_teams = len(context)
    return {
        "available": True, "matches": meta, "keys": [m.key for m in metrics if m.key in series], "series": series, "splits": splits, "window": window,
        "tiers": {k: list(v) for k, v in tier_bounds(n_teams).items()} if n_teams else {},
        "coverage": {"matches": len(mine), "played": sum(played), "pages": sum(1 for x in meta if x["page"]), "events": sum(1 for x in meta if x["events"])},
    }
