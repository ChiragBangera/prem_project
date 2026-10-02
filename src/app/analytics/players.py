"""Build the scouting dataset: one row per player with every metric of the registry, ranked against role peers.

Design decisions worth knowing:

* **The registry does the work.** A metric is declared once in :mod:`app.metrics.player`; this module only gathers the inputs
  (Understat's season table, its stored match pages, WhoScored event data), computes every declared metric for everyone at once
  over numpy arrays, and ranks them. A new metric needs no change here.
* **Peers, not the whole league.** Percentiles compare a player with others in his role group (attackers vs attackers) who have
  played enough minutes. Event metrics have their own, smaller pool: only players who have event data.
* **Unknown is not zero.** A player with no event data has *no* tackles recorded, not zero; every metric built on them is blank.
  A season-long statistic built from match pages is blank unless nearly every match of the season is stored.
* **Shrunk rates for ranking.** A per-90 rate from 90 minutes is mostly noise. Ranking uses an empirical-Bayes rate (pulled toward
  the role average in proportion to how little he has played); the displayed value stays raw.
* **Honest about roles.** ``group_source`` says whether his role came from the minutes he played at each position, from Understat's
  favourite position, from the families Understat lists, or was inferred from his profile.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Sequence

import numpy as np

from app.data.models import LeagueSeason
from app.events import counters as C
from app.events import schema as ES
from app.metrics.tags import earned as earned_tags
from app.metrics.player import PLAYER_METRICS, PROFILE, PROFILE_FULL, SCORE_METRICS
from app.metrics.registry import NAN, Frame, Metric, percentile_of, shrunk

from .roles import FAMILY_GROUP, RoleModel, families_of, group_from_favorite

GROUP_ORDER = ("ATT", "MID", "DEF", "GK")
MIN_POOL_MINUTES, MAX_POOL_MINUTES = 180, 900
MIN_POSITION_MINUTES = 270   # minutes started at known positions before the position decides his role
ROLE_FEATURES = ("npxg90", "shots90", "xa90", "kp90", "xgchain90", "xgbuildup90")
GK_GROUPS = {"goalkeeping", "passing", "discipline", "availability", "impact", "rating"}  # the metric groups a goalkeeper is ranked on
SHOT_FIELDS = ("n", "goals", "xg", "sot", "blocked", "off", "post", "big", "big_goals", "pens", "pen_goals", "pen_xg", "sp_shots", "sp_xg", "sp_goals",
               "op_shots", "op_xg", "head", "head_xg", "head_goals", "dist", "box", "assisted", "fk", "fk_goals", "fk_xg", "xg_np")
LEGACY_TOTALS = ("goals", "npg", "assists", "shots", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup", "games", "minutes")


@dataclass
class SeasonInput:
    """What is known about one league season. ``None`` means "not available for this season", which is not the same as "zero"."""

    ls: LeagueSeason
    shots: dict[int, dict] | None = None      # Understat id -> shot totals; None unless nearly every match page is stored
    positions: dict[int, dict] | None = None  # Understat id -> {"pos": {code: minutes}, "starts": n, "subs": n}
    events: dict[int, dict] | None = None     # Understat id -> {"c": counters, "matches": n, "starts": n, "pos": {code: starts}}; None if no event data


@dataclass
class Merged:
    """A player's totals across the requested seasons and leagues."""

    id: int
    name: str
    teams: list[str]
    league: str
    seasons: list[int]
    position: str
    c: dict[str, float] = field(default_factory=dict)       # Understat counters
    available: int = 0                                      # minutes his club(s) played while he could have been in the squad
    shots: dict[str, float] | None = field(default_factory=dict)  # None once any of his seasons lacks full match-page coverage
    starts: int | None = 0
    pos_min: dict[str, float] = field(default_factory=dict)
    ev: dict[str, float] | None = None
    ev_matches: int = 0
    ev_starts: dict[str, int] = field(default_factory=dict)


