"""A single team's season, unpacked: match log, form, splits, squad and schedule."""

from __future__ import annotations

from typing import Sequence

from app.data.models import LeagueSeason, Team, TeamMatch
from app.errors import NotFound
from app.stats import safe_div

from .table import (
    compute_table,
    rank_trajectories,
    rolling,
    select_matches,
    strengths,
    summarize,
    team_percentiles,
)

WINDOW = 5


def find_team(ls: LeagueSeason, name: str) -> Team:
    if name in ls.teams:
        return ls.teams[name]
    lowered = name.strip().lower()
    for team in ls.teams.values():
        if team.name.lower() == lowered or team.short.lower() == lowered:
            return team
    raise NotFound(f"'{name}' is not in the {ls.league} {ls.season} table.", hint="Check the spelling or pick another season.")


def _split(team: Team, matches: Sequence[TeamMatch]) -> dict:
    s = summarize(team, matches)
    return {k: s[k] for k in ("played", "pts", "pts_pg", "xpts_pg", "xg_pg", "xga_pg", "xgd_pg", "gf_pg", "ga_pg", "ppda", "w", "d", "l")}


def _match_row(m: TeamMatch, ls: LeagueSeason) -> dict:
    opponent = ls.teams.get(m.opponent or "")
    return {
        "n": m.matchweek,
        "date": m.date,
        "opponent": m.opponent,
        "opponent_short": opponent.short if opponent else (m.opponent or "")[:3].upper(),
        "venue": m.venue,
        "gf": m.gf, "ga": m.ga,
        "xg": round(m.xg, 2), "xga": round(m.xga, 2),
        "result": m.result,
        "pts": m.pts,
        "xpts": round(m.xpts, 2),
        "luck": round(m.pts - m.xpts, 2),
        "deep": int(m.deep),
        "ppda": round(m.ppda, 1) if m.ppda else None,
        "match_id": m.match_id,
    }


def squad_rows(ls: LeagueSeason, team: Team) -> list[dict]:
    members = [p for p in ls.players if team.name in p.teams]
    team_xg = sum(m.xg for m in team.history)
    team_npxg = sum(m.npxg for m in team.history)
    team_xa = sum(p.xa for p in members)
    rows = []
    for p in sorted(members, key=lambda p: -p.minutes):
        rows.append(
            {
                "id": p.id, "name": p.name, "pos": p.position,
                "games": p.games, "minutes": p.minutes,
                "goals": p.goals, "xg": round(p.xg, 2), "npxg": round(p.npxg, 2),
                "assists": p.assists, "xa": round(p.xa, 2), "shots": p.shots, "kp": p.key_passes,
                "xgchain": round(p.xgchain, 2), "xgbuildup": round(p.xgbuildup, 2),
                "share_npxg": round(safe_div(p.npxg, team_npxg), 3),
                "share_xa": round(safe_div(p.xa, team_xa), 3),
                "chain_share": round(safe_div(p.xgchain, team_xg), 3),
                "g_xg": round(p.goals - p.xg, 2),
            }
        )
    return rows


def concentration(rows: Sequence[dict]) -> dict:
    """How dependent is the team on a few players for chances?"""
    by_threat = sorted(rows, key=lambda r: -(r["npxg"] + r["xa"]))
    total = sum(r["npxg"] + r["xa"] for r in rows) or 1.0
    top1, top3 = by_threat[:1], by_threat[:3]
    return {
        "top_player": top1[0]["name"] if top1 else None,
        "top1_share": round(sum(r["npxg"] + r["xa"] for r in top1) / total, 3),
        "top3_share": round(sum(r["npxg"] + r["xa"] for r in top3) / total, 3),
        "top3": [r["name"] for r in top3],
    }


def era_splits(team: Team, eras: Sequence[dict], ls: LeagueSeason) -> list[dict]:
    out = []
    for era in eras:
        if era.get("team") != team.name:
            continue
        start, end = era["start"], era.get("end") or "9999-12-31"
        matches = select_matches(team, date_from=start, date_to=end)
        if not matches:
            continue
        split = _split(team, matches)
        out.append({"manager": era["manager"], "start": start, "end": era.get("end"), **split})
    return out


