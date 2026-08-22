from __future__ import annotations

import math
from typing import Iterable

from ._shared import round_value
from .percentiles import (
    to_float,
    per90,
    player_minutes,
    player_per90,
    position_group,
    position_families,
    filter_by_minutes,
    filter_by_families,
    radar_profile,
    PLAYER_RADAR_METRICS,
)


HONEST_LIMITATIONS = [
    "No post-shot xG: G-xG mixes finishing, GK quality, and model error; treat as diagnostic, not pure skill.",
    "No age/DOB in Understat: peak/age curves are not computable without external data.",
    "`position` is the listed role, not the in-match role; positional comparisons are approximate.",
    "`shots` coordinates are shot END location (where contact happened), not shot release or carry start.",
    "Percentiles rank within the peer set you supply; pre-filter by league/position/minutes first.",
]


def _round(value: float, digits: int = 2) -> float:
    return round(value, digits)


def per90_breakdown(player: dict) -> dict:
    """Per-90 normalization of the canonical involvement plus attacking output."""
    minutes = player_minutes(player)
    keys = ["goals", "xG", "npxG", "assists", "xA", "shots", "key_passes", "xGChain", "xGBuildup"]
    rates: dict[str, float] = {}
    for key in keys:
        rates[key] = player_per90(player, key)

    return {
        "raw": {k: _round(to_float(player.get(k, 0))) for k in keys},
        "per90": rates,
        "games": to_float(player.get("games", 0)),
        "minutes": minutes,
        "team_title": player.get("team_title"),
        "position": player.get("position"),
        "position_group": position_group(player.get("position")),
    }


def radar(player: dict, peers: list[dict], minimum_minutes: float = 900.0) -> dict:
    """Percentile radar / pizza chart vs pre-filtered peers.

    `peers` is expected to be the *already position+minutes filtered* slice.
    For convenience this function also does the same filters defensively and
    reports how many peers survived.
    """
    group = position_group(player.get("position"))
    families = position_families(player.get("position"))
    same_position = filter_by_families(peers, families)
    same_position = filter_by_minutes(same_position, minimum_minutes)

    profile = radar_profile(player, same_position)

    return {
        "position_group": group,
        "peer_count": len(same_position),
        "minutes_threshold": minimum_minutes,
        "profile": profile,
        "limitations": HONEST_LIMITATIONS,
    }


def involvement_profile(player: dict) -> dict:
    """xGChain / xGBuildup breakdown — the canonical deep-creation involvement."""
    xg_chain = to_float(player.get("xGChain", 0))
    xg_buildup = to_float(player.get("xGBuildup", 0))
    minutes = player_minutes(player)

    share = None
    if xg_chain > 0:
        share = round(xg_buildup / xg_chain, 3)

    return {
        "xGChain": _round(xg_chain),
        "xGBuildup": _round(xg_buildup),
        "xGChain_per90": round(per90(xg_chain, minutes), 3),
        "xGBuildup_per90": round(per90(xg_buildup, minutes), 3),
        "buildup_share_of_chain": share,
    }


def shot_selection_profile(player: dict) -> dict:
    """From the player-season table: how the player's shots are taking.

    Uses the player's season totals (`shots`, `xG`, `goals`, `npg`, `npxG`) to
    classify shot mix — keep honest that this is a *selection* description, not
    a finishing-skill claim. NOTE no penalty split on volume here beyond `npg`.
    """
    shots = to_float(player.get("shots", 0))
    xg = to_float(player.get("xG", 0))
    npg = to_float(player.get("npg", 0))
    npxg = to_float(player.get("npxG", 0))
    minutes = player_minutes(player)

    xg_per_shot = None
    npxg_per_shot: float | None = None
    if shots > 0:
        xg_per_shot = round(xg / shots, 4)
        npxg_per_shot = round(npxg / shots, 4)

    return {
        "shots": shots,
        "shots_per90": round(per90(shots, minutes), 3),
        "xG_per_shot": xg_per_shot,
        "npxG_per_shot": npxg_per_shot,
        "penalty_shots": _round(xg - npxg),
        "non_penalty_goals": npg,
        "interpretation": (
            "How the player chooses their shots — volume vs quality mix. "
            "Per90 normalizes for minutes; xG_per_shot distinguishes selective "
            "from volume shooters. Does not measure finishing skill (see caveat)."
        ),
    }


