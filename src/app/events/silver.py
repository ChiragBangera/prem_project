"""Silver layer: one raw WhoScored match -> a compact, typed, columnar document that everything else reads.

The raw page is ~1.1 MB of nested JSON. This turns it into

* ``info``    the match facts (kick-off, score, venue, referee, attendance, how long it ran),
* ``teams``   both sides (home first) with manager, average age and the formations they played,
* ``players`` everyone in the squad: lineup position, shirt, age, height, rating, and when he came on and went off,
* ``ev``      the events as parallel arrays (one entry per event in every array), coordinates in tenths of a pitch unit,
              qualifiers as two bit-words (see :mod:`app.events.schema`), related events resolved to array positions.

It is a pure function of the raw document and ``SILVER_VERSION``: no network, no clock, no randomness. Change a definition,
bump the version, and the store rebuilds silver from bronze offline.
"""

from __future__ import annotations

from typing import Any

from . import schema as S

SILVER_KIND = "ws_silver"
SILVER_VERSION = 1

# ``ev`` columns, in the order they are documented. Every array has the same length.
COLUMNS = (
    "eid",   # WhoScored's event id (unique per team within a match)
    "t",     # event type id (schema.EVENT)
    "o",     # outcome: 1 successful, 0 unsuccessful
    "tm",    # team: 0 home, 1 away
    "p",     # player id (0 = none)
    "pe",    # period id (1, 2 = play; 14 post-game; 16 pre-match)
    "mi",    # minute of the match, stoppage time ignored
    "se",    # second
    "em",    # expanded minute (the continuous clock: a full match runs to ~100)
    "x", "y", "ex", "ey",  # start and end position, tenths of a pitch unit (0..1000), -1 when absent
    "q0", "q1",            # qualifier flag words
    "ln",    # pass length, tenths of a metre, -1 when absent
    "an",    # pass angle, hundredths of a radian, -1 when absent
    "gy", "gz",  # where a shot was aimed in the goal mouth (tenths), -1 when absent
    "bx", "by",  # where a shot was blocked (tenths), -1 when absent
    "z",     # WhoScored's own zone of the pitch: 0 none, 1 back, 2 left, 3 centre, 4 right
    "rs",    # array position of the related event of the same team (e.g. a goal's assisting pass), -1 when none
    "ro",    # array position of the related event of the opposing team (e.g. the shot a save was made from), -1 when none
    "rp",    # related player id (the player a substitute replaced, ...), 0 when none
    "fl",    # bit 0 touch, bit 1 shot, bit 2 goal, bit 3 own goal
    "ct",    # card type: 0 none, 1 yellow, 2 red, 3 second yellow
)
FL_TOUCH, FL_SHOT, FL_GOAL, FL_OWN_GOAL = 1, 2, 4, 8
PERIOD_RANK = {16: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 14: 9}


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _tenths(value: Any) -> int:
    v = _num(value)
    return -1 if v is None else int(round(v * 10))


def _int(value: Any, default: int = 0) -> int:
    v = _num(value)
    return default if v is None else int(v)


def _score(text: Any) -> list[int] | None:
    try:
        a, b = str(text).split(":")
        return [int(a), int(b)]
    except (ValueError, TypeError):
        return None


def _final_rating(player: dict) -> float | None:
    ratings = (player.get("stats") or {}).get("ratings") or {}
    if not ratings:
        return None
    try:
        last = max(ratings, key=lambda k: int(k))
    except ValueError:
        return None
    value = _num(ratings[last])
    return None if value is None else round(value, 2)


def _formations(side: dict) -> list[dict]:
    out = []
    for f in side.get("formations") or []:
        slots = f.get("formationSlots") or []
        ids = f.get("playerIds") or []
        on_pitch = [pid for pid, slot in zip(ids, slots) if slot]
        pos = [[p.get("horizontal"), p.get("vertical")] for p in (f.get("formationPositions") or [])]
        out.append({
            "name": f.get("formationName") or "", "start": _int(f.get("startMinuteExpanded")), "end": _int(f.get("endMinuteExpanded")),
            "players": on_pitch, "positions": pos[: len(on_pitch)], "captain": f.get("captainPlayerId"),
        })
    return out


