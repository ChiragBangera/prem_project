"""Understat's match page, rebuilt from WhoScored's page, for a match Understat has not published yet.

Understat publishes a match (its shots, their xG, each player's line) only after the final whistle. WhoScored's match centre has the
match while it is being played, so the report can be drawn from it with everything WhoScored really records:

* every shot, at the spot WhoScored recorded (the same Opta point Understat uses: on finished matches half the shots sit exactly on
  Understat's), with its situation, body part, the action before it, and who assisted;
* each player's line: minutes (from the line-ups, substitutions and red cards, counted on a 90-minute match as Understat does), goals,
  own goals, shots, key passes, assists and cards.

Expected goals are **not** made up. WhoScored has none, and nothing else readable has them live (Sofascore refuses automated requests),
so xG, xA, xGChain and xGBuildup are left empty (NaN) until Understat publishes; the report says so instead of showing a zero.

A WhoScored player who cannot be linked to an Understat player gets a negative id (minus his WhoScored id): shown, never linked.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from app.data.models import MatchPage, RosterEntry, Shot

SHOT_TYPES = frozenset({"Goal", "SavedShot", "MissedShots", "ShotOnPost"})
NO_XG = math.nan
SITUATION = (("Penalty", "Penalty"), ("DirectFreekick", "DirectFreekick"), ("FromCorner", "FromCorner"), ("SetPiece", "SetPiece"), ("ThrowinSetPiece", "SetPiece"))
BODY = (("Head", "Head"), ("RightFoot", "RightFoot"), ("LeftFoot", "LeftFoot"), ("OtherBodyPart", "OtherBodyPart"))


def qualifiers(event: dict) -> set[str]:
    return {str((q.get("type") or {}).get("displayName")) for q in event.get("qualifiers") or []}


def is_shot(event: dict) -> bool:
    """A shot at goal (an own goal is recorded as a Goal by the player who put it in, and is not a shot)."""
    return (event.get("type") or {}).get("displayName") in SHOT_TYPES and "OwnGoal" not in qualifiers(event) and event.get("x") is not None


def score(doc: dict) -> tuple[int, int]:
    """The score WhoScored's page shows ("2 : 1")."""
    try:
        h, a = (int(x) for x in str(doc.get("score") or "0 : 0").split(":"))
        return h, a
    except ValueError:
        return 0, 0


def big_chances(doc: dict) -> dict[str, int]:
    """Big chances per side as Opta marks them (WhoScored's ``BigChance``): a real count, unlike Understat's, which is an xG threshold."""
    home_id = (doc.get("home") or {}).get("teamId")
    out = {"h": 0, "a": 0}
    for e in doc.get("events") or []:
        if is_shot(e) and "BigChance" in qualifiers(e):
            out["h" if e.get("teamId") == home_id else "a"] += 1
    return out


def _assist(event: dict, by_id: dict[tuple, dict]) -> dict | None:
    """The pass that set a shot up (WhoScored numbers each team's events on its own, so the shooter's team and the related id find it)."""
    related = next((q.get("value") for q in event.get("qualifiers") or [] if (q.get("type") or {}).get("displayName") == "RelatedEventId"), None)
    return by_id.get((event.get("teamId"), int(related))) if related is not None and str(related).isdigit() else None


def _last_action(assist: dict | None, quals: set[str]) -> str:
    if assist is None:
        return "Rebound" if "FirstTouch" in quals and "IndividualPlay" not in quals else "None"
    aq = qualifiers(assist)
    for name in ("Cross", "Throughball", "Chipped", "HeadPass"):
        if name in aq:
            return name
    if aq & {"CornerTaken", "FreekickTaken"}:
        return "Standard"
    return str((assist.get("type") or {}).get("displayName") or "Pass")