def finishing_overperformance(player: dict) -> dict:
    """Goals minus xG, with an honest CI.

    `g_minus_xg` is the standard finishing-deviation delta. We add a Wilson-style
    binomial interval around the *goal probability mass* — interpret this as 'if
    every shot scored with probability equal to xG, how extreme is this delta?'.
    """
    goals = to_float(player.get("goals", 0))
    xg = to_float(player.get("xG", 0))
    npg = to_float(player.get("npg", 0))
    npxg = to_float(player.get("npxG", 0))
    shots = to_float(player.get("shots", 0))

    delta = _round(goals - xg)
    np_delta = _round(npg - npxg)

    # Simple binomial standard error on goals given total xG:
    # treat each shot as Bernoulli(pi = xG_i). Observed goals variance ~ sum(pi*(1-pi)).
    # We don't have per-shot pi at season-table level, so approximate using mean xG/shot * shots.
    std_error = None
    if shots > 0:
        mean_pi = xg / shots
        variance = shots * mean_pi * (1 - mean_pi)
        std_error = math.sqrt(variance) if variance > 0 else 0.0
        std_error = round(std_error, 2)

    ci_low = ci_high = None
    if std_error is not None and std_error > 0:
        delta_low = (goals - xg) - 1.96 * std_error
        delta_high = (goals - xg) + 1.96 * std_error
        ci_low = round(delta_low, 2)
        ci_high = round(delta_high, 2)

    return {
        "goals": goals,
        "xG": _round(xg),
        "g_minus_xg": delta,
        "npg_minus_npxg": np_delta,
        "shots": shots,
        "g_minus_xg_std_error": std_error,
        "g_minus_xg_ci95": {"low": ci_low, "high": ci_high} if ci_low is not None else None,
        "interpretation": (
            "Goals minus xG as a *deviation from expected*. The CI is an approximate "
            "binomial 95% band on goals given shot volume and mean xG. Small samples are "
            "NOISE-dominated: finishing skill is not separable from GK quality without "
            "post-shot xG, which Understat does not provide."
        ),
    }


def creative_dominance(player: dict, all_players_team: list[dict]) -> dict:
    """Player xA as a share of team xA — is the offense running through them?"""
    player_xa = to_float(player.get("xA", 0))
    team_name = player.get("team_title")
    team_xa = sum(
        to_float(p.get("xA", 0))
        for p in all_players_team
        if p.get("team_title") == team_name
    )
    share = round(player_xa / team_xa, 3) if team_xa > 0 else None
    return {
        "team_title": team_name,
        "player_xA": _round(player_xa),
        "team_xA": _round(team_xa),
        "xA_share": share,
    }


def similar_players(target: dict, pool: list[dict], top_k: int = 5, minimum_minutes: float = 900.0) -> dict:
    """Nearest-neighbour search over a standardized per-90 metric vector.

    Honest nearest-neighbour similarity (cosine on standardized rates within
    position group). Pool should be league-scoped; we filter by position and
    minutes internally.
    """
    families = position_families(target.get("position"))
    candidates = filter_by_families(pool, families)
    candidates = filter_by_minutes(candidates, minimum_minutes)
    candidates = [c for c in candidates if c.get("id") != target.get("id")]

    keys = [k for k, _lbl, _p90, _h in PLAYER_RADAR_METRICS]
    target_vec = _standardized_vector(target, pool, keys)

    scored = []
    for candidate in candidates:
        vec = _standardized_vector(candidate, pool, keys)
        score = _cosine_similarity(target_vec, vec)
        scored.append((score, candidate))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return {
        "target": target.get("player_name"),
        "position_group": sorted(families),
        "pool_after_filters": len(candidates),
        "matches": [
            {
                "player_name": c.get("player_name"),
                "team_title": c.get("team_title"),
                "similarity": round(score, 3),
                "position": c.get("position"),
                "minutes": _round(player_minutes(c)),
            }
            for score, c in scored[:top_k]
        ],
    }


