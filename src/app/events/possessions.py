"""Possessions: a match cut into moves, each with its steps in order, how it began, how it ended, who lost it and who broke it up.

A **move** is a run of on-ball actions by one side. It ends when

- that side shoots (the shot is the last step; whatever follows is a new move),
- play stops: a foul either way, an offside, the ball out of play, the end of a half,
- or the other side **takes the ball**: a tackle won, an interception, a clearance, a blocked pass, a loose ball picked up, the keeper
  gathering it, or simply their next pass.

One thing does **not** end a move: a touch that leaves the ball with the same side. An opponent's stray touch (WhoScored's ``BallTouch``)
or a tackle that did not win the ball is only a deflection if the attacking side plays on; if the opponents play next, the move was
lost to that touch.

**Who lost it** is the last player of the move, unless that last action was a completed pass (the data has no receiver, so there is
nobody to name: it stays empty). **Who broke it** is the opponent whose action ended it. A ball played straight out has a loser and
nobody who broke it.

Nothing is estimated here except carries (see :func:`app.events.counters.carries`), which are drawn as such. Team totals in
:mod:`app.events.counters` (``seq_*``) still use the older, plainer rule (any touch by the other side ends a run); these rows are for
reading one match.

Coordinates are tenths of a pitch unit in the move's own direction, y with the left wing at 0 (as in :mod:`app.analytics.match_centre`).
"""

from __future__ import annotations

from app.events import counters as C
from app.events import schema as S
from app.events.silver import FL_OWN_GOAL, Match

K_PASS, K_CARRY, K_TAKEON, K_TOUCH, K_SHOT, K_WIN, K_CLEAR = 0, 1, 2, 3, 4, 5, 6
SF_CROSS, SF_LONG, SF_THROUGH, SF_KEY, SF_HEAD = 1, 2, 4, 8, 16     # what kind of pass a pass step was
SF_PROG = 32                                                        # a progressive pass or carry, by the counters' own rule

E_BALL_TOUCH, E_GOOD_SKILL, E_OFFSIDE_PASS = S.E_BALL_TOUCH, S.EVENT["GoodSkill"], S.EVENT["OffsidePass"]
STEP_KIND = {S.E_PASS: K_PASS, E_OFFSIDE_PASS: K_PASS, S.E_TAKEON: K_TAKEON, E_BALL_TOUCH: K_TOUCH, E_GOOD_SKILL: K_TOUCH,
             S.E_DISPOSSESSED: K_TOUCH, **dict.fromkeys(S.SHOT_EVENTS, K_SHOT)}
#: Actions that take the ball (when they succeed), and the word the page uses for each.
WIN_KIND = {S.E_TACKLE: "tackle", S.E_INTERCEPTION: "interception", S.E_RECOVERY: "recovery", S.E_BLOCKED_PASS: "blocked_pass",
            S.E_CLEARANCE: "clearance", S.E_CLAIM: "keeper", S.E_PICKUP: "keeper", S.E_SMOTHER: "keeper", S.E_SWEEPER: "keeper",
            S.E_PUNCH: "keeper", S.E_SAVE: "keeper"}
NEEDS_SUCCESS = frozenset({S.E_TACKLE, S.E_CLAIM, S.E_SWEEPER})    # these are also recorded when they fail: then they took nothing
IMPLIES_OPPONENT_HAD_IT = frozenset({S.E_TACKLE, S.E_INTERCEPTION})
M_FREEKICK_ANY = C._mask("FreekickTaken", "IndirectFreekickTaken")
RESTARTS = ((C.M_THROW, "throw_in"), (C.M_GOALKICK, "goal_kick"), (C.M_CORNER, "corner"), (M_FREEKICK_ANY, "free_kick"))
SHOT_END = {S.E_GOAL: "goal", S.E_SAVED: "shot_on", S.E_MISS: "shot_off", S.E_POST: "shot_off"}
REAL_STEPS = frozenset({K_PASS, K_CARRY, K_TAKEON, K_SHOT})         # a move with none of these (one stray touch) is not listed


