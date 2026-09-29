"""League tables and league-wide context, computed from typed team histories.

No positional row indexes anywhere: every value is a named field, so a column
reorder upstream cannot silently corrupt an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from app.data.models import LeagueSeason, Team, TeamMatch
from app.stats import percentile_rank, safe_div

FORM_LENGTH = 5


def rolling(values: Sequence[float], window: int) -> list[float | None]:
    """Trailing mean; ``None`` until a full window is available."""
    out: list[float | None] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        out.append(running / window if i >= window - 1 else None)
    return out


def select_matches(
    team: Team,
    *,
    venue: str = "all",
    last_n: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[TeamMatch]:
    matches: Iterable[TeamMatch] = team.history
    if venue in ("h", "a"):
        matches = (m for m in matches if m.venue == venue)
    if date_from:
        matches = (m for m in matches if m.date >= date_from)
    if date_to:
        matches = (m for m in matches if m.date <= date_to)
    chosen = list(matches)
    return chosen[-last_n:] if last_n else chosen


def _ppda(matches: Sequence[TeamMatch], own: bool) -> float | None:
    att = sum(m.ppda_att if own else m.oppda_att for m in matches)
    dfn = sum(m.ppda_def if own else m.oppda_def for m in matches)
    return att / dfn if dfn > 0 else None


def summarize(team: Team, matches: Sequence[TeamMatch]) -> dict:
    n = len(matches)
    w = sum(1 for m in matches if m.result == "w")
    d = sum(1 for m in matches if m.result == "d")
    gf, ga = sum(m.gf for m in matches), sum(m.ga for m in matches)
    pts = sum(m.pts for m in matches)
    xg, xga = sum(m.xg for m in matches), sum(m.xga for m in matches)
    xpts = sum(m.xpts for m in matches)
    npxg, npxga = sum(m.npxg for m in matches), sum(m.npxga for m in matches)
    deep, deep_a = sum(m.deep for m in matches), sum(m.deep_allowed for m in matches)

    def pg(x: float) -> float:
        return x / n if n else 0.0

    return {
        "team": team.name,
        "short": team.short,
        "played": n,
        "w": w, "d": d, "l": n - w - d,
        "gf": gf, "ga": ga, "gd": gf - ga, "pts": pts,
        "xg": xg, "xga": xga, "xgd": xg - xga, "npxg": npxg, "npxga": npxga, "npxgd": npxg - npxga,
        "xpts": xpts, "xpts_gap": pts - xpts, "g_xg": gf - xg, "xga_ga": xga - ga,
        "deep": deep, "deep_allowed": deep_a,
        "ppda": _ppda(matches, True), "oppda": _ppda(matches, False),
        "pts_pg": pg(pts), "xpts_pg": pg(xpts), "gf_pg": pg(gf), "ga_pg": pg(ga),
        "xg_pg": pg(xg), "xga_pg": pg(xga), "xgd_pg": pg(xg - xga), "npxg_pg": pg(npxg), "npxga_pg": pg(npxga),
        "deep_pg": pg(deep), "deep_allowed_pg": pg(deep_a),
        "form": [m.result for m in matches[-FORM_LENGTH:]],
    }


def _sort_key(row: dict):
    return (-row["pts"], -row["gd"], -row["gf"], row["team"])


def compute_table(
    ls: LeagueSeason,
    *,
    venue: str = "all",
    last_n: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    rows = []
    for team in ls.teams.values():
        matches = select_matches(team, venue=venue, last_n=last_n, date_from=date_from, date_to=date_to)
        if matches or venue == "all" and not team.history:
            row = summarize(team, matches)
            row["trend_xgd"] = [round(v, 3) for v in rolling([m.xgd for m in team.history], 5) if v is not None]
            rows.append(row)
    rows.sort(key=_sort_key)
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    by_xpts = sorted(rows, key=lambda r: (-r["xpts"], -r["xgd"], r["team"]))
    by_xgd = sorted(rows, key=lambda r: (-r["xgd_pg"], r["team"]))
    for i, row in enumerate(by_xpts, start=1):
        row["rank_xpts"] = i
    for i, row in enumerate(by_xgd, start=1):
        row["rank_xgd"] = i
    for row in rows:
        row["rank_gap"] = row["rank"] - row["rank_xpts"]  # >0: table flatters them less than xPTS would
    return rows


def league_context(ls: LeagueSeason, today: str | None = None) -> dict:
    played = ls.played
    n = len(played)
    next_dates = sorted(f.dt for f in ls.upcoming)
    rounds = max((len(t.history) for t in ls.teams.values()), default=0)
    total_rounds = 2 * (len(ls.teams) - 1) if len(ls.teams) > 1 else 0
    return {
        "teams": len(ls.teams),
        "matches_played": n,
        "matches_total": len(ls.fixtures),
        "rounds_played": rounds,
        "rounds_total": total_rounds,
        "progress": round(safe_div(n, len(ls.fixtures)), 3),
        "as_of": max((f.date for f in played), default=None),
        "next_kickoff": next_dates[0] if next_dates else None,
        "goals_pg": safe_div(sum((f.hg or 0) + (f.ag or 0) for f in played), n),
        "xg_pg": safe_div(sum((f.hxg or 0) + (f.axg or 0) for f in played), n),
        "home_win": safe_div(sum(1 for f in played if f.hg > f.ag), n),
        "draw": safe_div(sum(1 for f in played if f.hg == f.ag), n),
        "away_win": safe_div(sum(1 for f in played if f.hg < f.ag), n),
        "home_xg_edge": safe_div(sum((f.hxg or 0) - (f.axg or 0) for f in played), n),
        "complete": bool(ls.fixtures) and not ls.upcoming,
    }


def rank_trajectories(ls: LeagueSeason) -> dict:
    """Table position and cumulative points after each of a team's matches.

    Aligned by *matchweek* (a team's nth match) so postponements do not tear the
    chart apart; ranks compare every team's tally after the same number of games.
    """
    teams = list(ls.teams.values())
    rounds = max((len(t.history) for t in teams), default=0)
    cumulative: dict[str, list[tuple[int, int, int, float]]] = {}
    for team in teams:
        pts = gf = ga = 0
        xpts = 0.0
        series = []
        for m in team.history:
            pts += m.pts
            gf += m.gf
            ga += m.ga
            xpts += m.xpts
            series.append((pts, gf - ga, gf, xpts))
        cumulative[team.name] = series

    ranks: dict[str, list[int | None]] = {t.name: [] for t in teams}
    for k in range(rounds):
        table = [
            (name, s[k]) for name, s in cumulative.items() if len(s) > k
        ]
        table.sort(key=lambda item: (-item[1][0], -item[1][1], -item[1][2], item[0]))
        position = {name: i for i, (name, _s) in enumerate(table, start=1)}
        for name in ranks:
            ranks[name].append(position.get(name))
    return {
        "rounds": rounds,
        "rank": ranks,
        "points": {n: [s[0] for s in series] for n, series in cumulative.items()},
        "xpts": {n: [round(s[3], 3) for s in series] for n, series in cumulative.items()},
    }


def strengths(ls: LeagueSeason) -> dict[str, float]:
    """Season-to-date npxG difference per game for every team (a simple, robust strength)."""
    out = {}
    for team in ls.teams.values():
        n = len(team.history)
        out[team.name] = sum(m.npxg - m.npxga for m in team.history) / n if n else 0.0
    return out


TEAM_PROFILE_METRICS = (
    # (key, label, lower_is_better)
    ("xg_pg", "Chance creation", False),
    ("npxg_pg", "Open-play threat", False),
    ("xga_pg", "Chance prevention", True),
    ("ppda", "Pressing intensity", True),
    ("deep_pg", "Territory (deep completions)", False),
    ("deep_allowed_pg", "Territory conceded", True),
    ("xgd_pg", "Overall quality (xGD)", False),
    ("pts_pg", "Results (points per game)", False),
)


def team_percentiles(rows: Sequence[dict], team: str) -> list[dict]:
    """Where a team ranks among the league on each style/quality dimension (100 = best)."""
    me = next((r for r in rows if r["team"] == team), None)
    if me is None:
        return []
    out = []
    for key, label, lower_is_better in TEAM_PROFILE_METRICS:
        values = [r[key] for r in rows if r.get(key) is not None]
        if me.get(key) is None or not values:
            continue
        pct = percentile_rank(me[key], values)
        out.append(
            {
                "key": key,
                "label": label,
                "value": me[key],
                "percentile": round(100 - pct if lower_is_better else pct, 1),
                "lower_is_better": lower_is_better,
                "league_average": sum(values) / len(values),
            }
        )
    return out
