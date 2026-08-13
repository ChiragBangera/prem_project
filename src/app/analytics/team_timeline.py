from __future__ import annotations

"""Team timeline: a season (or two) at monthly grain.

Every Understat team-history metric is aggregated per calendar month so a
team's trajectory is readable: form, pressing intensity, penetration, and the
luck gap all on one time axis. Months carry the matches actually played that
month (fixture congestion differs), so per-game derived columns are the honest
comparison across months.
"""

from ._shared import round_value
from .percentiles import to_float


def team_timeline(
    history_by_season: dict[int, list[dict]],
    team_name: str,
    league_name: str,
) -> dict:
    seasons = []
    for season in sorted(history_by_season):
        matches = _as_rows(history_by_season[season])
        seasons.append(
            {
                "season": season,
                "months": _monthly_rows(matches),
                "n_matches": len(matches),
            }
        )

    return {
        "team_name": team_name,
        "league_name": league_name,
        "seasons": seasons,
        "interpretation": (
            f"Monthly view of {team_name}'s league seasons. Compare xG/game vs xGA/game "
            "for the quality trend, PPDA for pressing intensity, G − xG per month for "
            "luck swings. Months are not equal (fixtures differ), so per-game columns "
            "are the fair basis for comparison."
        ),
        "limitations": [
            "Monthly buckets are small samples — a single 5-0 can dominate one month's xG.",
            "PPDA is game-state dependent: teams leading sit deeper and press less.",
            "Understat xG is model-derived; monthly differences inside ~0.3 xG/game are noise.",
            "Only league matches; cups and continental games are not in this dataset.",
        ],
    }


def _monthly_rows(matches: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for match in matches:
        date = (match.get("date") or "")[:10]
        month = date[:7] if len(date) >= 7 else "unknown"
        buckets.setdefault(month, []).append(match)

    rows = []
    for month in sorted(buckets):
        bucket = buckets[month]
        n = len(bucket)
        rows.append(
            {
                "month": month,
                "matches": n,
                "wins": sum(to_float(m.get("wins")) for m in bucket),
                "draws": sum(to_float(m.get("draws")) for m in bucket),
                "loses": sum(to_float(m.get("loses")) for m in bucket),
                "points": sum(to_float(m.get("pts")) for m in bucket),
                "points_per_game": round_value(sum(to_float(m.get("pts")) for m in bucket) / n, 2),
                "goals": sum(to_float(m.get("scored")) for m in bucket),
                "xG": round_value(sum(to_float(m.get("xG")) for m in bucket), 2),
                "goals_against": sum(to_float(m.get("missed")) for m in bucket),
                "xGA": round_value(sum(to_float(m.get("xGA")) for m in bucket), 2),
                "xG_per_game": round_value(sum(to_float(m.get("xG")) for m in bucket) / n, 3),
                "xGA_per_game": round_value(sum(to_float(m.get("xGA")) for m in bucket) / n, 3),
                "npxGD_per_game": round_value(sum(to_float(m.get("npxGD")) for m in bucket) / n, 3),
                "g_minus_xg": round_value(
                    sum(to_float(m.get("scored")) for m in bucket)
                    - sum(to_float(m.get("xG")) for m in bucket),
                    2,
                ),
                "xpts": round_value(sum(to_float(m.get("xpts")) for m in bucket), 2),
                "ppda": _ppda_average(bucket, "ppda"),
                "oppda": _ppda_average(bucket, "ppda_allowed"),
                "deep": sum(to_float(m.get("deep")) for m in bucket),
                "deep_allowed": sum(to_float(m.get("deep_allowed")) for m in bucket),
            }
        )
    return rows


def _ppda_average(bucket: list[dict], key: str) -> float:
    total_att = sum(to_float((m.get(key) or {}).get("att")) for m in bucket)
    total_def = sum(to_float((m.get(key) or {}).get("def")) for m in bucket)
    if total_def <= 0:
        return 0.0
    return round_value(total_att / total_def, 2)


def _as_rows(history) -> list[dict]:
    if isinstance(history, dict):
        return list(history.values())
    return list(history or [])
