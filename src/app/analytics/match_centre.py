"""The match centre: one match's event data, laid out for the browser to analyse.

A WhoScored match is ~1,500 events. This module turns the silver document (see :mod:`app.events.silver`) into small parallel rows the
Match page reads: every touch, pass, defensive action, carry, take-on and shot with its period, clock minute, position and player, the
goals, cards and substitutions in order, and both line-ups with their formation slots. The page then works out what it shows (momentum,
territory, pass networks, the numbers of one half) from these rows, so one half or one player can be picked without asking again.

``possessions`` cuts the same events into moves (see :mod:`app.events.possessions`): each move's steps in order, how it began and ended,
who lost the ball and who took it.

Nothing here is a model: it is selection. Two things are inferred, and say so where they are shown: a pass's receiver (the data has
none: it is the next team-mate to touch the ball within a few seconds) and carries (see :func:`app.events.counters.carries`).

**Coordinates**: tenths of a pitch unit (0-1000). x runs in the acting team's attacking direction (its own goal line at 0); y runs with
the team's left wing at 0, so every team attacks left to right with its left wing at the top, as on every other map in the app.

A match read before the final whistle (half time) gives the same document from what has been played so far.
"""

from __future__ import annotations

from app.events import counters as C
from app.events import schema as S
from app.events.maps import (D_AERIAL, D_BEATEN, D_BLOCK_PASS, D_BLOCK_SHOT, D_CLEAR, D_INTERCEPT, D_RECOVER, D_TACKLE,
                             PF_BOX, PF_CROSS, PF_F3, PF_KEY, PF_LONG, PF_PROG, PF_RESTART, PF_THROUGH)
from app.events.possessions import build_possessions, led_to_shot
from app.events.silver import FL_GOAL, FL_OWN_GOAL, FL_TOUCH, Match

CENTRE_VERSION = 3
RECEIVE_GAP_SECS = 8          # a pass reaches the next team-mate to touch the ball within this long
PF_ASSIST, PF_CORNER, PF_FREEKICK = 128, 512, 1024

DEF_KIND = {S.E_TACKLE: D_TACKLE, S.E_INTERCEPTION: D_INTERCEPT, S.E_CLEARANCE: D_CLEAR, S.E_BLOCKED_PASS: D_BLOCK_PASS,
            S.E_RECOVERY: D_RECOVER, S.E_CHALLENGE: D_BEATEN}
SHOT_RESULT = {S.E_GOAL: "Goal", S.E_SAVED: "SavedShot", S.E_MISS: "MissedShots", S.E_POST: "ShotOnPost"}
M_GOAL_ASSIST = C._mask("IntentionalGoalAssist")
M_FAST_BREAK, M_FROM_CORNER, M_SET_PIECE, M_THROW_SET = C._mask("FastBreak"), C._mask("FromCorner"), C._mask("SetPiece"), C._mask("ThrowinSetPiece")
M_RIGHT, M_LEFT, M_OWN_GOAL = C._mask("RightFoot"), C._mask("LeftFoot"), C._mask("OwnGoal")


def _situation(q: int) -> str:
    if q & C.M_PEN:
        return "Penalty"
    if q & C.M_DIRECT_FK:
        return "DirectFreekick"
    if q & M_FROM_CORNER:
        return "FromCorner"
    if q & (M_SET_PIECE | M_THROW_SET):
        return "SetPiece"
    return "FastBreak" if q & M_FAST_BREAK else "OpenPlay"


def _body(q: int) -> str:
    return "Head" if q & C.M_HEAD else "RightFoot" if q & M_RIGHT else "LeftFoot" if q & M_LEFT else "Other"


def _lineup(m: Match, tm: int) -> dict:
    """One side: its formation at kick-off (name and each starter's slot on a 0-10 grid), and everyone in the squad."""
    team = m.teams[tm]
    first = (team.get("formations") or [{}])[0]
    slot = {pid: pos for pid, pos in zip(first.get("players") or [], first.get("positions") or []) if pos and pos[0] is not None}
    players = []
    for p in m.players:
        if p["tm"] != tm:
            continue
        at = slot.get(p["id"])
        players.append({"id": p["id"], "name": p["name"], "shirt": p.get("shirt"), "pos": p.get("pos") or "", "start": bool(p.get("start")),
                        "on": p.get("on"), "off": p.get("off") if (p.get("off") or -1) >= 0 else None, "red": p.get("red"), "rating": p.get("rating"),
                        "motm": bool(p.get("motm")), "slot": [round(float(at[0]), 2), round(float(at[1]), 2)] if at else None})
    players.sort(key=lambda p: (not p["start"], p["on"] if p["on"] is not None else 999, p["shirt"] or 99))
    return {"name": team["name"], "manager": team.get("manager"), "formation": first.get("name") or None,
            "formations": [{"name": f.get("name"), "from": f.get("start"), "to": f.get("end")} for f in team.get("formations") or []],
            "captain": first.get("captain"), "players": players}