def build_possessions(m: Match) -> list[dict]:
    """Every move of the match in order. ``tm`` is the silver team index; ``shot`` is the event index of the shot that ended it.

    ``ix`` runs beside ``steps``: the event index of each step (for a carry, the event it led into).
    """
    ev = m.ev
    play = m.play_indices()
    carry_into = {i: (pid, x0, y0, x1, y1) for pid, _t, x0, y0, x1, y1, i in C.carries(m)}
    out: list[dict] = []
    cur: dict | None = None
    pending: tuple[int, str, int] | None = None     # an opponent's touch that has not (yet) taken the ball: (player, what, event)
    skip: set[int] = set()
    kickoff_next = True                             # the next pass from the centre spot is a kick-off

    def clock(i: int) -> int:
        return ev["mi"][i] * 60 + ev["se"][i]

    def own_xy(i: int) -> tuple[int, int]:
        return ev["x"][i], 1000 - ev["y"][i]

    def their_xy(i: int) -> list[int] | None:
        """Where an opponent's event happened, in the move's direction."""
        return [1000 - ev["x"][i], ev["y"][i]] if ev["x"][i] >= 0 and ev["y"][i] >= 0 else None

    def open_move(i: int, start: str, *, marker: bool) -> dict:
        x, y = own_xy(i) if ev["x"][i] >= 0 else (-1, -1)
        return {"tm": ev["tm"][i], "pe": ev["pe"][i], "em": ev["em"][i], "c0": clock(i), "c1": clock(i), "st": start,
                "sp": ev["p"][i] if marker else 0, "sat": [x, y] if marker and x >= 0 else None, "steps": [], "n": 0, "end": "", "lost": 0,
                "by": 0, "how": "", "at": None, "shot": -1, "f3": False, "box": False, "keep": None, "re": "", "ix": []}

    def reach(move: dict, x: int, y: int) -> None:
        if x < 0:
            return
        move["f3"] = move["f3"] or x / 10.0 >= S.FINAL_THIRD_X
        move["box"] = move["box"] or S.in_box(x / 10.0, (1000 - y) / 10.0)

    def add_step(move: dict, i: int) -> None:
        code, ok, pid, em = ev["t"][i], ev["o"][i], ev["p"][i], ev["em"][i]
        has_xy = ev["x"][i] >= 0 and ev["y"][i] >= 0
        x, y = own_xy(i) if has_xy else (-1, -1)
        carried = carry_into.get(i)
        if carried is not None and (move["steps"] or move["sp"]):
            cp, x0, y0, x1, y1 = carried
            prog = (x1 - x0 >= S.PROGRESSIVE_MIN and x1 >= S.PROGRESSIVE_END_X) or (S.in_box(x1, y1) and not S.in_box(x0, y0))
            move["steps"].append([K_CARRY, cp, int(x0 * 10), 1000 - int(y0 * 10), int(x1 * 10), 1000 - int(y1 * 10), 1, em, SF_PROG if prog else 0])
            move["ix"].append(i)
        kind = STEP_KIND.get(code, K_CLEAR if code == S.E_CLEARANCE else K_WIN)
        ex, ey, flags = -1, -1, 0
        if kind == K_PASS:
            if ev["ex"][i] >= 0 and ev["ey"][i] >= 0:
                ex, ey = ev["ex"][i], 1000 - ev["ey"][i]
            q = ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)
            flags = ((SF_CROSS if q & C.M_CROSS else 0) | (SF_LONG if q & C.M_LONG else 0) | (SF_THROUGH if q & C.M_THROUGH else 0)
                     | (SF_KEY if q & C.M_KEY else 0) | (SF_HEAD if q & C.M_HEADPASS else 0))
            if code == E_OFFSIDE_PASS:
                ok = 0
            elif ok:
                move["n"] += 1
                reach(move, ex, ey)
                if (not q & (C.M_RESTART | C.M_CROSS) and has_xy and ex >= 0 and (ex - x) / 10.0 >= S.PROGRESSIVE_MIN
                        and ex / 10.0 >= S.PROGRESSIVE_END_X):
                    flags |= SF_PROG
        elif kind == K_CLEAR or code == S.E_DISPOSSESSED:
            ok = 0
        reach(move, x, y)
        move["steps"].append([kind, pid, x, y, ex, ey, 1 if ok else 0, em, flags])
        move["ix"].append(i)
        move["c1"] = clock(i)

    def close(end: str, *, lost: bool = False, by: tuple[int, str, int] | None = None, keep: bool | None = None, re: str = "") -> None:
        nonlocal cur, pending
        move, cur, pending = cur, None, None
        if move is None or not any(s[0] in REAL_STEPS for s in move["steps"]):
            return
        last = move["steps"][-1]
        move["end"], move["keep"], move["re"] = end, keep, re
        if lost and not (last[0] == K_PASS and last[6]):
            move["lost"] = last[1]
        if by is not None:
            move["by"], move["how"], move["at"] = by[0], by[1], their_xy(by[2])
        out.append(move)

    def begin(i: int, after: tuple[int, str, int] | None = None) -> None:
        """Start a move from event ``i`` of a side that had no move open. ``after`` is that side's stray touch that won the ball."""
        nonlocal cur, kickoff_next
        code, q = ev["t"][i], ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)
        if code in STEP_KIND and code != S.E_DISPOSSESSED:
            start = "open"
            if code == S.E_PASS:
                start = next((name for mask, name in RESTARTS if q & mask), "keeper" if q & C.M_GKTHROW else "open")
                if start == "open" and kickoff_next and abs(ev["x"][i] - 500) <= 15 and abs(ev["y"][i] - 500) <= 15:
                    start = "kickoff"
            elif code in S.SHOT_EVENTS:
                start = "penalty" if q & C.M_PEN else "free_kick" if q & C.M_DIRECT_FK else "open"
            cur = open_move(i, start, marker=False)
            if after is not None and start == "open":
                cur["st"], cur["sp"], cur["sat"] = "loose", after[0], list(own_xy(after[2])) if ev["x"][after[2]] >= 0 else None
            kickoff_next = False
            add_step(cur, i)
        elif code in WIN_KIND and (ev["o"][i] or code not in NEEDS_SUCCESS):
            cur = open_move(i, WIN_KIND[code], marker=True)
            kickoff_next = False

    def shot_end(i: int) -> str:
        q = ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)
        return "shot_blocked" if ev["t"][i] == S.E_SAVED and q & C.M_BLOCKED else SHOT_END[ev["t"][i]]

    period = None
    for k, i in enumerate(play):
        if i in skip:
            continue
        code, tm, ok = ev["t"][i], ev["tm"][i], ev["o"][i]
        q = ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)
        if ev["pe"][i] != period:
            close("whistle")
            period, kickoff_next = ev["pe"][i], True

        if code == S.E_FOUL:
            partner = next((j for j in (play[k + 1] if k + 1 < len(play) else -1, play[k - 1] if k else -1)
                            if j >= 0 and ev["t"][j] == S.E_FOUL and ev["tm"][j] != tm and abs(clock(j) - clock(i)) <= 2), -1)
            if partner >= 0:
                skip.add(partner)
            offender = i if not ok else partner
            if cur is not None:
                fouled_side = tm if ok else 1 - tm
                if cur["tm"] == fouled_side:
                    close("foul_won", by=(ev["p"][offender], "foul", offender) if offender >= 0 else None, keep=True, re="free_kick")
                else:
                    move = cur
                    close("foul", keep=False, re="free_kick")
                    if offender >= 0 and out and out[-1] is move:
                        move["lost"] = ev["p"][offender]
            continue
        if code == S.E_GOAL and ev["fl"][i] & FL_OWN_GOAL:
            if cur is not None and cur["tm"] != tm:
                close("own_goal", by=(ev["p"][i], "own_goal", i))
            else:
                close("lost", lost=True)
            kickoff_next = True
            continue

        is_step = code in STEP_KIND
        is_win = code in WIN_KIND and bool(ok or code not in NEEDS_SUCCESS)
        if not (is_step or is_win or (code == S.E_TACKLE and not ok)):
            continue                                    # duels, cards, substitutions, awards: nothing that moves the ball

        restart = next((name for mask, name in RESTARTS if q & mask), "") if code == S.E_PASS else ""
        if restart:
            if cur is not None:
                keep = cur["tm"] == tm
                stopped = "out" if restart != "free_kick" else "stopped"
                close(stopped, lost=not keep, by=pending if keep else None, keep=keep, re=restart)
            begin(i)
            continue

        if cur is None:
            begin(i)
        elif tm == cur["tm"]:
            if code in IMPLIES_OPPONENT_HAD_IT and is_win:
                close("lost", lost=True, by=pending)     # they had to win it back: the first move was over
                begin(i)
            elif is_step or is_win:
                pending = None
                add_step(cur, i)
            else:
                continue                                 # a tackle of their own that won nothing
        elif code == E_BALL_TOUCH or (code == S.E_TACKLE and not ok):
            pending = pending or (ev["p"][i], "touch" if code == E_BALL_TOUCH else "tackle", i)
            continue
        else:
            touched = pending
            close("lost", lost=True, by=pending or (ev["p"][i], WIN_KIND.get(code, "took"), i))
            begin(i, touched)

        if cur is not None and cur["steps"] and code in S.SHOT_EVENTS:
            cur["shot"] = i
            close(shot_end(i))
            kickoff_next = code == S.E_GOAL
        elif cur is not None and code == E_OFFSIDE_PASS:
            close("offside", keep=False, re="free_kick")
    close("whistle")
    return out