def _event_flags(qualifiers: list[dict]) -> tuple[int, int, dict[str, Any]]:
    """(low flag word, high flag word, the valued qualifiers by name)."""
    lo = hi = 0
    values: dict[str, Any] = {}
    for q in qualifiers or []:
        try:
            name = q["type"]["displayName"]
        except (KeyError, TypeError):
            continue
        bit = S.FLAG_BIT.get(name)
        if bit is not None:
            if bit < S.WORD_BITS:
                lo |= 1 << bit
            else:
                hi |= 1 << (bit - S.WORD_BITS)
        elif name in S.VALUE_QUALIFIERS:
            values[name] = q.get("value")
    return lo, hi, values


def parse_match(raw: dict, *, league: str = "", season: int = 0, game_id: int = 0) -> dict | None:
    """The silver document for one raw match, or None if the document is not a usable match."""
    if not isinstance(raw, dict) or not isinstance(raw.get("events"), list) or not raw["events"]:
        return None
    sides = [raw.get("home") or {}, raw.get("away") or {}]
    if not all(s.get("teamId") is not None for s in sides):
        return None
    team_index = {int(s["teamId"]): i for i, s in enumerate(sides)}
    names = {int(k): v for k, v in (raw.get("playerIdNameDictionary") or {}).items()}

    # ---- events, in play order (the raw list is already chronological; the sort only settles pre-match / post-game rows)
    ordered = sorted(enumerate(raw["events"]), key=lambda pair: (PERIOD_RANK.get(_int((pair[1].get("period") or {}).get("value"), 99), 99), pair[0]))
    events = [e for _i, e in ordered]
    n = len(events)
    cols: dict[str, list] = {c: [0] * n for c in COLUMNS}
    by_team_eid: dict[tuple[int, int], int] = {}
    types_seen: dict[int, str] = {}
    unknown_flags: set[str] = set()
    related: list[tuple[int, int | None, int | None]] = []
    for i, e in enumerate(events):
        t = e.get("type") or {}
        code = _int(t.get("value"))
        types_seen[code] = t.get("displayName") or S.EVENT_NAME.get(code, str(code))
        team = team_index.get(_int(e.get("teamId"), -1), 0)
        lo, hi, vals = _event_flags(e.get("qualifiers") or [])
        for q in e.get("qualifiers") or []:
            nm = (q.get("type") or {}).get("displayName")
            if nm and nm not in S.FLAG_BIT and nm not in S.VALUE_QUALIFIERS and nm not in S.IGNORED_QUALIFIERS:
                unknown_flags.add(nm)
        fl = (FL_TOUCH if e.get("isTouch") else 0) | (FL_SHOT if e.get("isShot") else 0) | (FL_GOAL if e.get("isGoal") else 0) | (FL_OWN_GOAL if e.get("isOwnGoal") else 0)
        card = S.CARD_CODE.get(((e.get("cardType") or {}).get("displayName")) or "", 0)
        cols["eid"][i] = _int(e.get("eventId"), -1)
        cols["t"][i] = code
        cols["o"][i] = 1 if (e.get("outcomeType") or {}).get("value") == 1 else 0
        cols["tm"][i] = team
        cols["p"][i] = _int(e.get("playerId"))
        cols["pe"][i] = _int((e.get("period") or {}).get("value"))
        cols["mi"][i] = _int(e.get("minute"))
        cols["se"][i] = _int(e.get("second"))
        cols["em"][i] = _int(e.get("expandedMinute"), _int(e.get("minute")))
        cols["x"][i], cols["y"][i] = _tenths(e.get("x")), _tenths(e.get("y"))
        cols["ex"][i] = _tenths(e.get("endX") if e.get("endX") is not None else vals.get("PassEndX"))
        cols["ey"][i] = _tenths(e.get("endY") if e.get("endY") is not None else vals.get("PassEndY"))
        cols["q0"][i], cols["q1"][i] = lo, hi
        cols["ln"][i] = _tenths(vals.get("Length"))
        ang = _num(vals.get("Angle"))
        cols["an"][i] = -1 if ang is None else int(round(ang * 100))
        cols["gy"][i] = _tenths(e.get("goalMouthY") if e.get("goalMouthY") is not None else vals.get("GoalMouthY"))
        cols["gz"][i] = _tenths(e.get("goalMouthZ") if e.get("goalMouthZ") is not None else vals.get("GoalMouthZ"))
        cols["bx"][i] = _tenths(e.get("blockedX") if e.get("blockedX") is not None else vals.get("BlockedX"))
        cols["by"][i] = _tenths(e.get("blockedY") if e.get("blockedY") is not None else vals.get("BlockedY"))
        cols["z"][i] = S.ZONE_CODE.get(str(vals.get("Zone") or ""), 0)
        cols["rp"][i] = _int(e.get("relatedPlayerId"))
        cols["fl"][i] = fl
        cols["ct"][i] = card
        eid = cols["eid"][i]
        if eid >= 0:
            by_team_eid.setdefault((team, eid), i)  # the first event with an id wins: a goal and its shot-assist share nothing
        related.append((i, _int(vals.get("RelatedEventId"), -1) if vals.get("RelatedEventId") is not None else None,
                        _int(vals.get("OppositeRelatedEvent"), -1) if vals.get("OppositeRelatedEvent") is not None else None))
        cols["rs"][i] = cols["ro"][i] = -1
    for i, same, opposite in related:
        team = cols["tm"][i]
        if same is not None and same >= 0:
            cols["rs"][i] = by_team_eid.get((team, same), -1)
        if opposite is not None and opposite >= 0:
            cols["ro"][i] = by_team_eid.get((1 - team, opposite), -1)

    # ---- timing: a player is on from the whistle (starter) or from the minute he came on, until he goes off or is sent off
    play = [i for i in range(n) if cols["pe"][i] in S.PLAY_PERIODS]
    full_time = max((cols["em"][i] for i in play), default=0)
    on_at: dict[int, int] = {}
    off_at: dict[int, int] = {}
    red_at: dict[int, int] = {}
    for i in play:
        pid, code = cols["p"][i], cols["t"][i]
        if not pid:
            continue
        if code == S.E_SUB_ON:
            on_at[pid] = cols["em"][i]
        elif code == S.E_SUB_OFF:
            off_at[pid] = cols["em"][i]
        elif code == S.E_CARD and cols["ct"][i] in (S.CARD_RED, S.CARD_SECOND_YELLOW):
            red_at[pid] = min(red_at.get(pid, full_time), cols["em"][i])

    # ---- teams and players
    teams, players = [], []
    for idx, side in enumerate(sides):
        teams.append({
            "id": _int(side.get("teamId")), "name": side.get("name") or "", "side": "h" if idx == 0 else "a", "manager": side.get("managerName") or None,
            "avg_age": _num(side.get("averageAge")), "formations": _formations(side),
        })
        for p in side.get("players") or []:
            pid = _int(p.get("playerId"))
            if not pid:
                continue
            started = bool(p.get("isFirstEleven"))
            came_on = pid in on_at or p.get("subbedInExpandedMinute") is not None
            players.append({
                "id": pid, "name": p.get("name") or names.get(pid, ""), "tm": idx, "pos": p.get("position") or "", "shirt": _int(p.get("shirtNo"), 0) or None,
                "age": _int(p.get("age"), 0) or None, "height": _int(p.get("height"), 0) or None, "weight": _int(p.get("weight"), 0) or None,
                "start": started, "motm": bool(p.get("isManOfTheMatch")), "rating": _final_rating(p),
                "on": 0 if started else (on_at.get(pid, _int(p.get("subbedInExpandedMinute"), -1)) if came_on else None),
                "off": off_at.get(pid, _int(p.get("subbedOutExpandedMinute"), -1) if p.get("subbedOutExpandedMinute") is not None else None),
                "red": red_at.get(pid),
            })
    known = {p["id"] for p in players}
    for pid in sorted({cols["p"][i] for i in play if cols["p"][i]} - known):  # on the pitch but not in a lineup: keep him so nothing is anonymous
        team = next((cols["tm"][i] for i in play if cols["p"][i] == pid), 0)
        players.append({"id": pid, "name": names.get(pid, ""), "tm": team, "pos": "", "shirt": None, "age": None, "height": None, "weight": None,
                        "start": pid not in on_at, "motm": False, "rating": None, "on": 0 if pid not in on_at else on_at[pid], "off": off_at.get(pid), "red": red_at.get(pid)})

    ft, ht, et = _score(raw.get("ftScore") or raw.get("score")), _score(raw.get("htScore")), _score(raw.get("etScore"))
    referee = raw.get("referee") or {}
    info = {
        "start": str(raw.get("startTime") or raw.get("startDate") or ""), "ft": ft, "ht": ht, "et": et, "status": raw.get("elapsed") or "",
        "venue": raw.get("venueName") or None, "attendance": _int(raw.get("attendance"), 0) or None, "referee": referee.get("name") or None,
        "weather": raw.get("weatherCode"), "full_time": full_time, "max_minute": _int(raw.get("maxMinute"), 0),
        "period_end": {str(k): _int(v) for k, v in (raw.get("periodEndMinutes") or {}).items()},
    }
    return {
        "v": SILVER_VERSION, "league": league, "season": season, "game": int(game_id), "info": info, "teams": teams, "players": players,
        "types": {str(k): v for k, v in sorted(types_seen.items())}, "unknown": sorted(unknown_flags), "n": n, "ev": cols,
    }


