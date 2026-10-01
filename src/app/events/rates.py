"""From summed event counts to the numbers shown in the app.

Every rate is per 90 minutes of playing time, every ratio is a share of attempts. Ranking uses shrunk values
(a few attempts or minutes are pulled toward the role average) exactly as the Understat metrics do, so a
cameo cannot top a leaderboard.
"""

from __future__ import annotations

from app.stats import per90, safe_div

EVENT_SHRINK_MINUTES = 360.0  # counting stats settle faster than xG, so a shorter prior than the Understat rates' 720

# ratio metric -> (numerator, denominator, prior attempts)
RATIOS: dict[str, tuple[str, str, float]] = {
    "fwd_pass_ratio": ("fwd", "passes", 60.0),
    "pass_acc": ("pass_ok", "passes", 60.0),
    "def_duel_win": ("def_won", "def_duels", 15.0),
    "aerial_win": ("aer_won", "aer", 10.0),
}
# per-90 metric -> the count it is made from
PER90: dict[str, str] = {
    "passes90": "passes", "prog_passes90": "prog", "def_duels90": "def_duels",
    "tackles90": "tackles", "interceptions90": "int", "recoveries90": "rec",
}
EVENT_KEYS = tuple(RATIOS) + tuple(PER90)


def with_duels(t: dict) -> dict:
    """The counts plus the two derived duel totals (a tackle or a won aerial wins a duel; a challenge or a lost aerial loses it)."""
    out = dict(t)
    out["def_duels"] = t.get("tackles", 0) + t.get("challenges", 0) + t.get("aer_def", 0)
    out["def_won"] = t.get("tackles", 0) + t.get("aer_def_won", 0)
    return out


def event_rates(t: dict) -> dict[str, float | None]:
    """The raw (unshrunk) metrics for one player's totals; a ratio with no attempts is None."""
    t = with_duels(t)
    minutes = t.get("min", 0.0)
    out: dict[str, float | None] = {k: per90(t[src], minutes) if minutes > 0 else None for k, src in PER90.items()}
    for key, (num, den, _prior) in RATIOS.items():
        out[key] = safe_div(t[num], t[den]) if t[den] > 0 else None
    return out


def merge_totals(parts: list[dict]) -> dict:
    """Add several seasons' totals for the same player."""
    out: dict = {}
    for p in parts:
        if not out:
            out = {**p, "teams": dict(p.get("teams", {}))}
            continue
        for k, v in p.items():
            if k in ("id", "name"):
                continue
            if k == "teams":
                for team, minutes in v.items():
                    out["teams"][team] = round(out["teams"].get(team, 0.0) + minutes, 1)
            elif isinstance(v, (int, float)):
                out[k] = out.get(k, 0) + v
    out["min"] = round(out.get("min", 0.0), 1)
    return out