def team_profile(ls: LeagueSeason, name: str, *, eras: Sequence[dict] = ()) -> dict:
    team = find_team(ls, name)
    table = compute_table(ls)
    row = next(r for r in table if r["team"] == team.name)
    history = team.history

    matches = [_match_row(m, ls) for m in history]
    xg_roll = rolling([m.xg for m in history], WINDOW)
    xga_roll = rolling([m.xga for m in history], WINDOW)
    ppg_roll = rolling([m.pts for m in history], WINDOW)
    xpts_roll = rolling([m.xpts for m in history], WINDOW)

    cum_pts = cum_xpts = cum_g_xg = 0.0
    cumulative = []
    for m in history:
        cum_pts += m.pts
        cum_xpts += m.xpts
        cum_g_xg += m.gf - m.xg
        cumulative.append({"pts": cum_pts, "xpts": round(cum_xpts, 2), "g_xg": round(cum_g_xg, 2)})

    trajectories = rank_trajectories(ls)
    strength = strengths(ls)
    ordered = sorted(strength.values())
    median = ordered[len(ordered) // 2] if ordered else 0.0
    vs_strong = [m for m in history if m.opponent and strength.get(m.opponent, 0) >= median]
    vs_weak = [m for m in history if m.opponent and strength.get(m.opponent, 0) < median]
    half = len(history) // 2

    remaining = []
    for f in ls.upcoming:
        if team.name not in (f.home, f.away):
            continue
        home = f.home == team.name
        opponent = f.away if home else f.home
        forecast = None
        if f.forecast:
            w, d, l = f.forecast
            forecast = {"win": w if home else l, "draw": d, "loss": l if home else w}
        remaining.append(
            {
                "date": f.date, "dt": f.dt, "opponent": opponent,
                "opponent_short": (f.away_short if home else f.home_short),
                "venue": "h" if home else "a",
                "opp_strength": round(strength.get(opponent, 0.0), 3),
                "forecast": forecast,
                "match_id": f.id,
            }
        )
    played_opps = [strength.get(m.opponent, 0.0) for m in history if m.opponent]
    squad = squad_rows(ls, team)

    return {
        "team": {**row, "id": team.id},
        "percentiles": team_percentiles(table, team.name),
        "matches": matches,
        "rolling": {
            "window": WINDOW,
            "dates": [m.date for m in history],
            "xg": [None if v is None else round(v, 3) for v in xg_roll],
            "xga": [None if v is None else round(v, 3) for v in xga_roll],
            "ppg": [None if v is None else round(v, 3) for v in ppg_roll],
            "xppg": [None if v is None else round(v, 3) for v in xpts_roll],
        },
        "cumulative": cumulative,
        "rank_path": trajectories["rank"].get(team.name, []),
        "n_teams": len(ls.teams),
        "splits": {
            "home": _split(team, select_matches(team, venue="h")),
            "away": _split(team, select_matches(team, venue="a")),
            "first_half": _split(team, history[:half]) if half else None,
            "second_half": _split(team, history[half:]) if half else None,
            "last6": _split(team, history[-6:]) if history else None,
            "vs_stronger": _split(team, vs_strong) if vs_strong else None,
            "vs_weaker": _split(team, vs_weak) if vs_weak else None,
        },
        "schedule": {
            "played_avg_opp": round(sum(played_opps) / len(played_opps), 3) if played_opps else None,
            "remaining_avg_opp": round(sum(r["opp_strength"] for r in remaining) / len(remaining), 3) if remaining else None,
            "remaining": len(remaining),
            "league_avg_opp": 0.0,
        },
        "upcoming": remaining[:8],
        "squad": squad,
        "concentration": concentration(squad) if squad else None,
        "eras": era_splits(team, eras, ls) if eras else [],
    }