SET_PIECE_WON = frozenset({"corner", "free_kick", "penalty"})


def led_to_shot(moves: list[dict]) -> list[bool]:
    """Per move: did it come to a shot? Either it ended in one, or it won a corner, free kick or penalty and **that** ended in one.

    One link only: the set piece has to be the same side's very next move. Anything further on is a new attack.
    """
    out = [move["shot"] >= 0 for move in moves]
    for k in range(len(moves) - 1):
        move, nxt = moves[k], moves[k + 1]
        if not out[k] and move["keep"] and nxt["tm"] == move["tm"] and nxt["pe"] == move["pe"] and nxt["st"] in SET_PIECE_WON and nxt["shot"] >= 0:
            out[k] = True
    return out


def action_outcomes(moves: list[dict]) -> tuple[set[int], set[int]]:
    """Which actions came to a shot: ``(events, carries)``, the second being the event each such carry led into.

    The shot itself is not an action that "led to" a shot, so it is left out.
    """
    events: set[int] = set()
    carried: set[int] = set()
    for move, shot in zip(moves, led_to_shot(moves), strict=True):
        if not shot:
            continue
        for step, i in zip(move["steps"], move["ix"], strict=True):
            if step[0] == K_CARRY:
                carried.add(i)
            elif step[0] != K_SHOT:
                events.add(i)
    return events, carried