@dataclass
class ScoutDataset:
    rows: list[dict]
    keys: list[str]                        # the metric keys, in the order of the arrays of the API payload
    pools: dict[str, dict[str, int]]       # role group -> metric -> how many peers it is ranked among
    pool_minutes: int
    ev_pool_minutes: int
    group_sizes: dict[str, int]
    leagues: list[str]
    seasons: list[int]
    role_model_ok: bool
    ages_known: int = 0
    inferred: int = 0
    event_players: int = 0
    age_reference: str | None = None
    coverage: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def event_pool_minutes(self) -> int:  # the name older callers used
        return self.ev_pool_minutes


# ---------------------------------------------------------------------- merge


def _team_matches(ls: LeagueSeason) -> dict[str, int]:
    return {name: len(team.history) for name, team in ls.teams.items()}


def merge_players(inputs: Sequence[SeasonInput]) -> list[Merged]:
    """Combine season rows per player id. Identity fields come from the newest season."""
    merged: dict[int, Merged] = {}
    for inp in sorted(inputs, key=lambda i: i.ls.season):
        ls = inp.ls
        matches = _team_matches(ls)
        for p in ls.players:
            m = merged.get(p.id)
            if m is None:
                m = merged[p.id] = Merged(p.id, p.name, list(p.teams), ls.league, [ls.season], p.position, shots={k: 0.0 for k in SHOT_FIELDS})
            else:
                m.teams, m.league, m.position = list(p.teams), ls.league, p.position
                if ls.season not in m.seasons:
                    m.seasons.append(ls.season)
            for key in ("games", "minutes", "goals", "npg", "assists", "shots", "key_passes", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup"):
                m.c[key] = m.c.get(key, 0) + getattr(p, key)
            m.available += 90 * max((matches.get(t, 0) for t in p.teams), default=0)
            if inp.shots is None or m.shots is None:
                m.shots = None
            else:
                row = inp.shots.get(p.id) or {}
                for k in SHOT_FIELDS:
                    m.shots[k] += row.get(k, 0)
            if inp.positions is not None and m.starts is not None:
                row = inp.positions.get(p.id) or {}
                m.starts += row.get("starts", 0)
                for code, minutes in (row.get("pos") or {}).items():
                    m.pos_min[code] = m.pos_min.get(code, 0) + minutes
            elif inp.positions is None:
                m.starts = None
            if inp.events is not None:
                found = inp.events.get(p.id)
                if found:
                    m.ev = m.ev or {}
                    for k, v in found["c"].items():
                        m.ev[k] = m.ev.get(k, 0) + v
                    m.ev_matches += found.get("matches", 0)
                    for code, n in (found.get("pos") or {}).items():
                        m.ev_starts[code] = m.ev_starts.get(code, 0) + n
    return list(merged.values())


# ---------------------------------------------------------------------- helpers


def sample_label(minutes: float) -> str:
    return "low" if minutes < 450 else "solid" if minutes >= 1800 else "ok"


def pool_minutes_for(seasons: Sequence[LeagueSeason]) -> int:
    """Minutes needed to enter the peer pool: ~25% of what a full-time player could have played."""
    if not seasons:
        return MIN_POOL_MINUTES
    per_season = [max((len(t.history) for t in ls.teams.values()), default=0) * 90 for ls in seasons]
    threshold = 0.25 * sum(per_season)
    return int(min(MAX_POOL_MINUTES, max(MIN_POOL_MINUTES, int(threshold // 30) * 30)))


def _age_on(dob: str | None, reference: date) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))


def _applies(metric: Metric, group: str) -> bool:
    """Whether a metric means anything for a role group (a goalkeeper has no shot quality; an outfield player has no save percentage)."""
    if group not in metric.roles:
        return False
    return not (group == "GK" and metric.roles != ("GK",) and metric.group not in GK_GROUPS)


def _modal(pos_min: dict[str, float]) -> str | None:
    return max(pos_min, key=lambda k: (pos_min[k], k)) if pos_min else None


# ---------------------------------------------------------------------- build


def build_dataset(
    inputs: Sequence[SeasonInput] | Sequence[LeagueSeason],
    *,
    dob_of: Callable[[str, str | None], str | None] | None = None,
    dob_info: Callable[[str, list, date, int], tuple[str | None, str | None]] | None = None,   # (name, teams, reference, id) -> (dob, basis); preferred over dob_of
    favorite_of: Callable[[int], str | None] | None = None,
    events_of: Callable[[int], dict | None] | None = None,    # simple seam: Understat id -> summed event counters (flat shape). The app supplies per-season SeasonInput.events instead
    today: date | None = None,
    pool_minutes: int | None = None,
) -> ScoutDataset:
    today = today or date.today()
    inputs = [i if isinstance(i, SeasonInput) else SeasonInput(i) for i in inputs]
    seasons = [i.ls for i in inputs]
    merged = merge_players(inputs)
    n = len(merged)
    pool_min = pool_minutes if pool_minutes is not None else pool_minutes_for(seasons)
    newest = max((ls.season for ls in seasons), default=today.year)
    reference = min(today, date(newest + 1, 6, 30))

    if events_of is not None:  # the flat way of supplying event totals: handy for tests and one-off scripts
        for m in merged:
            t = events_of(m.id)
            if t and t.get("min", 0) > 0:
                m.ev = _legacy_counters(t)
                m.ev_matches = t.get("matches", 0)

    # ---- raw frame: Understat counters, then shot-level sums, then events
    frame = Frame(n)
    arr = lambda f: np.array([f(m) for m in merged], dtype=float)  # noqa: E731
    for key in ("games", "minutes", "goals", "npg", "assists", "shots", "key_passes", "yellow", "red", "xg", "npxg", "xa", "xgchain", "xgbuildup"):
        frame.set(key, arr(lambda m, k=key: m.c.get(k, 0)))
    frame.set("available", arr(lambda m: m.available))
    minutes = frame["minutes"]
    frame.set("npxg_xa", frame["npxg"] + frame["xa"])
    frame.set("g_xg", frame["goals"] - frame["xg"])
    frame.set("npg_npxg", frame["npg"] - frame["npxg"])
    frame.set("a_xa", frame["assists"] - frame["xa"])
    with np.errstate(divide="ignore", invalid="ignore"):
        shots, xg = frame["shots"], frame["xg"]
        p = np.where(shots > 0, xg / shots, 0.0)
        sd = np.sqrt(shots * p * (1 - p))
        z = np.where((shots > 0) & (xg > 0) & (xg < shots) & (sd > 0), (frame["goals"] - xg) / sd, 0.0)
    frame.set("g_xg_z", z)
    frame.set("starts", arr(lambda m: NAN if m.starts is None else m.starts))
    for k in SHOT_FIELDS:
        frame.set(f"s_{k}", arr(lambda m, k=k: NAN if m.shots is None else m.shots[k]))
    ev_present = np.array([m.ev is not None for m in merged])
    for k in C.COUNTERS:
        frame.set(f"w_{k}", arr(lambda m, k=k: NAN if m.ev is None else m.ev.get(k, 0)))
    frame.set("w_matches", arr(lambda m: NAN if m.ev is None else m.ev_matches))
    ev_min = frame["w_min"]

    # ---- roles
    rates = {metric: np.where(minutes > 0, 90.0 * frame[src] / np.where(minutes > 0, minutes, 1), 0.0) for metric, src in
             (("npxg90", "npxg"), ("shots90", "shots"), ("xa90", "xa"), ("kp90", "key_passes"), ("xgchain90", "xgchain"), ("xgbuildup90", "xgbuildup"))}
    samples = []
    for i, m in enumerate(merged):
        families, _sub = families_of(m.position)
        if m.c.get("minutes", 0) >= 450 and len(families) == 1:
            samples.append((families[0], [float(rates[k][i]) for k in ROLE_FEATURES]))
    model = RoleModel.fit(samples)
    group_of: list[tuple[str, str, float]] = []
    pos2_of: list[str | None] = []
    favorite_of_row: list[str | None] = []
    for i, m in enumerate(merged):
        favorite = favorite_of(m.id) if favorite_of else None
        favorite_of_row.append(favorite)
        modal_src = m.pos_min if sum(m.pos_min.values()) >= MIN_POSITION_MINUTES else ({k: float(v) for k, v in m.ev_starts.items() if k != "Sub"} if sum(m.ev_starts.values()) >= 5 else {})
        modal = _modal({k: v for k, v in modal_src.items() if k in ES.POSITION_CODE})
        families, _sub = families_of(m.position)
        if modal:
            pos2 = ES.POSITION_CODE[modal]
            group_of.append((ES.POSITION_GROUP[pos2], "minutes", 1.0))
        elif (from_fav := group_from_favorite(favorite)):
            pos2 = ES.POSITION_CODE.get((favorite or "").upper())
            group_of.append((from_fav, "favorite", 1.0))
        elif len(families) == 1:
            pos2 = None
            group_of.append((FAMILY_GROUP[families[0]], "listed", 1.0))
        elif families and model is not None:
            pos2 = None
            family, confidence = model.classify(families, [float(rates[k][i]) for k in ROLE_FEATURES])
            group_of.append((FAMILY_GROUP[family], "inferred", round(confidence, 2)))
        else:
            pos2 = None
            fallback = "F" if "F" in families else "M" if "M" in families else (families[0] if families else "M")
            group_of.append((FAMILY_GROUP[fallback], "inferred", 0.0))
        pos2_of.append(pos2)
    group = np.array([g for g, _s, _c in group_of])

    # ---- age (shown with its basis; filters decide separately whether a name-only match may count)
    ages, doms, bases = [], [], []
    for m in merged:
        if dob_info:
            dob, basis = dob_info(m.name, m.teams, reference, m.id)
        else:
            dob, basis = (dob_of(m.name, m.teams[0] if m.teams else None) if dob_of else None), None
        doms.append(dob)
        bases.append(basis)
        ages.append(_age_on(dob, reference))
    frame.set("age", [NAN if a is None else a for a in ages])
    frame.set("mins_per_app", np.where(frame["games"] > 0, minutes / np.where(frame["games"] > 0, frame["games"], 1), 0.0))
    frame.set("minutes_share", np.clip(np.where(frame["available"] > 0, minutes / np.where(frame["available"] > 0, frame["available"], 1), 0.0), 0.0, 1.0))

    # ---- pools
    in_pool = minutes >= pool_min
    ev_top = float(np.nanmax(ev_min)) if ev_present.any() else 0.0
    # like the base pool: a quarter of the most any player has, floor 180. While only a few matches are fetched nobody reaches that floor,
    # so it can never exceed half of what the busiest player has and the pool is never empty.
    ev_pool_min = int(min(900, max(0.25 * ev_top, min(180.0, 0.5 * ev_top)))) if ev_present.any() else 0
    ev_in_pool = ev_present & (np.nan_to_num(ev_min) >= ev_pool_min)

    # ---- every metric, ranked among role peers
    values: dict[str, np.ndarray] = {}
    pct: dict[str, np.ndarray] = {}
    rank: dict[str, np.ndarray] = {}
    pools: dict[str, dict[str, int]] = {g: {} for g in GROUP_ORDER}
    for metric in PLAYER_METRICS:
        value, num, den = metric.compute(frame)
        applies = np.array([_applies(metric, g) for g in group])
        value = np.where(applies, value, NAN)   # a goalkeeper has no shot quality and an outfielder has no save percentage: blank, not zero
        values[metric.key] = value
        pool_mask = ev_in_pool if metric.needs == "events" else in_pool
        p_arr, r_arr = np.full(n, NAN), np.full(n, NAN)
        for g in GROUP_ORDER:
            if not _applies(metric, g):
                continue
            members = group == g
            pool = members & pool_mask & np.isfinite(value)
            if not pool.any():
                continue
            ranked = shrunk(metric, value, num, den, pool)
            pooled = np.sort(ranked[pool])
            sel = members & np.isfinite(ranked)
            p_arr[sel] = percentile_of(pooled, ranked[sel], metric.hib)
            better = (np.searchsorted(pooled, ranked[sel], side="left") if metric.hib is False else len(pooled) - np.searchsorted(pooled, ranked[sel], side="right"))
            r_arr[sel] = better + 1
            pools[g][metric.key] = int(pool.sum())
        pct[metric.key], rank[metric.key] = p_arr, r_arr

    # ---- role scores: the average of a player's own percentiles
    def score(table: dict[str, tuple[str, ...]], need: float) -> np.ndarray:
        out = np.full(n, NAN)
        for g, keys in table.items():
            idx = np.where(group == g)[0]
            if not len(idx):
                continue
            stack = np.vstack([pct[k][idx] for k in keys])
            ok = np.isfinite(stack)
            have = ok.sum(axis=0)
            total = np.where(ok, stack, 0.0).sum(axis=0)
            mean = np.where(have > 0, total / np.where(have > 0, have, 1), NAN)
            out[idx] = np.where(have >= max(1, math.ceil(need * len(keys))), mean, NAN)
        return out

    output = score(PROFILE, 0.6)
    score_full = np.where(ev_in_pool, score(PROFILE_FULL, 0.6), NAN)   # only for players who have event data: it is the score of all the data
    values["output"], values["score_full"] = output, score_full

    group_sizes = {g: int(((group == g) & in_pool).sum()) for g in GROUP_ORDER}
    metrics_by_key = {m.key: m for m in (*PLAYER_METRICS, *SCORE_METRICS)}
    keys = [m.key for m in (*PLAYER_METRICS, *SCORE_METRICS)]

    rows: list[dict] = []
    ages_known = 0
    event_players = int(ev_present.sum())
    for i, m in enumerate(merged):
        g, source, confidence = group_of[i]
        ages_known += ages[i] is not None
        flat = {}   # every metric is a key of the row: a number, or None where it is unknown (never a zero that looks like a measurement)
        for key, arr_ in values.items():
            v = arr_[i]
            metric = metrics_by_key[key]
            flat[key] = (round(float(v), max(3, metric.decimals + 1)) if metric.unit != "score" else round(float(v), 1)) if np.isfinite(v) else None
        pc = {k: round(float(a[i]), 1) for k, a in pct.items() if np.isfinite(a[i])}
        rk = {k: int(a[i]) for k, a in rank.items() if np.isfinite(a[i])}
        is_ev = lambda k: metrics_by_key[k].needs == "events"  # noqa: E731
        row = {
            "id": m.id, "name": m.name, "team": " / ".join(m.teams), "teams": m.teams, "league": m.league, "seasons": sorted(m.seasons), "pos": m.position,
            "group": g, "group_source": source, "group_conf": confidence, "favorite": favorite_of_row[i], "pos2": pos2_of[i],
            "pos_min": {k: round(v) for k, v in sorted(m.pos_min.items(), key=lambda kv: -kv[1]) if k != "Sub"},
            "dob": doms[i], "dob_basis": bases[i], "age": ages[i],
            "minutes": int(m.c.get("minutes", 0)), "games": int(m.c.get("games", 0)), "sample": sample_label(m.c.get("minutes", 0)), "in_pool": bool(in_pool[i]),
            "goals": int(m.c.get("goals", 0)), "npg": int(m.c.get("npg", 0)), "assists": int(m.c.get("assists", 0)), "shots": int(m.c.get("shots", 0)),
            "kp": int(m.c.get("key_passes", 0)), "yellow": int(m.c.get("yellow", 0)), "red": int(m.c.get("red", 0)),
            "xg": round(m.c.get("xg", 0), 2), "npxg": round(m.c.get("npxg", 0), 2), "xa": round(m.c.get("xa", 0), 2),
            "xgchain": round(m.c.get("xgchain", 0), 2), "xgbuildup": round(m.c.get("xgbuildup", 0), 2),
            **{k: v for k, v in flat.items() if k not in ("goals", "npg", "assists", "shots", "yellow", "red", "xg", "npxg", "xa", "minutes", "games", "age")},
            "g_xg": round(float(frame["g_xg"][i]), 2), "npg_npxg": round(float(frame["npg_npxg"][i]), 2), "a_xa": round(float(frame["a_xa"][i]), 2),
            "g_xg_z": round(float(frame["g_xg_z"][i]), 2),
            "mins_per_app": round(float(frame["mins_per_app"][i])), "minutes_share": round(float(frame["minutes_share"][i]), 3),
            "pct": {k: v for k, v in pc.items() if not is_ev(k)}, "rank": {k: v for k, v in rk.items() if not is_ev(k)}, "pool_n": group_sizes.get(g, 0),
            "evpct": {k: v for k, v in pc.items() if is_ev(k)}, "evrank": {k: v for k, v in rk.items() if is_ev(k)},
            "ev_minutes": int(round(ev_min[i])) if ev_present[i] else 0, "ev_matches": m.ev_matches if ev_present[i] else 0,
            "ev_in_pool": bool(ev_in_pool[i]), "ev_pool_n": pools[g].get("tackles90", pools[g].get("passes90", 0)), "ev_pool_minutes": ev_pool_min,
            "output": None if not np.isfinite(output[i]) else round(float(output[i]), 1),
            "score_full": None if not np.isfinite(score_full[i]) else round(float(score_full[i]), 1),
            "full_pct": {**pc},   # every percentile, base and event: the one table the new views read
            "full_rank": {**rk},
        }
        row["tags"] = archetype_tags(row) if m.c.get("minutes", 0) >= 270 else []
        rows.append(row)

    return ScoutDataset(
        rows=rows, keys=keys, pools=pools, pool_minutes=pool_min, ev_pool_minutes=ev_pool_min, group_sizes=group_sizes,
        leagues=sorted({ls.league for ls in seasons}), seasons=sorted({ls.season for ls in seasons}), role_model_ok=model is not None,
        ages_known=ages_known, inferred=sum(1 for r in rows if r["group_source"] == "inferred"), event_players=event_players,
        age_reference=reference.isoformat(),
    )


def _legacy_counters(t: dict) -> dict[str, float]:
    """The flat counters the first event store produced, renamed to the current counter names."""
    rename = {"aer": "aerials", "aer_won": "aerial_won", "aer_def": "aerial_def", "aer_def_won": "aerial_def_won", "int": "interceptions", "rec": "recoveries",
              "disp": "dispossessed", "start": "starts"}
    out = {rename.get(k, k): v for k, v in t.items() if isinstance(v, (int, float)) and k not in ("id",)}
    out["min"] = t.get("min", 0)
    return out


# ---------------------------------------------------------------------- archetypes


def archetype_tags(row: dict) -> list[dict]:
    """Rule-based role labels with the evidence that earned them (max three). The rules live in :mod:`app.metrics.tags`."""
    return earned_tags(row["group"], {**row["pct"], **row.get("evpct", {})})


def group_word(group: str) -> str:
    return {"ATT": "attackers", "MID": "midfielders", "DEF": "defenders", "GK": "goalkeepers"}[group]
