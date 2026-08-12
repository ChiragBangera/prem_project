from __future__ import annotations

from .percentiles import to_float


HONEST_TEAM_LIMITATIONS = [
    "No event-level pass data: PPDA is the only pressing proxy; no pressure-events, no vertical pressure.",
    "Shot coordinates are end-location only; no defensive line height without tracking data.",
    "Single-match PPDA is noisy — compare to season baseline, not in isolation.",
    "deep_completions counts are aggregated only; no penetration map is possible.",
    "Understat `ppda` is game-state-dependent; teams chasing will look different to teams leading.",
    "No transition timing in seconds: `lastAction` is the only honest chance-type proxy.",
]


HONEST_LEAGUE_LIMITATIONS = [
    "Cross-league xG/xPTS absolute values depend on Understat's model (per-league vs pooled is undisclosed); interpret cross-league gaps cautiously.",
    "Finishing variance is luck + GK + model error; cannot be attributed to a single cause without post-shot xG.",
    "xPTS gaps are mean-reverting within-season — present as 'table is currently lying', not permanent truth.",
]


HONEST_MATCH_LIMITATIONS = [
    "Shot maps use end-coordinates; no ball path or GK position.",
    "xG-vs-actual calibration mixes striker finishing and GK shot-stopping; cannot split without post-shot xG.",
    "No game-state flags in the match payload; trailing teams that pump shots look artificially better on raw xG.",
    "Single-match PPDA is very noisy; season-level reads are more reliable.",
]


def round_value(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def ppda_ratio(ppda: dict) -> float:
    """Passes per defensive action; high = less intense press. Defensive actions -> 0 is missing data, return 0."""
    att = to_float(ppda.get("att", 0))
    defn = to_float(ppda.get("def", 0))
    if defn <= 0:
        return 0.0
    return round_value(att / defn)


def as_list_matches(rows) -> list[dict]:
    if isinstance(rows, dict):
        # Some upstream calls return a dict keyed by id; values are match dicts.
        return list(rows.values())
    return list(rows or [])