def live_match_page(doc: dict, *, match_id: int, season: int, home: str, away: str, date: str,
                    understat_id: Callable[[int], int | None] = lambda _ws: None) -> MatchPage:
    """``doc`` is WhoScored's page (read at half time, full time or in between); ``understat_id(WhoScored player id)`` links a player."""
    events = doc.get("events") or []
    by_id = {(e.get("teamId"), int(e["eventId"])): e for e in events if e.get("eventId") is not None}
    names = {int(k): v for k, v in (doc.get("playerIdNameDictionary") or {}).items() if str(k).isdigit()}
    home_id = (doc.get("home") or {}).get("teamId")

    def side_of(team) -> str:
        return "h" if team == home_id else "a"

    def pid(ws: int | None) -> int:
        if ws is None:
            return 0
        linked = understat_id(int(ws))
        return int(linked) if linked else -int(ws)

    def shot(e: dict, result: str, assisted_by: str | None, last_action: str) -> Shot:
        quals, ws = qualifiers(e), e.get("playerId")
        return Shot(
            id=int(e.get("id") or e.get("eventId") or 0), minute=int(e.get("minute") or 0), xg=NO_XG, result=result,
            x=float(e.get("x", 50.0)) / 100, y=float(e.get("y", 50.0)) / 100,
            situation=next((v for k, v in SITUATION if k in quals), "OpenPlay"), shot_type=next((v for k, v in BODY if k in quals), "OtherBodyPart"),
            last_action=last_action, player=names.get(int(ws), "") if ws is not None else "", player_id=pid(ws),
            venue=side_of(e.get("teamId")), season=season, match_id=match_id, home=home, away=away, date=date, assisted_by=assisted_by,
        )

    shots: dict[str, list[Shot]] = {"h": [], "a": []}
    line: dict[int, dict] = {}       # WhoScored player id -> his numbers

    def of(ws: int) -> dict:
        return line.setdefault(ws, {"goals": 0, "own_goals": 0, "shots": 0, "key_passes": 0, "assists": 0, "yellow": 0, "red": 0, "on": None, "off": None})

    last_minute = 0
    for e in events:
        kind = (e.get("type") or {}).get("displayName")
        quals = qualifiers(e)
        team, ws = e.get("teamId"), e.get("playerId")
        last_minute = max(last_minute, int(e.get("expandedMinute", e.get("minute")) or 0))
        if ws is None:
            continue
        clock = int(e.get("expandedMinute", e.get("minute")) or 0)   # Understat counts minutes on the clock that includes first-half stoppage
        if kind == "SubstitutionOn":
            of(int(ws))["on"] = clock
        elif kind == "SubstitutionOff":
            of(int(ws))["off"] = clock
        elif kind == "Card":
            if quals & {"Red", "SecondYellow"}:
                of(int(ws))["red"] += 1
                of(int(ws))["off"] = clock
            if quals & {"Yellow", "SecondYellow"}:
                of(int(ws))["yellow"] += 1
        if kind == "Goal" and "OwnGoal" in quals:                    # Understat lists an own goal among the shots of the player's side
            of(int(ws))["own_goals"] += 1
            shots[side_of(team)].append(shot(e, "OwnGoal", None, "None"))
            continue
        if not is_shot(e):
            continue
        assist = _assist(e, by_id)
        shooter = of(int(ws))
        shooter["shots"] += 1
        shooter["goals"] += kind == "Goal"
        passer = int(assist["playerId"]) if assist is not None and assist.get("playerId") is not None else None
        if passer is not None:
            of(passer)["key_passes"] += 1
            of(passer)["assists"] += kind == "Goal"
        result = "BlockedShot" if kind == "SavedShot" and "Blocked" in quals else str(kind)
        shots[side_of(team)].append(shot(e, result, names.get(passer) if passer is not None else None, _last_action(assist, quals)))

    end = min(max(last_minute + 1, 1), 90)   # Understat counts minutes on a 90-minute match: a starter who plays it all has 90
    rosters: dict[str, list[RosterEntry]] = {"h": [], "a": []}
    for side, key in (("h", "home"), ("a", "away")):
        for p in (doc.get(key) or {}).get("players") or []:
            ws = int(p["playerId"])
            n = line.get(ws) or of(ws)
            start = 0 if p.get("isFirstEleven") else n["on"]
            minutes = 0 if start is None else max(0, min(end, n["off"] if n["off"] is not None else end) - min(start, end))
            rosters[side].append(RosterEntry(
                player_id=pid(ws), player=p.get("name") or names.get(ws, ""), position=(p.get("position") or "Sub") if p.get("isFirstEleven") else "Sub",
                minutes=minutes, goals=n["goals"], own_goals=n["own_goals"], shots=n["shots"], xg=NO_XG, key_passes=n["key_passes"],
                assists=n["assists"], xa=NO_XG, xgchain=NO_XG, xgbuildup=NO_XG, yellow=n["yellow"], red=n["red"], venue=side,
            ))
    for side in shots:
        shots[side].sort(key=lambda s: (s.minute, s.id))
    return MatchPage(id=match_id, shots=shots, rosters=rosters)


def live_report(fixture, page: MatchPage, doc: dict) -> dict:
    """The match report (:func:`app.analytics.match.match_report`) for a page built from WhoScored, with nothing that needs xG made up.

    Every figure WhoScored records stays as the finished-match report has it. The ones that need xG are left empty (``None``) and
    ``has_xg`` is False, so the page shows the section and says xG comes from Understat after full time: the xG race, the xG split by
    player, the deserved result. "When the chances came" counts shots instead (``buckets.unit``), big chances are Opta's own count,
    and "the best chances" is every shot in the order it came.
    """
    import dataclasses

    from .match import BUCKETS, match_report

    zero = MatchPage(id=page.id, shots={side: [dataclasses.replace(s, xg=0.0) for s in page.shots[side]] for side in page.shots},
                     rosters={side: [dataclasses.replace(r, xg=0.0, xa=0.0, xgchain=0.0, xgbuildup=0.0) for r in page.rosters[side]] for side in page.rosters})
    report = match_report(fixture, zero)
    report["has_xg"] = False
    report["fixture"].update(hxg=None, axg=None)
    big = big_chances(doc)
    for side, key in (("home", "h"), ("away", "a")):
        report["summary"][side].update(xg=None, xg_per_shot=None, np_xg=None, big_chances=big[key])
        for row in report["situations"][side]:
            row["xg"] = None
        for player in report["players"][side]:
            player.update(xg=None, xa=None, xgchain=None, xgbuildup=None)
        for s in report["shots"][side]:
            s["xg"] = None
    report["deserved"] = None
    report["timeline"] = None
    counts = {side: [sum(1 for s in page.shots[key] if s.result != "OwnGoal" and lo <= s.minute <= hi) for lo, hi in BUCKETS]
              for side, key in (("home", "h"), ("away", "a"))}
    report["buckets"] = {**report["buckets"], "unit": "shots", **counts}
    report["key_chances"] = sorted(({**s, "side": side[0]} for side in ("home", "away") for s in report["shots"][side] if s["result"] != "OwnGoal"),
                                   key=lambda s: (s["minute"], s["id"]))
    return report
