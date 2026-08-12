from __future__ import annotations

from .percentiles import to_float
from ._shared import HONEST_MATCH_LIMITATIONS, round_value


def _shots_for(team_shots_dict: dict, side: str) -> list[dict]:
    return list(team_shots_dict.get(side, []))


def calibration(match_shots: dict) -> dict:
    """xG vs actual goals for both sides — bare-min 'did the score flatter?' read."""
    h_shots = _shots_for(match_shots, "h")
    a_shots = _shots_for(match_shots, "a")
    h_xg = sum(to_float(s.get("xG", 0)) for s in h_shots)
    a_xg = sum(to_float(s.get("xG", 0)) for s in a_shots)
    h_goals_from_shots = sum(1 for s in h_shots if s.get("result") == "Goal")
    a_goals_from_shots = sum(1 for s in a_shots if s.get("result") == "Goal")
    goals_from_match_shots = {
        "h": h_goals_from_shots,
        "a": a_goals_from_shots,
    }
    return {
        "xG": {"h": round_value(h_xg), "a": round_value(a_xg)},
        "goals_from_shots": goals_from_match_shots,
        "g_minus_xg": {"h": round_value(h_goals_from_shots - h_xg), "a": round_value(a_goals_from_shots - a_xg)},
        "interpretation": (
            "xG is sum over shots. Goals from shots may differ from official match goals if "
            "any goal was an own goal (not attributed to a bellicose shot). Use this class to "
            "rank which side 'deserved' from chances — but caveat: includes GK quality."
        ),
        "limitations": HONEST_MATCH_LIMITATIONS,
    }


def big_chance_inventory(match_shots: dict, xg_threshold: float = 0.20) -> dict:
    """Shots above an xG threshold. The xG >= 0.20 threshold is a disclosed heuristic; Understat exposes no official 'big chance' flag."""
    h_shots = _shots_for(match_shots, "h")
    a_shots = _shots_for(match_shots, "a")
    inventory_h = [_big_shot(s) for s in h_shots if to_float(s.get("xG", 0)) >= xg_threshold]
    inventory_a = [_big_shot(s) for s in a_shots if to_float(s.get("xG", 0)) >= xg_threshold]
    return {
        "xG_threshold": xg_threshold,
        "threshold_note": "Disclosed heuristic. Understat exposes no official 'big chance' flag.",
        "home": sorted(inventory_h, key=lambda i: -i["xG"]),
        "away": sorted(inventory_a, key=lambda i: -i["xG"]),
    }


def _big_shot(s: dict) -> dict:
    return {
        "minute": s.get("minute"),
        "xG": round_value(to_float(s.get("xG", 0))),
        "result": s.get("result"),
        "situation": s.get("situation"),
        "shotType": s.get("shotType"),
        "lastAction": s.get("lastAction"),
        "player": s.get("player"),
        "X": to_float(s.get("X", 0)),
        "Y": to_float(s.get("Y", 0)),
    }


def situation_breakdown(match_shots: dict) -> dict:
    h_shots = _shots_for(match_shots, "h")
    a_shots = _shots_for(match_shots, "a")
    return {
        "home": _by_situation(h_shots),
        "away": _by_situation(a_shots),
    }


def _by_situation(shots: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for s in shots:
        situation = s.get("situation", "Unknown")
        slot = out.setdefault(situation, {"shots": 0, "xG": 0.0, "goals": 0})
        slot["shots"] += 1
        slot["xG"] = round_value(slot["xG"] + to_float(s.get("xG", 0)))
        if s.get("result") == "Goal":
            slot["goals"] += 1
    return out


def shot_map(match_shots: dict) -> dict:
    """Pitch-normalized shot coordinates + xG for front-end plotting."""
    h = [_shot_point(s, "h") for s in _shots_for(match_shots, "h")]
    a = [_shot_point(s, "a") for s in _shots_for(match_shots, "a")]
    return {
        "home": h,
        "away": a,
        "coordinate_note": "X,Y are Understat's 0-1 normalized shot end-coordinates (orientation: defending goal at left).",
        "limitations": HONEST_MATCH_LIMITATIONS,
    }


def _shot_point(s: dict, side: str) -> dict:
    return {
        "side": side,
        "minute": s.get("minute"),
        "xG": round_value(to_float(s.get("xG", 0))),
        "result": s.get("result"),
        "situation": s.get("situation"),
        "shotType": s.get("shotType"),
        "lastAction": s.get("lastAction"),
        "player": s.get("player"),
        "X": to_float(s.get("X", 0)),
        "Y": to_float(s.get("Y", 0)),
    }


def xg_timeline(match_shots: dict) -> dict:
    """Cumulative xG by team over minute — the classic xG race narrative chart."""
    h = sorted(_shots_for(match_shots, "h"), key=lambda s: _minute(s))
    a = sorted(_shots_for(match_shots, "a"), key=lambda s: _minute(s))
    cum_h = _cumulative(h)
    cum_a = _cumulative(a)
    return {
        "home": cum_h,
        "away": cum_a,
    }


def _minute(s: dict) -> int:
    try:
        return int(s.get("minute", 0))
    except (TypeError, ValueError):
        return 0


def _cumulative(shots: list[dict]) -> list[dict]:
    total = 0.0
    out = []
    for s in shots:
        total += to_float(s.get("xG", 0))
        out.append({"minute": _minute(s), "cumulative_xG": round_value(total)})
    return out


def match_narrative(match_meta: dict, match_shots: dict) -> dict:
    """Plain-English narrative read of the match using xG-vs-actual and shots."""
    calib = calibration(match_shots)
    h_xg = calib["xG"]["h"]
    a_xg = calib["xG"]["a"]
    h_goals = calib["goals_from_shots"]["h"]
    a_goals = calib["goals_from_shots"]["a"]
    home_team = match_meta.get("h", "?")
    away_team = match_meta.get("a", "?")

    narrative = f"{home_team} {h_goals}-{a_goals} {away_team}"
    if h_xg + a_xg > 0:
        if h_xg > a_xg and h_goals < a_goals:
            narrative += f": {home_team} out-xG'd {away_team} {h_xg:.2f}-{a_xg:.2f} but lost on the scoreboard."
        elif a_xg > h_xg and a_goals < h_goals:
            narrative += f": {away_team} out-xG'd {home_team} {a_xg:.2f}-{h_xg:.2f} but lost on the scoreboard."
        elif h_xg > a_xg and h_goals > a_goals:
            narrative += f": {home_team} won both xG ({h_xg:.2f}-{a_xg:.2f}) and the scoreline."
        elif a_xg > h_xg and a_goals > h_goals:
            narrative += f": {away_team} won both xG ({a_xg:.2f}-{h_xg:.2f}) and the scoreline."
        else:
            narrative += f": xG {h_xg:.2f}-{a_xg:.2f}, decisive on the scoreboard."
    return {
        "narrative": narrative,
        "scoreline": {"h": h_goals, "a": a_goals},
        "xG": {"h": h_xg, "a": a_xg},
    }


def match_report(match_meta: dict, match_shots: dict) -> dict:
    return {
        "calibration": calibration(match_shots),
        "big_chance_inventory": big_chance_inventory(match_shots),
        "situation_breakdown": situation_breakdown(match_shots),
        "shot_map": shot_map(match_shots),
        "xg_timeline": xg_timeline(match_shots),
        "narrative": match_narrative(match_meta, match_shots),
        "limitations": HONEST_MATCH_LIMITATIONS,
    }
