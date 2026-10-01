"""Build the scouting dataset: one row per player with everything needed to judge him.

Design decisions worth knowing:

* **Peers, not the whole league.** Percentiles compare a player with others in
  his role group (attackers vs attackers) who have played enough minutes.
* **Shrunk rates for ranking.** A per-90 rate from 90 minutes is mostly noise.
  Ranking uses an empirical-Bayes shrunk rate (pulled toward the group average
  in proportion to how little he has played); the displayed rate stays raw.
* **Honest about luck.** Goals minus xG carries a z-score so a +3.1 over
  400 minutes is not mistaken for finishing skill.
* **Honest about roles.** ``group_source`` says whether a role was listed,
  inferred from his profile, or taken from Understat's favourite position.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable, Sequence

from app.data.models import LeagueSeason, PlayerSeason
from app.leagues import fold
from app.stats import per90, safe_div

from .metrics import GROUP_ORDER, PROFILE_METRICS, SHRINK_MINUTES, SHRUNK
from .roles import FAMILY_GROUP, RoleModel, families_of, group_from_favorite

MIN_POOL_MINUTES, MAX_POOL_MINUTES = 180, 900
ROLE_FEATURES = ("npxg90", "shots90", "xa90", "kp90", "xgchain90", "xgbuildup90")
RATE_SOURCES = {  # metric -> counting-stat attribute it is a per-90 of
    "npxg90": "npxg", "shots90": "shots", "xa90": "xa", "kp90": "key_passes", "xgchain90": "xgchain",
    "xgbuildup90": "xgbuildup", "goals90": "goals", "yellow90": "yellow",
}


@dataclass
class Merged:
    """A player's totals across the requested seasons/leagues."""

    id: int
    name: str
    teams: list[str]
    league: str
    seasons: list[int]
    position: str
    games: int = 0
    minutes: int = 0
    goals: int = 0
    npg: int = 0
    assists: int = 0
    shots: int = 0
    key_passes: int = 0
    yellow: int = 0
    red: int = 0
    xg: float = 0.0
    npxg: float = 0.0
    xa: float = 0.0
    xgchain: float = 0.0
    xgbuildup: float = 0.0
    available: int = 0  # minutes his club(s) played while he could have been in the squad


@dataclass
class ScoutDataset:
    rows: list[dict]
    pool_minutes: int
    group_sizes: dict[str, int]
    leagues: list[str]
    seasons: list[int]
    role_model_ok: bool
    ages_known: int = 0
    inferred: int = 0
    notes: list[str] = field(default_factory=list)
    age_reference: str | None = None  # the date every age is worked out on


# ---------------------------------------------------------------------- merge


def _team_matches(ls: LeagueSeason) -> dict[str, int]:
    return {name: len(team.history) for name, team in ls.teams.items()}


def merge_players(seasons: Sequence[LeagueSeason]) -> list[Merged]:
    """Combine season rows per player id. Identity fields come from the newest season."""
    ordered = sorted(seasons, key=lambda ls: ls.season)
    merged: dict[int, Merged] = {}
    for ls in ordered:
        matches = _team_matches(ls)
        for p in ls.players:
            m = merged.get(p.id)
            if m is None:
                m = merged[p.id] = Merged(p.id, p.name, list(p.teams), ls.league, [ls.season], p.position)
            else:
                m.teams, m.league, m.position = list(p.teams), ls.league, p.position
                if ls.season not in m.seasons:
                    m.seasons.append(ls.season)
            m.games += p.games
            m.minutes += p.minutes
            m.goals += p.goals
            m.npg += p.npg
            m.assists += p.assists
            m.shots += p.shots
            m.key_passes += p.key_passes
            m.yellow += p.yellow
            m.red += p.red
            m.xg += p.xg
            m.npxg += p.npxg
            m.xa += p.xa
            m.xgchain += p.xgchain
            m.xgbuildup += p.xgbuildup
            m.available += 90 * max((matches.get(t, 0) for t in p.teams), default=0)
    return list(merged.values())


# ---------------------------------------------------------------------- rates