def _standardized_vector(player: dict, pool: list[dict], keys: list[str]) -> list[float]:
    """Compute z-scored per-90 metric vector vs pool."""
    minutes = player_minutes(player)
    vec: list[float] = []
    for key in keys:
        p90 = per90(to_float(player.get(key, 0)), minutes)
        pool_values = [per90(to_float(p.get(key, 0)), player_minutes(p)) for p in pool]
        mu = sum(pool_values) / len(pool_values) if pool_values else 0.0
        sigma = math.sqrt(sum((v - mu) ** 2 for v in pool_values) / len(pool_values)) if pool_values else 0.0
        z = 0.0 if sigma == 0 else (p90 - mu) / sigma
        vec.append(z)
    return vec


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def compute_player_l1_metrics(player: dict, peers: list[dict], min_minutes: float = 450.0) -> list[dict]:
    """Compute Layer 1 Decision Metrics with peer benchmark deltas and percentiles."""
    group = position_group(player.get("position"))
    families = position_families(player.get("position"))
    same_pos = filter_by_families(peers, families)
    qualified_peers = filter_by_minutes(same_pos, min_minutes)
    if not qualified_peers:
        qualified_peers = same_pos or [player]

    def _metric_entry(key: str, label: str, subline: str, decimals: int = 2, unit: str = "/90", better: str = "higher"):
        val = player_per90(player, key) if key not in ("g_minus_xg", "conversion", "xG_per_shot") else 0.0
        if key == "g_minus_xg":
            val = to_float(player.get("goals", 0)) - to_float(player.get("xG", 0))
        elif key == "conversion":
            shots = to_float(player.get("shots", 0))
            val = (to_float(player.get("goals", 0)) / shots * 100.0) if shots > 0 else 0.0
        elif key == "xG_per_shot":
            shots = to_float(player.get("shots", 0))
            val = (to_float(player.get("xG", 0)) / shots) if shots > 0 else 0.0

        peer_vals = []
        for p in qualified_peers:
            if key in ("g_minus_xg", "conversion", "xG_per_shot"):
                if key == "g_minus_xg":
                    pv = to_float(p.get("goals", 0)) - to_float(p.get("xG", 0))
                elif key == "conversion":
                    ps = to_float(p.get("shots", 0))
                    pv = (to_float(p.get("goals", 0)) / ps * 100.0) if ps > 0 else 0.0
                elif key == "xG_per_shot":
                    ps = to_float(p.get("shots", 0))
                    pv = (to_float(p.get("xG", 0)) / ps) if ps > 0 else 0.0
            else:
                pv = player_per90(p, key)
            peer_vals.append(pv)

        peer_avg = sum(peer_vals) / len(peer_vals) if peer_vals else 0.0
        delta = val - peer_avg

        if len(peer_vals) > 1:
            count_below = sum(1 for pv in peer_vals if pv < val)
            count_equal = sum(1 for pv in peer_vals if pv == val)
            pct_rank = round((count_below + 0.5 * count_equal) / len(peer_vals) * 100.0, 1)
        else:
            pct_rank = 50.0

        is_pos = (delta >= 0) if better == "higher" else (delta <= 0)

        return {
            "key": key,
            "label": label,
            "value": round_value(val, decimals),
            "benchmark": round_value(peer_avg, decimals),
            "delta": round_value(delta, decimals),
            "delta_display": f"{delta:+.{decimals}f}",
            "percentile": pct_rank,
            "unit": unit,
            "subline": subline,
            "is_positive": is_pos,
            "sample_size": len(qualified_peers),
        }

    return [
        _metric_entry("npxG", "NP xG / 90", "Non-penalty goal threat", decimals=2, unit="/90"),
        _metric_entry("xA", "xA / 90", "Chances created quality", decimals=2, unit="/90"),
        _metric_entry("xGChain", "xG Chain / 90", "Total possession involvement", decimals=2, unit="/90"),
        _metric_entry("xGBuildup", "xG Buildup / 90", "Deep buildup contribution", decimals=2, unit="/90"),
        _metric_entry("xG_per_shot", "xG / Shot", "Shot selection quality", decimals=3, unit="xG"),
        _metric_entry("g_minus_xg", "Goals − xG", "Finishing variance", decimals=2, unit="goals"),
    ]