def build_centre(m: Match, *, final: bool, flip: bool = False) -> dict:
    """The match centre document of one silver match. ``flip`` swaps the sides (WhoScored listed the fixture's away team first)."""
    ev = m.ev
    side = (lambda tm: 1 - tm) if flip else (lambda tm: tm)
    play = m.play_indices()
    q = {i: ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS) for i in play}

    def xy(i: int) -> tuple[int, int]:
        return ev["x"][i], 1000 - ev["y"][i]

    touch_order = [i for i in play if ev["fl"][i] & FL_TOUCH and ev["x"][i] >= 0 and ev["p"][i]]
    position = {i: n for n, i in enumerate(touch_order)}

    def receiver(i: int) -> int:
        """Who a completed pass reached: the next team-mate to touch the ball, unless the other side got there first. 0 when unknown."""
        t0 = ev["mi"][i] * 60 + ev["se"][i]
        at = position.get(i)
        if at is None:
            return 0
        for j in touch_order[at + 1: at + 6]:
            if ev["pe"][j] != ev["pe"][i] or ev["mi"][j] * 60 + ev["se"][j] - t0 > RECEIVE_GAP_SECS or ev["tm"][j] != ev["tm"][i]:
                return 0
            if ev["p"][j] != ev["p"][i]:
                return ev["p"][j]
        return 0

    touches, passes, defs, takeons, timeline, fouls = [], [], [], [], [], []
    shots: list[dict] = []
    shot_at: dict[int, int] = {}                    # event index -> its place in ``shots``
    for i in play:
        code, ok, tm, pid, pe, em, mi = ev["t"][i], ev["o"][i], side(ev["tm"][i]), ev["p"][i], ev["pe"][i], ev["em"][i], ev["mi"][i]
        qq = q[i]
        has_xy = ev["x"][i] >= 0 and ev["y"][i] >= 0
        x, y = xy(i) if has_xy else (-1, -1)
        if ev["fl"][i] & FL_TOUCH and has_xy:
            touches.append([tm, pe, em, x, y, pid])
        if code == S.E_PASS and has_xy and ev["ex"][i] >= 0 and ev["ey"][i] >= 0:
            ex, ey = ev["ex"][i], 1000 - ev["ey"][i]
            restart = bool(qq & C.M_RESTART)
            flags = 0
            if ok and not restart and not qq & C.M_CROSS and (ev["ex"][i] - ev["x"][i]) / 10.0 >= S.PROGRESSIVE_MIN and ev["ex"][i] / 10.0 >= S.PROGRESSIVE_END_X:
                flags |= PF_PROG
            if qq & C.M_KEY:
                flags |= PF_KEY
            if S.in_box(ev["ex"][i] / 10.0, ev["ey"][i] / 10.0) and not S.in_box(ev["x"][i] / 10.0, ev["y"][i] / 10.0):
                flags |= PF_BOX
            if ev["x"][i] / 10.0 < S.FINAL_THIRD_X <= ev["ex"][i] / 10.0:
                flags |= PF_F3
            flags |= (PF_LONG if qq & C.M_LONG else 0) | (PF_CROSS if qq & C.M_CROSS else 0) | (PF_THROUGH if qq & C.M_THROUGH else 0)
            flags |= (PF_RESTART if restart else 0) | (PF_ASSIST if qq & M_GOAL_ASSIST else 0) | (PF_CORNER if qq & C.M_CORNER else 0) | (PF_FREEKICK if qq & C.M_FK else 0)
            passes.append([tm, pe, em, x, y, ex, ey, ok, flags, pid, receiver(i) if ok else 0])
        elif code in DEF_KIND and has_xy:
            defs.append([tm, pe, em, x, y, DEF_KIND[code], ok, pid])
        elif code == S.E_SAVE and qq & C.M_OUTFIELD_BLOCK and has_xy:
            defs.append([tm, pe, em, x, y, D_BLOCK_SHOT, ok, pid])
        elif code == S.E_AERIAL and has_xy:
            defs.append([tm, pe, em, x, y, D_AERIAL, ok, pid])
        elif code == S.E_TAKEON and has_xy:
            takeons.append([tm, pe, em, x, y, ok, pid])
        elif code == S.E_FOUL and has_xy and not ok:      # the foul committed (the same foul is also listed, as won, for the player fouled)
            fouls.append([tm, pe, em, x, y, pid])
        own_goal = bool(ev["fl"][i] & FL_OWN_GOAL) or bool(qq & M_OWN_GOAL)
        if code in S.SHOT_EVENTS and not own_goal and has_xy:
            result = "BlockedShot" if code == S.E_SAVED and qq & C.M_BLOCKED else SHOT_RESULT[code]
            assist = ev["p"][ev["rs"][i]] if ev["rs"][i] >= 0 and ev["t"][ev["rs"][i]] == S.E_PASS else 0
            shot_at[i] = len(shots)
            shots.append({"tm": tm, "pe": pe, "em": em, "mi": mi, "x": ev["x"][i], "y": 1000 - ev["y"][i], "result": result, "p": pid,
                          "situation": _situation(qq), "body": _body(qq), "big": bool(qq & C.M_BIGCH), "assist": assist,
                          "gy": ev["gy"][i] if ev["gy"][i] >= 0 else None, "gz": ev["gz"][i] if ev["gz"][i] >= 0 else None, "xg": None})
        if code == S.E_GOAL or (ev["fl"][i] & FL_GOAL and code in S.SHOT_EVENTS):
            assist = ev["p"][ev["rs"][i]] if ev["rs"][i] >= 0 and ev["t"][ev["rs"][i]] == S.E_PASS else 0
            timeline.append({"em": em, "mi": mi, "pe": pe, "kind": "own_goal" if own_goal else "penalty" if qq & C.M_PEN else "goal",
                             "tm": 1 - tm if own_goal else tm, "p": pid, "other": 0 if own_goal else assist})
        elif code == S.E_CARD and ev["ct"][i]:
            timeline.append({"em": em, "mi": mi, "pe": pe, "kind": "yellow" if ev["ct"][i] == S.CARD_YELLOW else "red", "tm": tm, "p": pid,
                             "other": 0, "second": ev["ct"][i] == S.CARD_SECOND_YELLOW})
        elif code == S.E_SUB_ON:
            timeline.append({"em": em, "mi": mi, "pe": pe, "kind": "sub", "tm": tm, "p": pid, "other": ev["rp"][i]})

    carries = [[side(t), ev["pe"][i], ev["em"][i], int(x0 * 10), 1000 - int(y0 * 10), int(x1 * 10), 1000 - int(y1 * 10),
                1 if (x1 - x0) >= S.PROGRESSIVE_MIN and x1 >= S.PROGRESSIVE_END_X else 0, pid] for pid, t, x0, y0, x1, y1, i in C.carries(m)]

    possessions = []
    moves = build_possessions(m)
    for move, led in zip(moves, led_to_shot(moves), strict=True):
        move["ls"] = led                              # it came to a shot: its own, or from the corner, free kick or penalty it won
        move["tm"] = side(move["tm"])
        move["si"] = shot_at.get(move.pop("shot"))
        del move["ix"]
        possessions.append(move)

    first = [ev["em"][i] for i in play if ev["pe"][i] == 1]
    second = [ev["em"][i] for i in play if ev["pe"][i] == 2]
    lineups = [_lineup(m, 0), _lineup(m, 1)]
    if flip:
        lineups.reverse()
    timeline.sort(key=lambda t: (t["em"], t["kind"] != "goal"))
    return {
        "v": CENTRE_VERSION, "available": True, "final": final,
        "clock": {"end": max(first + second, default=0), "ht": max(first, default=0), "second_from": min(second, default=None) if second else None,
                  "status": m.info.get("status") or ""},
        "info": {k: m.info.get(k) for k in ("venue", "attendance", "referee", "ht", "ft")},
        "teams": lineups, "names": {str(p["id"]): p["name"] for p in m.players},
        "timeline": timeline, "shots": shots, "touches": touches, "passes": passes, "def": defs, "takeons": takeons, "carries": carries, "fouls": fouls,
        "possessions": possessions,
    }