def _rates(m: Merged) -> dict[str, float]:
    minutes = m.minutes
    out = {metric: per90(getattr(m, attr), minutes) for metric, attr in RATE_SOURCES.items()}
    out["contrib90"] = out["npxg90"] + out["xa90"]
    out["xgps"] = safe_div(m.xg, m.shots)
    out["buildup_share"] = safe_div(m.xgbuildup, m.xgchain)
    return out


def _luck(m: Merged) -> dict[str, float]:
    """Goals minus xG with a conservative z (homogeneous-shot variance is an upper bound)."""
    diff = m.goals - m.xg
    z = 0.0
    if m.shots > 0 and 0 < m.xg < m.shots:
        p = m.xg / m.shots
        sd = math.sqrt(m.shots * p * (1 - p))
        z = diff / sd if sd > 0 else 0.0
    return {"g_xg": diff, "npg_npxg": m.npg - m.npxg, "a_xa": m.assists - m.xa, "g_xg_z": z}


def sample_label(minutes: int) -> str:
    return "low" if minutes < 450 else "solid" if minutes >= 1800 else "ok"


# ---------------------------------------------------------------------- build


def pool_minutes_for(seasons: Sequence[LeagueSeason]) -> int:
    """Minutes needed to enter the peer pool: ~25% of what a full-time player could have played."""
    if not seasons:
        return MIN_POOL_MINUTES
    per_season = []
    for ls in seasons:
        rounds = max((len(t.history) for t in ls.teams.values()), default=0)
        per_season.append(rounds * 90)
    threshold = 0.25 * sum(per_season)
    return int(min(MAX_POOL_MINUTES, max(MIN_POOL_MINUTES, int(threshold // 30) * 30)))


def build_dataset(
    seasons: Sequence[LeagueSeason],
    *,
    dob_of: Callable[[str, str | None], str | None] | None = None,
    dob_info: Callable[[str, list, date], tuple[str | None, str | None]] | None = None,  # (dob, basis); preferred over dob_of
    favorite_of: Callable[[int], str | None] | None = None,
    today: date | None = None,
    pool_minutes: int | None = None,
) -> ScoutDataset:
    today = today or date.today()
    merged = merge_players(seasons)
    pool_min = pool_minutes if pool_minutes is not None else pool_minutes_for(seasons)
    newest = max((ls.season for ls in seasons), default=today.year)
    reference = min(today, date(newest + 1, 6, 30))

    rates = {m.id: _rates(m) for m in merged}

    # ---- roles
    samples = []
    for m in merged:
        families, _sub = families_of(m.position)
        if m.minutes >= 450 and len(families) == 1:
            samples.append((families[0], [rates[m.id][k] for k in ROLE_FEATURES]))
    model = RoleModel.fit(samples)
    group_of: dict[int, tuple[str, str, float]] = {}
    for m in merged:
        families, _sub = families_of(m.position)
        favorite = favorite_of(m.id) if favorite_of else None
        from_favorite = group_from_favorite(favorite)
        if from_favorite:
            group_of[m.id] = (from_favorite, "favorite", 1.0)
        elif len(families) == 1:
            group_of[m.id] = (FAMILY_GROUP[families[0]], "listed", 1.0)
        elif families and model is not None:
            family, confidence = model.classify(families, [rates[m.id][k] for k in ROLE_FEATURES])
            group_of[m.id] = (FAMILY_GROUP[family], "inferred", round(confidence, 2))
        else:
            fallback = "F" if "F" in families else "M" if "M" in families else (families[0] if families else "M")
            group_of[m.id] = (FAMILY_GROUP[fallback], "inferred", 0.0)

    # ---- group averages for shrinkage (minutes-weighted, over the pool)
    group_rate: dict[str, dict[str, float]] = {}
    for group in GROUP_ORDER:
        members = [m for m in merged if group_of[m.id][0] == group and m.minutes >= pool_min]
        total_minutes = sum(m.minutes for m in members)
        group_rate[group] = {
            metric: per90(sum(getattr(m, attr) for m in members), total_minutes)
            for metric, attr in RATE_SOURCES.items()
        }
        group_rate[group]["contrib90"] = group_rate[group]["npxg90"] + group_rate[group]["xa90"]

    def ranked_value(m: Merged, metric: str) -> float:
        group = group_of[m.id][0]
        value = rates[m.id][metric]
        if metric in SHRUNK and metric in group_rate[group]:
            prior = group_rate[group][metric]
            return (value * m.minutes + prior * SHRINK_MINUTES) / (m.minutes + SHRINK_MINUTES)
        return value

    # ---- pools: sorted ranked values per (group, metric)
    metrics_needed = {k for keys in PROFILE_METRICS.values() for k in keys} | {"contrib90", "goals90", "xgps"}
    pools: dict[tuple[str, str], list[float]] = {}
    for group in GROUP_ORDER:
        members = [m for m in merged if group_of[m.id][0] == group and m.minutes >= pool_min]
        for metric in metrics_needed:
            pools[(group, metric)] = sorted(ranked_value(m, metric) for m in members)

    def rank_of(group: str, metric: str, value: float, higher_is_better: bool = True) -> int | None:
        sample = pools.get((group, metric))
        if not sample:
            return None
        better = (len(sample) - bisect_right(sample, value)) if higher_is_better else bisect_left(sample, value)
        return better + 1

    def percentile(group: str, metric: str, value: float, higher_is_better: bool = True) -> float | None:
        sample = pools.get((group, metric))
        if not sample:
            return None
        below = bisect_left(sample, value)
        equal = bisect_right(sample, value) - below
        pct = 100.0 * (below + 0.5 * equal) / len(sample)
        return pct if higher_is_better else 100.0 - pct

    rows: list[dict] = []
    group_sizes = {g: len(pools.get((g, "npxg90"), [])) for g in GROUP_ORDER}
    ages_known = 0
    for m in merged:
        group, source, confidence = group_of[m.id]
        r = rates[m.id]
        luck = _luck(m)
        favorite = favorite_of(m.id) if favorite_of else None
        basis = None
        if dob_info:
            dob, basis = dob_info(m.name, m.teams, reference)
        else:
            dob = dob_of(m.name, m.teams[0] if m.teams else None) if dob_of else None
        age = _age_on(dob, reference)
        ages_known += age is not None

        pct: dict[str, float] = {}
        rank: dict[str, int] = {}
        if group != "GK":
            for metric in PROFILE_METRICS[group] + ("contrib90", "goals90", "xgps"):
                hib = metric != "yellow90"
                value = ranked_value(m, metric)
                p = percentile(group, metric, value, higher_is_better=hib)
                if p is not None:
                    pct[metric] = round(p, 1)
                    rank[metric] = rank_of(group, metric, value, higher_is_better=hib)
        profile = [pct[k] for k in (PROFILE_METRICS.get(group, ())) if k in pct and k != "yellow90"]
        output_index = round(sum(profile) / len(profile), 1) if profile else None

        row = {
            "id": m.id,
            "name": m.name,
            "team": " / ".join(m.teams),
            "teams": m.teams,
            "league": m.league,
            "seasons": sorted(m.seasons),
            "pos": m.position,
            "group": group,
            "group_source": source,
            "group_conf": confidence,
            "favorite": favorite,
            "dob": dob,
            "dob_basis": basis,
            "age": age,
            "minutes": m.minutes,
            "games": m.games,
            "mins_per_app": round(safe_div(m.minutes, m.games)),
            "minutes_share": round(min(1.0, safe_div(m.minutes, m.available)), 3),
            "sample": sample_label(m.minutes),
            "in_pool": m.minutes >= pool_min,
            "goals": m.goals, "npg": m.npg, "assists": m.assists, "shots": m.shots, "kp": m.key_passes,
            "yellow": m.yellow, "red": m.red,
            "xg": round(m.xg, 2), "npxg": round(m.npxg, 2), "xa": round(m.xa, 2),
            "xgchain": round(m.xgchain, 2), "xgbuildup": round(m.xgbuildup, 2),
            **{k: round(v, 3) for k, v in r.items()},
            "g_xg": round(luck["g_xg"], 2), "npg_npxg": round(luck["npg_npxg"], 2),
            "a_xa": round(luck["a_xa"], 2), "g_xg_z": round(luck["g_xg_z"], 2),
            "pct": pct,
            "rank": rank,
            "pool_n": group_sizes.get(group, 0),
            "output": output_index,
        }
        row["tags"] = archetype_tags(row) if group != "GK" and m.minutes >= 270 else []
        rows.append(row)

    return ScoutDataset(
        rows=rows,
        pool_minutes=pool_min,
        group_sizes=group_sizes,
        leagues=sorted({ls.league for ls in seasons}),
        seasons=sorted({ls.season for ls in seasons}),
        role_model_ok=model is not None,
        ages_known=ages_known,
        inferred=sum(1 for r in rows if r["group_source"] == "inferred"),
        age_reference=reference.isoformat(),
    )


def _age_on(dob: str | None, reference: date) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))


# ---------------------------------------------------------------------- archetypes

def _top(pct: dict, key: str, level: float) -> bool:
    return pct.get(key, 0) >= level


def _bottom(pct: dict, key: str, level: float) -> bool:
    return key in pct and pct[key] <= level


def archetype_tags(row: dict) -> list[dict]:
    """Rule-based role labels with the evidence that earned them (max three)."""
    pct, group = row["pct"], row["group"]
    tags: list[tuple[float, dict]] = []

    def add(key: str, label: str, evidence: list[tuple[str, str]], strength: float) -> None:
        why = ", ".join(f"top {max(1, round(100 - pct[m]))}% for {name}" for m, name in evidence if m in pct)
        tags.append((strength, {"key": key, "label": label, "why": why + f" among {group_word(group)}"}))

    if group == "ATT":
        if _top(pct, "npxg90", 85) and pct.get("xa90", 100) < 55:
            add("poacher", "Poacher", [("npxg90", "npxG/90")], pct["npxg90"])
        if _top(pct, "npxg90", 70) and _top(pct, "xa90", 70):
            add("complete", "Complete forward", [("npxg90", "npxG/90"), ("xa90", "xA/90")], (pct["npxg90"] + pct["xa90"]) / 2)
        if _top(pct, "xa90", 85) and _top(pct, "kp90", 75):
            add("creator", "Chance creator", [("xa90", "xA/90"), ("kp90", "key passes")], pct["xa90"])
        if _top(pct, "shots90", 85) and _bottom(pct, "xgps", 40):
            add("volume", "Volume shooter", [("shots90", "shots/90")], pct["shots90"] - 10)
        if _top(pct, "xgps", 85) and pct.get("shots90", 100) < 60:
            add("selective", "Selective finisher", [("xgps", "xG/shot")], pct["xgps"] - 10)
        if _top(pct, "xgbuildup90", 80):
            add("dropper", "Link-up player", [("xgbuildup90", "buildup")], pct["xgbuildup90"] - 5)
    elif group == "MID":
        if _top(pct, "xa90", 82) and _top(pct, "kp90", 70):
            add("playmaker", "Playmaker", [("xa90", "xA/90"), ("kp90", "key passes")], pct["xa90"])
        if _top(pct, "xgbuildup90", 82):
            add("progressor", "Deep progressor", [("xgbuildup90", "buildup")], pct["xgbuildup90"])
        if _top(pct, "npxg90", 82):
            add("boxcrasher", "Goal-scoring midfielder", [("npxg90", "npxG/90")], pct["npxg90"])
        if _top(pct, "xgchain90", 85):
            add("hub", "Attacking hub", [("xgchain90", "xGChain")], pct["xgchain90"] - 5)
        if _top(pct, "contrib90", 85) and pct.get("xgbuildup90", 0) < 50:
            add("advanced", "Advanced creator", [("contrib90", "npxG+xA")], pct["contrib90"] - 5)
    elif group == "DEF":
        if _top(pct, "xgbuildup90", 82):
            add("builder", "Ball-playing defender", [("xgbuildup90", "buildup")], pct["xgbuildup90"])
        if _top(pct, "xa90", 82) or _top(pct, "kp90", 82):
            add("wide", "Attacking full-back", [("xa90", "xA/90"), ("kp90", "key passes")], max(pct.get("xa90", 0), pct.get("kp90", 0)))
        if _top(pct, "npxg90", 85):
            add("setpiece", "Set-piece threat", [("npxg90", "npxG/90")], pct["npxg90"])
    tags.sort(key=lambda t: -t[0])
    return [t for _s, t in tags[:3]]


def group_word(group: str) -> str:
    return {"ATT": "attackers", "MID": "midfielders", "DEF": "defenders", "GK": "goalkeepers"}[group]
