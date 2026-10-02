"""Build tiny raw WhoScored match documents from simple event specs, so definitions can be tested without a browser or a website.

``match(...)`` returns a document shaped like WhoScored's ``matchCentreData`` (just the parts the pipeline reads), ``counters(...)`` runs
it through silver and gold and returns each player's counters. Everything is plain data; nothing here touches the network.
"""

from __future__ import annotations

from app.events import counters as C
from app.events import schema as S
from app.events import silver as SV

HOME, AWAY = 1, 2


def q(name: str, value=None) -> dict:
    out = {"type": {"displayName": name, "value": 1}}
    if value is not None:
        out["value"] = str(value)
    return out


def ev(kind: str, pid: int | None = None, *, team: int = HOME, x: float | None = 50.0, y: float | None = 50.0, end_x: float | None = None, end_y: float | None = None,
       minute: int = 10, second: int = 0, outcome: int = 1, quals=(), period: int = 1, touch: bool = True, eid: int | None = None, **extra) -> dict:
    """One raw event. ``quals`` are qualifier names, or ``(name, value)`` pairs for valued qualifiers."""
    out = {
        "eventId": eid if eid is not None else 0, "id": 0, "type": {"displayName": kind, "value": S.EVENT[kind]}, "outcomeType": {"displayName": "Successful" if outcome else "Unsuccessful", "value": outcome},
        "teamId": team, "minute": minute, "second": second, "expandedMinute": minute, "period": {"displayName": {1: "FirstHalf", 2: "SecondHalf", 14: "PostGame", 16: "PreMatch"}[period], "value": period},
        "isTouch": touch, "qualifiers": [q(*(n if isinstance(n, tuple) else (n,))) for n in quals],
    }
    if x is not None:
        out["x"] = x
    if y is not None:
        out["y"] = y
    if pid is not None:
        out["playerId"] = pid
    if end_x is not None:
        out["endX"] = end_x
    if end_y is not None:
        out["endY"] = end_y
    out.update(extra)
    return out


def end(minute: int = 100) -> dict:
    return ev("End", None, x=None, y=None, minute=minute, period=2, touch=False)


def player(pid: int, *, team_side: str = "home", start: bool = True, position: str = "MC", name: str | None = None, **extra) -> dict:
    return {"playerId": pid, "name": name or f"Player {pid}", "position": position if start else "Sub", "isFirstEleven": start, "shirtNo": pid % 99, "age": 25, "height": 180,
            "weight": 75, "isManOfTheMatch": False, "stats": {"ratings": {"90": 6.5}}, "field": team_side, **extra}


def match(events: list[dict], *, home_players=(), away_players=(), score="1 : 0", home="Reds", away="Blues", manager=("Boss", "Gaffer")) -> dict:
    """A raw match document. Event ids are numbered in order so related events can refer to each other."""
    numbered = []
    for i, e in enumerate(events, start=1):
        numbered.append({**e, "eventId": e["eventId"] or i, "id": 1000 + i})
    return {
        "events": numbered, "score": score, "ftScore": score, "htScore": "0 : 0", "startTime": "2025-08-16T15:00:00", "venueName": "Ground", "attendance": 40000,
        "referee": {"name": "A. Ref"}, "elapsed": "FT", "maxMinute": 96, "periodEndMinutes": {"1": 47, "2": 96}, "playerIdNameDictionary": {},
        "home": {"teamId": HOME, "name": home, "managerName": manager[0], "averageAge": 26.0, "players": list(home_players), "formations": []},
        "away": {"teamId": AWAY, "name": away, "managerName": manager[1], "averageAge": 25.0, "players": list(away_players), "formations": []},
    }


def silver(events, **kw) -> SV.Match:
    return SV.Match(SV.parse_match(match(events, **kw), league="EPL", season=2025, game_id=9001))


def gold(events, **kw) -> dict:
    return C.derive_match(silver(events, **kw))


def counters(events, **kw) -> dict[int, dict]:
    """Each player's counters in the match."""
    return {r["id"]: r["c"] for r in gold(events, **kw)["players"]}