def attach_xg(centre: dict, understat_shots: dict[str, list]) -> None:
    """Give each shot Understat's xG, where Understat has the same shot: same side, the same minute (give or take one) and the nearest spot.

    Both sources draw on the same collected data, so most shots sit on the same point; a shot Understat does not list keeps ``xg: None``.
    ``understat_shots`` is ``{"h": [...], "a": [...]}`` of shots with ``minute``, ``x``, ``y`` (0-1) and ``xg``.
    """
    for tm, key in ((0, "h"), (1, "a")):
        pool = [s for s in understat_shots.get(key, []) if getattr(s, "result", None) != "OwnGoal"]
        used: set[int] = set()
        for shot in centre["shots"]:
            if shot["tm"] != tm:
                continue
            best, best_d = None, 0.0
            for n, s in enumerate(pool):
                if n in used or abs(int(s.minute) - shot["mi"]) > 1:
                    continue
                d = (float(s.x) - shot["x"] / 1000) ** 2 + (float(s.y) - (1 - shot["y"] / 1000)) ** 2
                if best is None or d < best_d:
                    best, best_d = n, d
            if best is not None and best_d <= 0.02:
                used.add(best)
                xg = float(pool[best].xg)
                shot["xg"] = None if xg != xg else round(xg, 3)
