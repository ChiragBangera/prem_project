"""Build the team dataset: one row per team per season with every team metric of the registry, ranked against the league.

The same ideas as :mod:`app.analytics.players`, one level up:

* the registry (:mod:`app.metrics.team`) declares each metric once; this module gathers the inputs and computes them all;
* percentiles compare a team with the other teams of its **own league and season** (a Premier League side against the Premier
  League), never across leagues, and read "higher is better" for every metric where better is defined;
* unknown is not zero: a metric that needs event data is blank for a team whose matches have none, and one built from match pages is
  blank unless nearly every match of the season is stored;
* event metrics are per match *that has event data*, so a half-fetched season is still read fairly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

from app.data.models import LeagueSeason
from app.events import counters as C
from app.metrics.registry import NAN, Frame, percentile_of
from app.metrics.team import TEAM_METRICS

from .players import SHOT_FIELDS
from .table import compute_table

MIN_POOL_MATCHES = 3   # a team needs this many matches to be ranked
MIN_AGE_MINUTES = 90


@dataclass
class TeamInput:
    """What is known about one league season. ``None`` means "not available", which is not the same as "zero"."""

    ls: LeagueSeason
    shots: dict[str, dict] | None = None   # Understat team name -> {"for": sums, "against": sums, "matches": n}; None unless nearly every match page is stored
    events: dict[str, dict] | None = None  # Understat team name -> {"c", "a", "matches", "formations", "managers", "age"}; None if no event data
    ages: dict[str, float] | None = None   # Understat team name -> minutes-weighted mean age of players with a confirmed age


@dataclass
class TeamDataset:
    rows: list[dict]
    keys: list[str]
    pools: dict[str, int]                  # league-season label -> teams ranked
    leagues: list[str]
    seasons: list[int]
    coverage: dict = field(default_factory=dict)


def _history_sums(ls: LeagueSeason, name: str) -> dict[str, float]:
    h = ls.teams[name].history
    n = len(h)
    sums = {
        "matches": n, "pts": sum(m.pts for m in h), "wins": sum(m.result == "w" for m in h), "draws": sum(m.result == "d" for m in h),
        "losses": sum(m.result == "l" for m in h), "gf": sum(m.gf for m in h), "ga": sum(m.ga for m in h), "xg": sum(m.xg for m in h),
        "xga": sum(m.xga for m in h), "npxg": sum(m.npxg for m in h), "npxga": sum(m.npxga for m in h), "xpts": sum(m.xpts for m in h),
        "deep": sum(m.deep for m in h), "deep_allowed": sum(m.deep_allowed for m in h), "ppda_att": sum(m.ppda_att for m in h),
        "ppda_def": sum(m.ppda_def for m in h), "oppda_att": sum(m.oppda_att for m in h), "oppda_def": sum(m.oppda_def for m in h),
        "cs": sum(m.ga == 0 for m in h),
    }
    return {k: float(v) for k, v in sums.items()}


def build_team_dataset(inputs: Sequence[TeamInput]) -> TeamDataset:
    entries: list[tuple[TeamInput, str]] = [(inp, name) for inp in inputs for name in inp.ls.teams if inp.ls.teams[name].history]
    n = len(entries)
    frame = Frame(n)
    hist = [_history_sums(inp.ls, name) for inp, name in entries]
    for key in hist[0] if hist else ():
        frame.set(key, [h[key] for h in hist])
    prefixed = lambda src, side, k: NAN if src is None else (src.get(side) or {}).get(k, 0)  # noqa: E731
    for k in SHOT_FIELDS:
        frame.set(f"s_{k}", [NAN if (inp.shots is None or name not in inp.shots) else inp.shots[name]["for"].get(k, 0) for inp, name in entries])
        frame.set(f"sa_{k}", [NAN if (inp.shots is None or name not in inp.shots) else inp.shots[name]["against"].get(k, 0) for inp, name in entries])
    ev = [None if inp.events is None else inp.events.get(name) for inp, name in entries]
    for k in C.COUNTERS:
        frame.set(f"w_{k}", [NAN if e is None else e["c"].get(k, 0) for e in ev])
        frame.set(f"wa_{k}", [NAN if e is None else e["a"].get(k, 0) for e in ev])
    frame.set("w_matches", [NAN if e is None else e["matches"] for e in ev])
    frame.set("squad_age", [NAN if (inp.ages is None or name not in inp.ages) else inp.ages[name] for inp, name in entries])
    frame.set("players_used", [sum(1 for p in inp.ls.players if name in p.teams and p.minutes > 0) for inp, name in entries])

    # the pool: teams are ranked within their own league and season
    league_season = np.array([f"{inp.ls.league}:{inp.ls.season}" for inp, _n in entries])
    played = frame["matches"]
    in_pool = played >= MIN_POOL_MATCHES
    values: dict[str, np.ndarray] = {}
    pct: dict[str, np.ndarray] = {}
    for metric in TEAM_METRICS:
        value, _num, _den = metric.compute(frame)
        values[metric.key] = value
        p = np.full(n, NAN)
        for label in dict.fromkeys(league_season):
            members = league_season == label
            pool = members & in_pool & np.isfinite(value)
            if pool.sum() >= 4:
                pooled = np.sort(value[pool])
                sel = members & np.isfinite(value)
                p[sel] = percentile_of(pooled, value[sel], metric.hib)
        pct[metric.key] = p

    tables = {f"{inp.ls.league}:{inp.ls.season}": {r["team"]: r for r in compute_table(inp.ls)} for inp in inputs}
    keys = [m.key for m in TEAM_METRICS]
    rows: list[dict] = []
    for i, (inp, name) in enumerate(entries):
        ls, team = inp.ls, inp.ls.teams[name]
        table = tables[f"{ls.league}:{ls.season}"].get(name, {})
        e = ev[i]
        formations = (e or {}).get("formations") or {}
        managers = (e or {}).get("managers") or {}
        rows.append({
            "team": name, "short": team.short, "league": ls.league, "season": ls.season, "key": f"{ls.league}:{ls.season}:{name}",
            "rank": table.get("rank"), "rank_xpts": table.get("rank_xpts"), "form": table.get("form", []), "trend_xgd": table.get("trend_xgd", []),
            "matches": int(hist[i]["matches"]), "ev_matches": int(e["matches"]) if e else 0, "shots_ok": inp.shots is not None and name in (inp.shots or {}),
            "formation": next(iter(formations), None), "manager": max(managers, key=managers.get) if managers else None,
            "in_pool": bool(in_pool[i]),
            "values": {k: round(float(a[i]), 4) for k, a in values.items() if np.isfinite(a[i])},
            "pct": {k: round(float(a[i]), 1) for k, a in pct.items() if np.isfinite(a[i])},
        })
    return TeamDataset(
        rows=rows, keys=keys, pools={str(label): int(((league_season == label) & in_pool).sum()) for label in dict.fromkeys(league_season)},
        leagues=sorted({inp.ls.league for inp in inputs}), seasons=sorted({inp.ls.season for inp in inputs}),
        coverage={"event_teams": sum(1 for e in ev if e), "teams": n, "shot_teams": sum(1 for r in rows if r["shots_ok"])},
    )


def squad_ages(ls: LeagueSeason, age_of: Callable[[object], int | None]) -> dict[str, float]:
    """Per team, the minutes-weighted mean age of the players with a confirmed age (a team with none is left out, not guessed)."""
    out: dict[str, float] = {}
    for name in ls.teams:
        total = weight = 0.0
        for p in ls.players:
            if name in p.teams and p.minutes > 0:
                age = age_of(p)
                if age is not None:
                    total += age * p.minutes
                    weight += p.minutes
        if weight >= MIN_AGE_MINUTES * 5:
            out[name] = total / weight
    return out