# ------------------------------------------------------------------ reading it back


class Match:
    """A silver document with the small conveniences analytics need. Holds no copy: it reads the document's own arrays."""

    __slots__ = ("doc", "ev", "n", "info", "teams", "players", "by_id", "league", "season", "game")

    def __init__(self, doc: dict):
        self.doc = doc
        self.ev = doc["ev"]
        self.n = doc["n"]
        self.info = doc["info"]
        self.teams = doc["teams"]
        self.players = doc["players"]
        self.by_id = {p["id"]: p for p in self.players}
        self.league, self.season, self.game = doc.get("league", ""), doc.get("season", 0), doc.get("game", 0)

    def play_indices(self) -> list[int]:
        pe = self.ev["pe"]
        return [i for i in range(self.n) if pe[i] in S.PLAY_PERIODS]

    def has_flag(self, i: int, name: str) -> bool:
        bit = S.FLAG_BIT[name]
        word = self.ev["q0"][i] if bit < S.WORD_BITS else self.ev["q1"][i]
        return bool(word >> (bit if bit < S.WORD_BITS else bit - S.WORD_BITS) & 1)

    def flags_at(self, i: int) -> set[str]:
        return {name for name in S.FLAGS if self.has_flag(i, name)}

    def coords(self, i: int) -> tuple[float | None, float | None, float | None, float | None]:
        ev = self.ev
        f = lambda v: None if v < 0 else v / 10.0  # noqa: E731
        return f(ev["x"][i]), f(ev["y"][i]), f(ev["ex"][i]), f(ev["ey"][i])

    def row(self, i: int) -> dict:
        """One event as a readable dict (for tests and debugging; analytics read the arrays)."""
        x, y, ex, ey = self.coords(i)
        ev = self.ev
        return {"type": self.doc["types"].get(str(ev["t"][i]), str(ev["t"][i])), "ok": bool(ev["o"][i]), "team": ev["tm"][i], "player": ev["p"][i],
                "minute": ev["mi"][i], "em": ev["em"][i], "x": x, "y": y, "ex": ex, "ey": ey, "flags": self.flags_at(i), "length": None if ev["ln"][i] < 0 else ev["ln"][i] / 10.0}
