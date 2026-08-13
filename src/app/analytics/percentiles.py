from __future__ import annotations

"""Per-90 normalization and percentile ranking — the foundation for radar/pizza
profiles and player discovery. Pure functions over fetched Understat row dicts.

Honest scope: stats.rank() is vs the *slice you pass in*. Callers are responsible
for filtering by league/position/minutes-threshold before ranking so percentiles
are meaningful (e.g. don't percentile a GK against FWs).
"""

from typing import Iterable

import math


def to_float(value, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def per90(value: float, minutes: float) -> float:
    """Normalize a counting stat to per-90. Returns 0.0 when minutes <= 0."""
    if minutes <= 0:
        return 0.0
    return value * 90.0 / minutes


def player_minutes(row: dict) -> float:
    return to_float(row.get("time", 0))


def player_per90(row: dict, key: str) -> float:
    return round(per90(to_float(row.get(key, 0)), player_minutes(row)), 4)


# Canonical attacking-all-action metric vectors, per position group.
# Each entry: (api_key, label, per90?, want_higher?). Used for radars.
PLAYER_RADAR_METRICS: tuple[tuple[str, str, bool, bool], ...] = (
    ("goals", "Goals", True, True),
    ("xG", "xG", True, True),
    ("assists", "Assists", True, True),
    ("xA", "xA", True, True),
    ("shots", "Shots", True, True),
    ("key_passes", "Key passes", True, True),
    ("xGChain", "xG chain", True, True),
    ("xGBuildup", "xG buildup", True, True),
    ("npxG", "NP xG", True, True),
)


# Which radar metrics apply by position group.
POSITION_GROUPS = {
    "GK": (),
    "D": (
        "goals", "xG", "assists", "xA", "key_passes",
        "xGChain", "xGBuildup", "npxG",
    ),
    "M": (
        "goals", "xG", "assists", "xA", "shots", "key_passes",
        "xGChain", "xGBuildup", "npxG",
    ),
    "F": (
        "goals", "xG", "assists", "xA", "shots", "key_passes",
        "xGChain", "xGBuildup", "npxG",
    ),
}


def position_group(position_code: str | None) -> str:
    """Legacy single-family guess from the first token (alphabetical!).

    Prefer group_from_favorite / position_families — the league string's first
    token is NOT the player's primary role.
    """
    if not position_code:
        return ""
    head = position_code.strip().split()[0].upper()
    if head in {"G", "GK"}:
        return "GK"
    if head in {"D", "DC", "DL", "DR", "D M"}:
        return "D"
    if head in {"M", "MC", "ML", "MR", "AM", "DM"}:
        return "M"
    if head in {"F", "FW", "FW S", "S"}:
        return "F"
    return head


def group_from_favorite(favorite_position: str | None) -> str:
    """Map Understat's favorite_position to a role family.

    Understat's raw codes follow classic football notation: DC/DL/DR = centre/
    left/right BACKS (defence), but DMC/DML = defensive MIDFIELDERS — the
    family check is prefix-aware (DMC is midfield, not defence).
    """
    if not favorite_position:
        return ""
    head = favorite_position.strip().upper()
    if head == "NON":
        return ""
    if head.startswith("GK"):
        return "GK"
    if head.startswith(("FW", "FWL", "FWR", "ST")):
        return "F"
    if head.startswith(("DMC", "DML", "MC", "ML", "MR", "AM", "AMC", "AML", "AMR", "DM", "M")):
        return "M"
    if head.startswith(("DC", "DL", "DR", "SW", "WB", "D")):
        return "D"
    return ""


def position_families(position_code: str | None) -> set[str]:
    """Families a multi-role league string belongs to.

    Understat league strings are alphabetical role lists ('D M S' = appeared
    as D, M and substitute). The 'S' token is a substitute marker, not a role.
    """
    if not position_code:
        return set()
    families = set()
    for token in position_code.strip().upper().split():
        if token == "S":
            continue
        if token.startswith("G"):
            families.add("GK")
        elif token.startswith("F"):
            families.add("F")
        elif token.startswith("M"):
            families.add("M")
        elif token.startswith("D"):
            families.add("D")
    return families


def filter_by_families(rows: list[dict], families: set[str]) -> list[dict]:
    if not families:
        return list(rows)
    return [r for r in rows if position_families(r.get("position")) & families]


def percentile_rank(value: float, within: Iterable[float]) -> float:
    """Average-rank percentile of `value` against `within` (0..100).

    Uses average ranks for ties, the standard radar/pizza chart handling.
    """
    series = sorted(to_float(v) for v in within)
    if not series:
        return 50.0
    n = len(series)
    below = sum(1 for v in series if v < value)
    equal = sum(1 for v in series if v == value)
    if equal == 0:
        raw = 100.0 * below / max(n - 1, 1)
    else:
        raw = 100.0 * (below + (equal - 1) / 2) / max(n - 1, 1)
    # Values strictly above every peer map to rank n+1, which would exceed 100
    # under the (n-1) normalization; clamp to the documented 0..100 range.
    return round(max(0.0, min(100.0, raw)), 2)


def radar_profile(player: dict, peers: list[dict], metrics: tuple[tuple[str, str, bool, bool], ...] | None = None) -> list[dict]:
    """Build a percentile radar/pizza profile for one player vs peers.

    Each entry: {key, label, raw, per90_value, percentile, higher_is_better}.
    Callers MUST pre-filter `peers` to same position group and minutes threshold.
    """
    chosen = metrics or PLAYER_RADAR_METRICS
    minutes = player_minutes(player)
    out: list[dict] = []
    for key, label, do_per90, higher in chosen:
        raw = to_float(player.get(key, 0))
        p90 = round(per90(raw, minutes), 4) if do_per90 else raw
        if do_per90:
            peer_values = [per90(to_float(p.get(key, 0)), player_minutes(p)) for p in peers]
        else:
            peer_values = [to_float(p.get(key, 0)) for p in peers]
        pct = percentile_rank(p90, peer_values) if higher else 100.0 - percentile_rank(p90, peer_values)
        out.append(
            {
                "key": key,
                "label": label,
                "raw": round(raw, 3),
                "per90": p90,
                "percentile": pct,
                "higher_is_better": higher,
            }
        )
    return out


def filter_by_minutes(rows: list[dict], minimum_minutes: float = 900.0) -> list[dict]:
    return [r for r in rows if player_minutes(r) >= minimum_minutes]


def filter_by_position(rows: list[dict], group: str) -> list[dict]:
    if not group:
        return list(rows)
    return [r for r in rows if position_group(r.get("position")) == group]
