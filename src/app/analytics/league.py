from __future__ import annotations

from .percentiles import to_float
from ._shared import HONEST_LEAGUE_LIMITATIONS, round_value


def _rows(table: list) -> list[list]:
    return table[1:] if len(table) > 1 else []


def league_table_full(table: list) -> list[dict]:
    """Complete 18-metric Understat team league table with rank (№) and derived diagnostic metrics."""
    rows = []
    for i, row in enumerate(_rows(table)):
        try:
            team = row[0]
            m = int(float(row[1]))
            w = int(float(row[2]))
            d = int(float(row[3]))
            l = int(float(row[4]))
            g = int(float(row[5]))
            ga = int(float(row[6]))
            pts = int(float(row[7]))
            xg = float(row[8])
            npxg = float(row[9])
            xga = float(row[10])
            npxga = float(row[11])
            npxgd = float(row[12])
            ppda = float(row[13])
            oppda = float(row[14])
            dc = int(float(row[15]))
            odc = int(float(row[16]))
            xpts = float(row[17])
        except (IndexError, TypeError, ValueError):
            continue

        rows.append(
            {
                "rank": i + 1,
                "team": team,
                "matches": m,
                "wins": w,
                "draws": d,
                "losses": l,
                "goals": g,
                "goals_against": ga,
                "points": pts,
                "xG": round_value(xg),
                "npxG": round_value(npxg),
                "xGA": round_value(xga),
                "npxGA": round_value(npxga),
                "npxGD": round_value(npxgd),
                "PPDA": round_value(ppda),
                "OPPDA": round_value(oppda),
                "deep_completions": dc,
                "deep_completions_allowed": odc,
                "xPTS": round_value(xpts),
                "xPTS_gap": round_value(pts - xpts),
                "g_minus_xg": round_value(g - xg),
                "xga_minus_ga": round_value(xga - ga),
                "gd": g - ga,
                "xgd": round_value(xg - xga),
                "xg_per_game": round_value(xg / m if m else 0),
                "xga_per_game": round_value(xga / m if m else 0),
                "pts_per_game": round_value(pts / m if m else 0),
                "xpts_per_game": round_value(xpts / m if m else 0),
            }
        )
    return rows


def league_is_lying(table: list) -> dict:
    """xPTS gap for every team — the canonical 'table is lying' dashboard."""
    full_table = league_table_full(table)
    sorted_rows = sorted(full_table, key=lambda item: item["xPTS_gap"], reverse=True)
    overperformer = sorted_rows[0] if sorted_rows else None
    underperformer = sorted_rows[-1] if sorted_rows else None
    return {
        "rows": sorted_rows,
        "table_order_rows": full_table,
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
        "table": league_table_full(table),
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