LOST_WITHIN = 3   # "lost soon": the side lost the ball within this many further actions of the same move


def lost_soon(moves: list[dict], within: int = LOST_WITHIN) -> tuple[set[int], set[int]]:
    """Which actions were followed by the side losing the ball within the next ``within`` actions: ``(events, carries)``, as
    :func:`action_outcomes` gives them.

    The second thing that can come of an action, beside a shot: the move went to the other side (taken in play, played out of play,
    a foul or an offside given away) and the losing action was one of the next ``within``. A move that ended in a shot, a restart
    won or the whistle lost nothing. The action that itself gave the ball away is not listed: it did not lead to a loss, it was one.
    """
    events: set[int] = set()
    carried: set[int] = set()
    for move in moves:
        gone = move["end"] in ("lost", "foul", "offside") or (move["end"] in ("out", "stopped") and move["keep"] is False)
        if not gone:
            continue
        last = len(move["steps"]) - 1
        final = move["steps"][last]
        # the losing action is the move's last step (a pass that went astray, a player dispossessed), unless that step is a completed
        # pass: then the receiver lost it before doing anything the data records, one action further on
        loss_at = last + 1 if final[0] == K_PASS and final[6] else last
        for pos, (step, i) in enumerate(zip(move["steps"], move["ix"], strict=True)):
            if pos < loss_at and loss_at - pos <= within:   # pos == loss_at: he lost it himself, which is not "followed by" a loss
                (carried if step[0] == K_CARRY else events).add(i)
    return events, carried
