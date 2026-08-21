from __future__ import annotations

"""Tactical archetypes: rule-based labels from league-table z-scores.

Honest scope: every feature comes from the same season's league table
(style_profile) — no event data, no shots. This is a deterministic heuristic,
not a learned cluster; set-piece reliance and build-up shape are not
detectable from table metrics alone (surfaced in honest_note).
"""

import math

from .team import style_profile
from ._shared import to_float

FEATURE_KEYS = ("xg_per_game", "xga_per_game", "npxgd", "ppda", "oppda", "dc_per_game")

HONEST_NOTE = (
    "Rule-based heuristic on this season's league-table z-scores — not a learned "
    "cluster. Set-piece reliance is not detectable from table metrics alone."
)

# Ordered rules: first match wins. Conditions are (feature, comparator, threshold).
RULES = [
    (
        "Expansive / Chaos",
        "Trades at both ends — high attacking volume conceded as well as created.",
        [("xg_per_game", ">=", 0.8), ("xga_per_game", ">=", 0.8)],
    ),
    (
        "Control & Territory",
        "Dominant territory and box penetration with defensive control.",
        [("dc_per_game", ">=", 0.7), ("xga_per_game", "<=", -0.3), ("ppda", "<=", 0.5)],
    ),
    (
        "High Press & Transition",
        "Intense high press feeding a positive non-penalty process.",
        [("ppda", "<=", -0.7), ("npxgd", ">=", 0.2)],
    ),
    (
        "Low Block & Counter",
        "Comfortable without the ball; defensively solid deep block.",
        [("ppda", ">=", 0.5), ("xga_per_game", "<=", -0.3)],
    ),
    (
        "Direct & Vertical",
        "Little deep-buildup penetration but still productive going forward.",
        [("dc_per_game", "<=", -0.5), ("ppda", ">=", 0.0), ("xg_per_game", ">=", -0.3)],
    ),
    (
        "Balanced Mid",
        "No strong stylistic extreme versus the league baseline.",
        [],
    ),
]


def _per_game(total: float, matches: float) -> float:
    return total / matches if matches else 0.0


def _features_from_style(style: dict) -> dict:
    matches = to_float(style.get("matches")) or 0.0
    return {
        "xg_per_game": to_float(style.get("xG_per_game")) or _per_game(to_float(style.get("xG")), matches),
        "xga_per_game": to_float(style.get("xGA_per_game")) or _per_game(to_float(style.get("xGA")), matches),
        "npxgd": to_float(style.get("npxGD")),
        "ppda": to_float(style.get("PPDA")),
        "oppda": to_float(style.get("OPPDA")),
        "dc_per_game": _per_game(to_float(style.get("deep_completions")), matches),
    }


def league_feature_stats(table_rows: list[list]) -> dict:
    """Mean/std per feature across all teams in one season's table.

    `table_rows` includes the header row ([Team, M, W, ...]) which is skipped.
    std of 0 is kept so team_z can guard z to 0.
    """
    rows = [r for r in (table_rows or []) if r and str(r[0]).strip().lower() != "team"]
    per_team = []
    for row in rows:
        if len(row) < 18:
            continue
        style = style_profile(row)
        per_team.append(_features_from_style(style))
    stats = {}
    for key in FEATURE_KEYS:
        values = [t[key] for t in per_team]
        n = len(values)
        mean = sum(values) / n if n else 0.0
        var = sum((v - mean) ** 2 for v in values) / n if n else 0.0
        stats[key] = {"mean": round(mean, 4), "std": round(math.sqrt(var), 4)}
    return stats


def team_z(style: dict, stats: dict) -> dict:
    features = _features_from_style(style)
    out = {}
    for key in FEATURE_KEYS:
        value = features[key]
        entry = stats.get(key) or {}
        std = to_float(entry.get("std"))
        mean = to_float(entry.get("mean"))
        z = 0.0 if std <= 0 else (value - mean) / std
        out[key] = {"value": round(value, 3), "z": round(z, 3)}
    return out


def _satisfied_with_margin(comparator: str, z: float, threshold: float) -> bool:
    if comparator == ">=":
        return z >= threshold + 0.3
    return z <= threshold - 0.3


def classify(z_map: dict) -> dict:
    """First-match-wins rules over z-scores; confidence = strongly- met share."""
    for label, description, conditions in RULES:
        if not conditions:
            return {
                "label": label,
                "description": description,
                "confidence": 0.5,  # fallback rule: neutral confidence
            }
        hit = all(
            (z_map[key]["z"] >= thr) if comp == ">=" else (z_map[key]["z"] <= thr)
            for key, comp, thr in conditions
        )
        if hit:
            strong = sum(
                1 for key, comp, thr in conditions if _satisfied_with_margin(comp, z_map[key]["z"], thr)
            )
            confidence = round(strong / len(conditions), 2)
            return {"label": label, "description": description, "confidence": min(confidence, 1.0)}
    # Unreachable: Balanced Mid has no conditions and always returns.
    return {"label": "Balanced Mid", "description": RULES[-1][1], "confidence": 0.5}


def _z_distance(a: dict, b: dict) -> float:
    return math.sqrt(sum((a[k]["z"] - b[k]["z"]) ** 2 for k in FEATURE_KEYS))


def archetype_report(team_row: list, table_rows: list[list], season_note: str | None = None) -> dict:
    """Full archetype payload for one team within its season's table."""
    stats = league_feature_stats(table_rows)
    z_map = team_z(style_profile(team_row), stats)

    matches_played = to_float(team_row[1]) if len(team_row) > 1 else 0.0
    note = HONEST_NOTE
    if matches_played <= 0:
        note += " Insufficient matches played."
    if season_note:
        note += f" {season_note}"

    label = classify(z_map)["label"]
    peers = []
    for row in table_rows or []:
        if not row or len(row) < 18 or str(row[0]).strip().lower() == "team":
            continue
        if str(row[0]).strip().lower() == str(team_row[0]).strip().lower():
            continue
        other_z = team_z(style_profile(row), stats)
        other_label = classify(other_z)["label"]
        if other_label != label:
            continue
        peers.append({"team": row[0], "label": other_label, "distance": round(_z_distance(z_map, other_z), 3)})
    peers.sort(key=lambda p: p["distance"])

    result = classify(z_map)
    return {
        "label": result["label"],
        "description": result["description"],
        "confidence": result["confidence"],
        "features": z_map,
        "peers": peers,
        "honest_note": note,
    }


def league_archetype_map(table_rows: list[list]) -> dict:
    """Label every team in the table + counts, for the league view."""
    stats = league_feature_stats(table_rows)
    by_team = {}
    counts: dict[str, int] = {}
    for row in table_rows or []:
        if not row or len(row) < 18 or str(row[0]).strip().lower() == "team":
            continue
        label = classify(team_z(style_profile(row), stats))["label"]
        by_team[row[0]] = label
        counts[label] = counts.get(label, 0) + 1
    return {"by_team": by_team, "counts": counts, "honest_note": HONEST_NOTE}