def player_report(player: dict, league_peers: list[dict], team_roster: list[dict] | None = None,
                  shots: list[dict] | None = None) -> dict:
    """Bundle the full player analytics view into one JSON-serializable payload."""
    return {
        "player": {
            "id": player.get("id"),
            "name": player.get("player_name"),
            "team_title": player.get("team_title"),
            "position": player.get("position"),
            "position_group": position_group(player.get("position")),
        },
        "l1_metrics": compute_player_l1_metrics(player, league_peers),
        "per90_breakdown": per90_breakdown(player),
        "involvement_profile": involvement_profile(player),
        "shot_selection": shot_selection_profile(player),
        "finishing_overperformance": finishing_overperformance(player),
        "radar": radar(player, league_peers),
        "creative_dominance": creative_dominance(player, team_roster or league_peers),
        "similar_players": similar_players(player, league_peers, top_k=5),
        "pressing_output": pressing_output(shots) if shots else None,
        "limitations": HONEST_LIMITATIONS,
    }


REGAIN_ACTIONS = {"BallRecovery", "Dispossessed", "BlockedPass", "Rebound"}


def shot_minute_buckets(shots: list[dict]) -> list[dict]:
    """Shots, xG and goals in 15-minute buckets (0-15 ... 75-90+)."""
    buckets = [(0, 15, "0–15'"), (15, 30, "15–30'"), (30, 45, "30–45'"),
               (45, 60, "45–60'"), (60, 75, "60–75'"), (75, 200, "75–90+'")]
    rows = []
    for start, end, label in buckets:
        in_bucket = [s for s in shots if start <= to_float(s.get("minute")) < end]
        rows.append(
            {
                "label": label,
                "shots": len(in_bucket),
                "xG": round_value(sum(to_float(s.get("xG")) for s in in_bucket), 2),
                "goals": sum(1 for s in in_bucket if str(s.get("result", "")).lower() == "goal"),
            }
        )
    return rows


def home_away_shot_split(shots: list[dict]) -> dict:
    """Shot volume, xG and goals split by venue."""
    home = [s for s in shots if s.get("h_a") == "h"]
    away = [s for s in shots if s.get("h_a") == "a"]

    def summarize(rows):
        return {
            "shots": len(rows),
            "xG": round_value(sum(to_float(s.get("xG")) for s in rows), 2),
            "goals": sum(1 for s in rows if str(s.get("result", "")).lower() == "goal"),
        }

    return {"home": summarize(home), "away": summarize(away)}


def pressing_output(shots: list[dict]) -> dict:
    """Chances the player finished from possession-regain situations.

    Understat has no per-player pressing counts; the honest available signal
    is the `lastAction` of each shot: BallRecovery / Dispossessed /
    BlockedPass / Rebound mean the chance came from a possession regain.
    This measures the OUTPUT of pressing (chances finished after regains),
    not pressing actions themselves.
    """
    total_xg = sum(to_float(shot.get("xG")) for shot in shots)
    total_goals = sum(1 for shot in shots if str(shot.get("result", "")).lower() == "goal")
    regain_shots = [shot for shot in shots if shot.get("lastAction") in REGAIN_ACTIONS]
    regain_xg = sum(to_float(shot.get("xG")) for shot in regain_shots)
    regain_goals = sum(1 for shot in regain_shots if str(shot.get("result", "")).lower() == "goal")
    by_action = {}
    for action in sorted(REGAIN_ACTIONS):
        subset = [shot for shot in regain_shots if shot.get("lastAction") == action]
        if not subset:
            continue
        by_action[action] = {
            "shots": len(subset),
            "xG": round_value(sum(to_float(shot.get("xG")) for shot in subset), 2),
            "goals": sum(1 for shot in subset if str(shot.get("result", "")).lower() == "goal"),
        }
    return {
        "total_shots": len(shots),
        "total_xG": round_value(total_xg, 2),
        "regain_shots": len(regain_shots),
        "regain_xG": round_value(regain_xg, 2),
        "regain_goals": regain_goals,
        "regain_xG_share": round_value(regain_xg / total_xg, 3) if total_xg > 0 else 0.0,
        "by_action": by_action,
        "interpretation": (
            "xG from shots that followed a possession regain (BallRecovery, Dispossessed, "
            "BlockedPass, Rebound). This measures how often the player converts pressing "
            "rewards — it is not a count of pressing actions, which Understat does not track."
        ),
        "limitations": [
            "This is press OUTPUT (chances after regains), not pressing activity; no pressure-event data exists in Understat.",
            "A player's own shots carry the whole team's regain; team-mates earn the regain itself.",
            "Single-season regain samples are small — treat as a profile hint, not a ranking.",
        ],
    }
