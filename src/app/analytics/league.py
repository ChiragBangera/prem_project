from __future__ import annotations

from .percentiles import to_float
from ._shared import HONEST_LEAGUE_LIMITATIONS, round_value


def _rows(table: list) -> list[list]:
    return table[1:] if len(table) > 1 else []


def league_is_lying(table: list) -> dict:
    """xPTS gap for every team — the canonical 'table is lying' dashboard."""
    enrich = []
    for row in _rows(table):
        try:
            team = row[0]
            pts = float(row[7])
            xpts = float(row[17])
            xg = float(row[8])
            xga = float(row[10])
            goals = float(row[5])
            goals_against = float(row[6])
        except (IndexError, TypeError, ValueError):
            continue
        enrich.append(
            {
                "team": team,
                "points": int(pts),
                "xPTS": round_value(xpts),
                "xPTS_gap": round_value(pts - xpts),
                "g_minus_xg": round_value(goals - xg),
                "xga_minus_ga": round_value(xga - goals_against),
            }
        )
    enrich.sort(key=lambda item: item["xPTS_gap"], reverse=True)
    overperformer = enrich[0] if enrich else None
    underperformer = enrich[-1] if enrich else None
    return {
        "rows": enrich,
        "biggest_overperformer": overperformer,
        "biggest_underperformer": underperformer,
        "interpretation": (
            "Points minus xPTS quantifies 'table lies'. Mean-reverting within-season: persistent positive "
            "gaps usually regress, persistent negative gaps usually climb."
        ),
        "limitations": HONEST_LEAGUE_LIMITATIONS,
    }


def finishing_and_defensive_variance(table: list) -> dict:
    """Per-league stdev of team G-xG and xGA-GA — how much of the table is luck."""
    g_xg = []
    xga_ga = []
    for row in _rows(table):
        try:
            goals = float(row[5])
            xg = float(row[8])
            xga = float(row[10])
            goals_against = float(row[6])
        except (IndexError, TypeError, ValueError):
            continue
        g_xg.append(goals - xg)
        xga_ga.append(xga - goals_against)
    return {
        "finishing_variance": {
            "mean_g_minus_xg": round_value(sum(g_xg) / len(g_xg) if g_xg else 0),
            "stdev_g_minus_xg": round_value(_stdev(g_xg)),
        },
        "defensive_variance": {
            "mean_xga_minus_ga": round_value(sum(xga_ga) / len(xga_ga) if xga_ga else 0),
            "stdev_xga_minus_ga": round_value(_stdev(xga_ga)),
        },
        "interpretation": (
            "High finishing stdev = the league table is heavily luck-driven this season; low stdev = settled. "
            "Defensive variance mixes GK quality and model error — do NOT attribute to keepers alone."
        ),
        "limitations": HONEST_LEAGUE_LIMITATIONS,
    }


def ppda_ranking(table: list) -> dict:
    """Teams ranked by pressing intensity (low PPDA = intense press)."""
    rows = []
    for row in _rows(table):
        try:
            rows.append(
                {
                    "team": row[0],
                    "PPDA": round_value(float(row[13])),
                    "OPPDA": round_value(float(row[14])),
                    "deep_completions": int(float(row[15])),
                    "deep_completions_allowed": int(float(row[16])),
                }
            )
        except (IndexError, TypeError, ValueError):
            continue
    rows.sort(key=lambda item: item["PPDA"])
    return {
        "ranking": rows,
        "most_intense_press": rows[0] if rows else None,
        "least_intense_press": rows[-1] if rows else None,
        "interpretation": (
            "PPDA ranking within the league. NOTE PPDA is also opponent-possession-dependent and "
            "game-state-dependent; treat as a style signature, not pure defensive quality."
        ),
        "limitations": HONEST_LEAGUE_LIMITATIONS,
    }


def process_pace(table: list) -> dict:
    """League-wide xG/game and xGA/game — pace-of-chances signature."""
    rows = _rows(table)
    if not rows:
        return {"xG_per_game": None, "xGA_per_game": None, "matches": 0}
    total_xg = sum(to_float(r[8]) for r in rows if len(r) > 8)
    total_xga = sum(to_float(r[10]) for r in rows if len(r) > 10)
    matches = sum(int(to_float(r[1])) for r in rows if len(r) > 1)
    return {
        "xG_per_game": round_value(total_xg / matches if matches else 0),
        "xGA_per_game": round_value(total_xga / matches if matches else 0),
        "matches": matches,
        "interpretation": (
            "League average xG/game. Cross-league absolute values can be model-dependent "
            "(Understat's xG calibration across leagues is not fully disclosed)."
        ),
        "limitations": HONEST_LEAGUE_LIMITATIONS,
    }


def league_report(table: list) -> dict:
    return {
        "is_lying": league_is_lying(table),
        "variance": finishing_and_defensive_variance(table),
        "ppda_ranking": ppda_ranking(table),
        "pace": process_pace(table),
        "limitations": HONEST_LEAGUE_LIMITATIONS,
    }


def _stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return var ** 0.5
