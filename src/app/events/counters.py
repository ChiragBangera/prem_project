"""Gold layer, step one: a silver match -> counts per player and per team.

Counters are *sums*, never rates: a season is the sum of its matches, and every metric the app shows (per 90, ratios,
shares) is a function of summed counters (see :mod:`app.metrics`). That keeps definitions in one place and lets a new
metric be added without touching how matches are read.

Conventions
-----------
* only the two playing halves count (no pre-match, post-game or extra-time rows);
* coordinates are WhoScored's 0-100 units in the acting team's attacking direction (see :mod:`app.events.schema`);
* ``min`` is playing time scaled so that a full match is 90 minutes whatever the stoppage time, as it always was here;
* "open-play passes" leave out throw-ins, goal kicks, corners and goalkeeper throws (restarts) and crosses (counted on
  their own), because the first are not play and the last is chance creation;
* a *tackle* is Opta's ``Tackle`` event (the defender won the duel); a *challenge* is the opposite, a defender beaten by a
  dribble, so tackles + challenges are all the tackle attempts.

Every counter is declared in :data:`COUNTERS` with its definition. The data dictionary and the tests read that table.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from . import schema as S
from .silver import FL_GOAL, FL_OWN_GOAL, FL_TOUCH, Match

GOLD_KIND = "ws_gold"
GOLD_VERSION = 1

#: counter -> definition (every counter a gold row can contain)
COUNTERS: dict[str, str] = {
    # time
    "min": "Minutes played, scaled so a full match is 90 whatever the stoppage time.",
    "apps": "Matches in which the player was on the pitch.", "starts": "Matches started.", "sub_on": "Times he came on as a substitute.",
    "sub_off": "Times he was substituted off.", "rating": "WhoScored's match rating (1-10), summed over rated matches.", "rated": "Matches with a WhoScored rating.",
    "motm": "Man of the match awards.", "gf_on": "Goals his team scored while he was on the pitch.", "ga_on": "Goals his team conceded while he was on the pitch.",
    # touches
    "touches": "Every event on the ball (passes, take-ons, tackles, shots ...).", "touch_def3": "Touches in the team's own third.",
    "touch_mid3": "Touches in the middle third.", "touch_att3": "Touches in the attacking third.", "touch_box": "Touches in the opponent's penalty area.",
    # passing
    "passes": "Open-play passes attempted.", "pass_ok": "Open-play passes completed.", "fwd": "Open-play passes that advance the ball at least 5% of the pitch (~5 m).",
    "prog": "Completed passes that advance the ball at least 10% of the pitch and end in the attacking 60%.", "bwd": "Open-play passes that go back at least 5% of the pitch.",
    "pass_len": "Total length (m) of open-play passes.", "pass_len_n": "Open-play passes with a recorded length.", "pass_x": "Sum of the start position (0-100) of open-play passes.",
    "pass_fwd_m": "Metres gained toward goal by completed open-play passes (forward gains only).",
    "pass_f3": "Open-play passes from outside the final third into it.", "pass_f3_ok": "...of which completed.",
    "pass_box": "Open-play passes from outside the penalty area into it.", "pass_box_ok": "...of which completed.",
    "pass_long": "Open-play long balls (Opta's long-ball marker).", "pass_long_ok": "...of which completed.",
    "pass_through": "Through balls attempted.", "pass_through_ok": "...of which completed.", "pass_chip": "Chipped passes.", "pass_head": "Headed passes.",
    "pass_short_ok": "Completed open-play passes of under 15 m.", "pass_short": "Open-play passes of under 15 m.",
    "crosses": "Crosses attempted (open play and free kicks, not corners).", "crosses_ok": "Crosses that found a team-mate.",
    "key_passes": "Actions (almost always passes) that led directly to a shot by a team-mate. Same idea as Understat's key passes.", "assists": "Passes that led directly to a goal.", "bc_created": "Passes that created a big chance.",
    "corners": "Corner kicks taken.", "corners_key": "Corners that led directly to a shot.", "fk_taken": "Free kicks taken as passes.", "throwins": "Throw-ins taken.",
    "goal_kicks": "Goal kicks taken.", "gk_throws": "Goalkeeper throws.",
    # carrying (estimated from consecutive on-ball events by the same team)
    "carries": "Carries: the ball moved at least 3 m with the same team on it between two events.", "carry_m": "Total metres carried.",
    "carry_prog": "Carries that advance the ball at least 10% of the pitch and end in the attacking 60%, or end in the penalty area.", "carry_prog_m": "Metres gained by progressive carries.",
    "carry_f3": "Carries from outside the final third into it.", "carry_box": "Carries from outside the penalty area into it.",
    # dribbling and being fouled
    "takeons": "Take-ons (dribbles past an opponent) attempted.", "takeons_won": "Take-ons that beat the opponent.", "dispossessed": "Times he lost the ball to a tackle.",
    "fouled": "Fouls suffered.",
    # shooting (WhoScored's own shot events; Understat's xG is used for shot quality)
    "shots": "Shots (excluding own goals).", "sot": "Shots on target (goals and saves, not blocked).", "shots_blocked": "Shots blocked by an outfield player.",
    "shots_off": "Shots off target.", "shots_post": "Shots that hit the woodwork.", "goals": "Goals (excluding own goals).", "own_goals": "Own goals scored.",
    "bigch": "Shots Opta marks as a big chance.", "bigch_goals": "...of which scored.", "pen_taken": "Penalties taken.", "pen_goals": "Penalties scored.",
    "shots_box": "Shots from inside the penalty area.", "shots_head": "Headed shots.", "fk_shots": "Direct free-kick shots.", "shot_dist": "Sum of the distance (m) from goal of shots.",
    # defending
    "tackles": "Tackles won (Opta Tackle events).", "tackles_kept": "...after which his team kept the ball.", "challenges": "Times he was dribbled past.",
    "interceptions": "Passes read and cut out.", "clearances": "Clearances.", "clr_head": "Headed clearances.", "blocks_pass": "Passes and crosses blocked.",
    "blocks_shot": "Shots blocked by an outfield player.", "recoveries": "Loose or contested balls won back.", "rec_opp": "...in the opponent's half.", "rec_att3": "...in the attacking third.",
    "aerials": "Aerial duels contested.", "aerial_won": "Aerial duels won.", "aerial_def": "Aerial duels as the defending side.", "aerial_def_won": "...won.",
    "fouls": "Fouls committed.", "pen_conceded": "Penalties conceded.", "pen_won": "Penalties won.", "offside_won": "Opponents caught offside by his line.",
    "errors": "Errors by him (any).", "err_shot": "Errors that led to an opponent's shot.", "err_goal": "Errors that led to an opponent's goal.",
    "defx": "Sum of the pitch position (0-100) of tackles, interceptions, challenges and pass blocks.", "defx_n": "Number of those actions.",
    # goalkeeping
    "gk_saves": "Shots saved by a goalkeeper.", "gk_saves_box": "...from inside the box.", "gk_saves_out": "...from outside the box.", "gk_saves_6yd": "...from inside the six-yard box.",
    "gk_dive": "Diving saves.", "gk_claims": "High claims of crosses.", "gk_punches": "Punches.", "gk_sweeper": "Sweeper actions outside the box.", "gk_sweeper_ok": "...successful.",
    "gk_pickups": "Pick-ups of loose balls.", "gk_smother": "Smothers (diving at an attacker's feet).", "gk_pen_faced": "Penalties faced.", "gk_cross_missed": "Crosses he failed to claim.",
    "sot_faced": "Shots on target faced (saves + goals conceded, own goals excluded).", "clean_sheet": "Matches with 60+ minutes played and no goal conceded by the team.",
    # discipline
    "yellow": "Yellow cards (a second yellow is counted as a red instead; cards rescinded after a review do not count).", "red": "Red cards, direct or second yellow.", "second_yellow": "Second yellow cards.", "offsides": "Times flagged offside.",
    # team-level possession sequences
    "seq": "Possession sequences (runs of touches uninterrupted by the opponent).", "seq_passes": "Passes within sequences.", "seq_10p": "Sequences of ten or more passes.",
    "seq_f3": "Sequences that reached the final third.", "seq_box": "Sequences that reached the penalty area.", "seq_shot": "Sequences that ended in a shot.",
    "seq_gain": "Net pitch gained (0-100 units) from the first to the last touch, summed over sequences.", "seq_secs": "Duration in seconds, summed over sequences.",
    "seq_fast": "Sequences that gained at least 40% of the pitch in 15 seconds or less (direct attacks).", "seq_start_x": "Sum of the position (0-100) where sequences began.",
}
TEAM_ONLY = ("seq", "seq_passes", "seq_10p", "seq_f3", "seq_box", "seq_shot", "seq_gain", "seq_secs", "seq_fast", "seq_start_x")


def _mask(*names: str) -> int:
    lo, hi = S.flag_mask(*names)
    return lo | (hi << S.WORD_BITS)


M_RESTART = _mask("ThrowIn", "GoalKick", "CornerTaken", "KeeperThrow")
M_CROSS, M_LONG, M_THROUGH = _mask("Cross"), _mask("Longball"), _mask("Throughball")
M_CHIP, M_HEADPASS, M_KEY, M_BCC = _mask("Chipped"), _mask("HeadPass"), _mask("KeyPass"), _mask("BigChanceCreated")
M_CORNER, M_FK, M_THROW, M_GOALKICK, M_GKTHROW = _mask("CornerTaken"), _mask("FreekickTaken"), _mask("ThrowIn"), _mask("GoalKick"), _mask("KeeperThrow")
M_BLOCKED, M_OUTFIELD_BLOCK, M_BIGCH, M_PEN, M_HEAD, M_DIRECT_FK = _mask("Blocked"), _mask("OutfielderBlock"), _mask("BigChance"), _mask("Penalty"), _mask("Head"), _mask("DirectFreekick")
M_ASSISTED, M_AERIAL_FOUL, M_DEFENSIVE, M_OFFENSIVE = _mask("Assisted"), _mask("AerialFoul"), _mask("Defensive"), _mask("Offensive")
M_SAVE_BOX, M_SAVE_OUT, M_SAVE_6YD, M_DIVE = _mask("KeeperSaveInTheBox"), _mask("KeeperSaveObox"), _mask("KeeperSaveInSixYard"), _mask("DivingSave")
M_LEAD_SHOT, M_LEAD_GOAL, M_VOID_YELLOW = _mask("LeadingToAttempt"), _mask("LeadingToGoal"), _mask("VoidYellowCard")

DEF_ACTIONS = frozenset({S.E_TACKLE, S.E_INTERCEPTION, S.E_CHALLENGE, S.E_BLOCKED_PASS})
SHORT_PASS_M = 15.0
MIN_CARRY_M, MAX_CARRY_M, MAX_CARRY_SECS = 3.0, 60.0, 10.0


def _u(value: int) -> float | None:
    return None if value < 0 else value / 10.0


def _in_box(x: float | None, y: float | None) -> bool:
    return S.in_box(x, y)


def _dist_m(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot((x1 - x0) * S.PITCH_LENGTH_M / 100.0, (y1 - y0) * S.PITCH_WIDTH_M / 100.0)


class _Acc:
    """Counters for one player or team: only non-zero ones are kept."""

    __slots__ = ("c",)

    def __init__(self) -> None:
        self.c: dict[str, float] = defaultdict(float)

    def add(self, key: str, value: float = 1) -> None:
        self.c[key] += value

    def out(self) -> dict[str, float]:
        return {k: (round(v, 2) if isinstance(v, float) and not float(v).is_integer() else int(v)) for k, v in self.c.items() if v}


def carries(m: Match) -> list[tuple[int, int, float, float, float, float, int]]:
    """Estimated carries as ``(player, team, x0, y0, x1, y1, event index)``.

    Between two consecutive touches by the same team in the same half, if the ball ended up at least 3 m (and at most 60 m)
    from where the previous event left it within ten seconds, the second player carried it that far. This is the standard way
    of recovering dribbles from an event stream (the SPADL convention); it is an estimate, and the Data dictionary says so.
    """
    ev = m.ev
    out = []
    prev = None  # (team, end x, end y, clock, period, index)
    for i in m.play_indices():
        if not (ev["fl"][i] & FL_TOUCH) or ev["x"][i] < 0:
            continue
        team, pe = ev["tm"][i], ev["pe"][i]
        clock = ev["mi"][i] * 60 + ev["se"][i]
        x, y = ev["x"][i] / 10.0, ev["y"][i] / 10.0
        if prev is not None and prev[0] == team and prev[4] == pe and ev["p"][i]:
            d = _dist_m(prev[1], prev[2], x, y)
            if MIN_CARRY_M <= d <= MAX_CARRY_M and 0 <= clock - prev[3] <= MAX_CARRY_SECS:
                out.append((ev["p"][i], team, prev[1], prev[2], x, y, i))
        code = ev["t"][i]
        ex, ey = _u(ev["ex"][i]), _u(ev["ey"][i])
        if code == S.E_PASS and ev["o"][i] and ex is not None and ey is not None:
            prev = (team, ex, ey, clock, pe, i)  # a completed pass ends where it was received
        elif code in (S.E_PASS, S.E_CLEARANCE) or code in S.SHOT_EVENTS:
            prev = None  # an incomplete pass, a clearance or a shot ends the move
        else:
            prev = (team, x, y, clock, pe, i)
    return out


def _sequences(m: Match, accs: list[_Acc]) -> None:
    """Possession sequences per team: runs of touches broken only by a touch from the other side."""
    ev = m.ev
    cur = None  # dict for the sequence in progress
    sequences = []
    for i in m.play_indices():
        if not (ev["fl"][i] & FL_TOUCH):
            continue
        team, clock = ev["tm"][i], ev["mi"][i] * 60 + ev["se"][i]
        x = ev["x"][i] / 10.0 if ev["x"][i] >= 0 else None
        if cur is None or cur["team"] != team or ev["pe"][i] != cur["pe"]:
            if cur is not None:
                sequences.append(cur)
            cur = {"team": team, "pe": ev["pe"][i], "x0": x, "x1": x, "t0": clock, "t1": clock, "passes": 0, "f3": False, "box": False, "shot": False}
        if x is not None:
            cur["x1"] = x
            if cur["x0"] is None:
                cur["x0"] = x
            cur["f3"] |= x >= S.FINAL_THIRD_X
            cur["box"] |= _in_box(x, ev["y"][i] / 10.0 if ev["y"][i] >= 0 else None)
        cur["t1"] = clock
        if ev["t"][i] == S.E_PASS and not (ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS)) & M_RESTART:
            cur["passes"] += 1
        if ev["t"][i] in S.SHOT_EVENTS and not ev["fl"][i] & FL_OWN_GOAL:
            cur["shot"] = True
    if cur is not None:
        sequences.append(cur)
    for s in sequences:
        a = accs[s["team"]]
        a.add("seq")
        a.add("seq_passes", s["passes"])
        if s["passes"] >= 10:
            a.add("seq_10p")
        a.add("seq_f3", s["f3"])
        a.add("seq_box", s["box"])
        a.add("seq_shot", s["shot"])
        if s["x0"] is not None and s["x1"] is not None:
            gain = s["x1"] - s["x0"]
            a.add("seq_gain", gain)
            a.add("seq_start_x", s["x0"])
            secs = max(0, s["t1"] - s["t0"])
            a.add("seq_secs", secs)
            if gain >= 40 and 0 < secs <= 15:
                a.add("seq_fast")


def derive_match(m: Match) -> dict:
    """The gold row of one match: both teams' counters and every player's, plus the facts needed to place them."""
    ev = m.ev
    ft = m.info.get("full_time") or 0
    teams = [_Acc(), _Acc()]
    players: dict[int, _Acc] = defaultdict(_Acc)
    play = m.play_indices()
    q = [ev["q0"][i] | (ev["q1"][i] << S.WORD_BITS) for i in range(m.n)]

    def put(pid: int, tm: int, key: str, value: float = 1) -> None:
        teams[tm].add(key, value)
        if pid:
            players[pid].add(key, value)

    # ---- goals timeline (who scored, and when): an own goal counts for the other side
    goals: list[tuple[int, int, bool]] = []  # (expanded minute, scoring team, was it an own goal)
    for i in play:
        if ev["fl"][i] & FL_GOAL:
            tm, own = ev["tm"][i], bool(ev["fl"][i] & FL_OWN_GOAL)
            goals.append((ev["em"][i], 1 - tm if own else tm, own))

    # ---- one pass over the events
    for i in play:
        code, pid, tm, ok, qq = ev["t"][i], ev["p"][i], ev["tm"][i], ev["o"][i], q[i]
        x, y, ex, ey = _u(ev["x"][i]), _u(ev["y"][i]), _u(ev["ex"][i]), _u(ev["ey"][i])
        if ev["fl"][i] & FL_TOUCH:
            put(pid, tm, "touches")
            if x is not None:
                put(pid, tm, "touch_def3" if x < S.DEF_THIRD_X else "touch_att3" if x >= S.FINAL_THIRD_X else "touch_mid3")
                if _in_box(x, y):
                    put(pid, tm, "touch_box")
        if qq & M_KEY and code != S.E_PASS:
            put(pid, tm, "key_passes")  # the action that set up a shot is not always a pass (a touch, a tackle, a rebound)
            if qq & M_BCC:
                put(pid, tm, "bc_created")
        if code == S.E_PASS:
            if qq & M_KEY:
                put(pid, tm, "key_passes")
                if qq & M_BCC:
                    put(pid, tm, "bc_created")
            if qq & M_CORNER:
                put(pid, tm, "corners")
            if qq & M_FK:
                put(pid, tm, "fk_taken")
            if qq & M_THROW:
                put(pid, tm, "throwins")
            if qq & M_GOALKICK:
                put(pid, tm, "goal_kicks")
            if qq & M_GKTHROW:
                put(pid, tm, "gk_throws")
            if qq & M_RESTART:
                continue
            if qq & M_CROSS:
                put(pid, tm, "crosses")
                put(pid, tm, "crosses_ok", ok)
                continue
            put(pid, tm, "passes")
            put(pid, tm, "pass_ok", ok)
            ln = ev["ln"][i]
            if ln >= 0:
                put(pid, tm, "pass_len", ln / 10.0)
                put(pid, tm, "pass_len_n")
                if ln / 10.0 < SHORT_PASS_M:
                    put(pid, tm, "pass_short")
                    put(pid, tm, "pass_short_ok", ok)
            if qq & M_LONG:
                put(pid, tm, "pass_long")
                put(pid, tm, "pass_long_ok", ok)
            if qq & M_THROUGH:
                put(pid, tm, "pass_through")
                put(pid, tm, "pass_through_ok", ok)
            if qq & M_CHIP:
                put(pid, tm, "pass_chip")
            if qq & M_HEADPASS:
                put(pid, tm, "pass_head")
            if x is not None:
                put(pid, tm, "pass_x", x)
            if x is not None and ex is not None:
                gain = ex - x
                if gain >= S.FORWARD_MIN:
                    put(pid, tm, "fwd")
                elif gain <= -S.FORWARD_MIN:
                    put(pid, tm, "bwd")
                if ok and gain >= S.PROGRESSIVE_MIN and ex >= S.PROGRESSIVE_END_X:
                    put(pid, tm, "prog")
                if ok and gain > 0:
                    put(pid, tm, "pass_fwd_m", gain * S.PITCH_LENGTH_M / 100.0)
                if x < S.FINAL_THIRD_X <= ex:
                    put(pid, tm, "pass_f3")
                    put(pid, tm, "pass_f3_ok", ok)
                if ey is not None and _in_box(ex, ey) and not _in_box(x, y):
                    put(pid, tm, "pass_box")
                    put(pid, tm, "pass_box_ok", ok)
        elif code == S.E_TAKEON:
            put(pid, tm, "takeons")
            put(pid, tm, "takeons_won", ok)
        elif code == S.E_DISPOSSESSED:
            put(pid, tm, "dispossessed")
        elif code == S.E_TACKLE:
            put(pid, tm, "tackles")
            put(pid, tm, "tackles_kept", ok)
        elif code == S.E_CHALLENGE:
            put(pid, tm, "challenges")
        elif code == S.E_INTERCEPTION:
            put(pid, tm, "interceptions")
        elif code == S.E_CLEARANCE:
            put(pid, tm, "clearances")
            if qq & M_HEAD:
                put(pid, tm, "clr_head")
        elif code == S.E_BLOCKED_PASS:
            put(pid, tm, "blocks_pass")
        elif code == S.E_RECOVERY:
            put(pid, tm, "recoveries")
            if x is not None and x >= S.OWN_HALF_X:
                put(pid, tm, "rec_opp")
            if x is not None and x >= S.FINAL_THIRD_X:
                put(pid, tm, "rec_att3")
        elif code == S.E_AERIAL or (code == S.E_FOUL and qq & M_AERIAL_FOUL):
            put(pid, tm, "aerials")
            put(pid, tm, "aerial_won", ok)  # for an aerial foul, successful is the player fouled and unsuccessful the one who fouled
            defending = bool(qq & M_DEFENSIVE) if qq & (M_DEFENSIVE | M_OFFENSIVE) else (x is not None and x < S.OWN_HALF_X)
            if defending:
                put(pid, tm, "aerial_def")
                put(pid, tm, "aerial_def_won", ok)
        if code == S.E_FOUL:
            if ok:
                put(pid, tm, "fouled")
                if qq & M_PEN:
                    put(pid, tm, "pen_won")
            else:
                put(pid, tm, "fouls")
                if qq & M_PEN:
                    put(pid, tm, "pen_conceded")
        elif code == S.E_SAVE:
            if qq & M_OUTFIELD_BLOCK:
                put(pid, tm, "blocks_shot")
            else:
                put(pid, tm, "gk_saves")
                if qq & M_SAVE_BOX:
                    put(pid, tm, "gk_saves_box")
                if qq & M_SAVE_OUT:
                    put(pid, tm, "gk_saves_out")
                if qq & M_SAVE_6YD:
                    put(pid, tm, "gk_saves_6yd")
                if qq & M_DIVE:
                    put(pid, tm, "gk_dive")
        elif code == S.E_CLAIM:
            put(pid, tm, "gk_claims", ok)
        elif code == S.E_PUNCH:
            put(pid, tm, "gk_punches")
        elif code == S.E_SWEEPER:
            put(pid, tm, "gk_sweeper")
            put(pid, tm, "gk_sweeper_ok", ok)
        elif code == S.E_PICKUP:
            put(pid, tm, "gk_pickups")
        elif code == S.E_SMOTHER:
            put(pid, tm, "gk_smother")
        elif code == S.E_PEN_FACED:
            put(pid, tm, "gk_pen_faced")
        elif code == S.E_CROSS_NOT_CLAIMED:
            put(pid, tm, "gk_cross_missed")
        elif code == S.E_ERROR:
            put(pid, tm, "errors")
            if qq & M_LEAD_SHOT:
                put(pid, tm, "err_shot")
            if qq & M_LEAD_GOAL:
                put(pid, tm, "err_goal")
        elif code == S.E_OFFSIDE_PROVOKED:
            put(pid, tm, "offside_won")
        elif code == S.E_OFFSIDE_GIVEN:
            put(pid, tm, "offsides")
        elif code == S.E_CARD:
            card = ev["ct"][i]
            if card == S.CARD_YELLOW:
                if not qq & M_VOID_YELLOW:  # a booking the referee rescinded after a review is not a card
                    put(pid, tm, "yellow")
            elif card == S.CARD_SECOND_YELLOW:  # his first yellow was already counted; this booking sends him off
                put(pid, tm, "second_yellow")
                put(pid, tm, "red")
            elif card == S.CARD_RED:
                put(pid, tm, "red")
        if x is not None and (code in DEF_ACTIONS or (code == S.E_SAVE and qq & M_OUTFIELD_BLOCK)):
            put(pid, tm, "defx", x)
            put(pid, tm, "defx_n")
        if code in S.SHOT_EVENTS and not ev["fl"][i] & FL_OWN_GOAL:
            put(pid, tm, "shots")
            if code == S.E_GOAL:
                put(pid, tm, "goals")
                put(pid, tm, "sot")
            elif code == S.E_SAVED:
                if qq & M_BLOCKED:
                    put(pid, tm, "shots_blocked")
                else:
                    put(pid, tm, "sot")
            elif code == S.E_MISS:
                put(pid, tm, "shots_off")
            elif code == S.E_POST:
                put(pid, tm, "shots_post")
            if qq & M_BIGCH:
                put(pid, tm, "bigch")
                put(pid, tm, "bigch_goals", code == S.E_GOAL)
            if qq & M_PEN:
                put(pid, tm, "pen_taken")
                put(pid, tm, "pen_goals", code == S.E_GOAL)
            if qq & M_HEAD:
                put(pid, tm, "shots_head")
            if qq & M_DIRECT_FK:
                put(pid, tm, "fk_shots")
            if x is not None and y is not None:
                if _in_box(x, y):
                    put(pid, tm, "shots_box")
                put(pid, tm, "shot_dist", _dist_m(x, y, 100.0, 50.0))
        elif code == S.E_GOAL and ev["fl"][i] & FL_OWN_GOAL:
            put(pid, tm, "own_goals")

    # ---- assists: the pass related to a goal that was marked as assisted
    for i in play:
        if ev["t"][i] == S.E_GOAL and not ev["fl"][i] & FL_OWN_GOAL and q[i] & M_ASSISTED and ev["rs"][i] >= 0:
            j = ev["rs"][i]
            if ev["t"][j] == S.E_PASS and ev["p"][j]:
                put(ev["p"][j], ev["tm"][j], "assists")
    for i in play:  # corners that led to a shot (the key-pass flag on a corner pass)
        if ev["t"][i] == S.E_PASS and q[i] & M_CORNER and q[i] & M_KEY:
            put(ev["p"][i], ev["tm"][i], "corners_key")

    # ---- estimated carries
    for pid, tm, x0, y0, x1, y1, _i in carries(m):
        d = _dist_m(x0, y0, x1, y1)
        put(pid, tm, "carries")
        put(pid, tm, "carry_m", d)
        gain = x1 - x0
        if (gain >= S.PROGRESSIVE_MIN and x1 >= S.PROGRESSIVE_END_X) or (_in_box(x1, y1) and not _in_box(x0, y0)):
            put(pid, tm, "carry_prog")
            put(pid, tm, "carry_prog_m", max(0.0, gain) * S.PITCH_LENGTH_M / 100.0)
        if x0 < S.FINAL_THIRD_X <= x1:
            put(pid, tm, "carry_f3")
        if _in_box(x1, y1) and not _in_box(x0, y0):
            put(pid, tm, "carry_box")

    _sequences(m, teams)

    # ---- playing time and what happened while each player was on the pitch
    rows = []
    gf = [sum(1 for _t, s, _og in goals if s == 0), sum(1 for _t, s, _og in goals if s == 1)]
    for p in m.players:
        pid, tm = p["id"], p["tm"]
        start = 0 if p["start"] else p["on"]
        acc = players.get(pid)
        if start is None or start < 0:
            if acc is not None:  # never on the pitch (an unused substitute booked from the bench): his card counts, his time does not
                rows.append({"id": pid, "name": p["name"], "tm": tm, "pos": p["pos"], "start": False, "c": acc.out()})
            continue
        end = ft
        for stop in (p["off"], p["red"]):
            if stop is not None and stop >= 0:
                end = min(end, stop)
        minutes = max(0.0, min(end, ft) - start) * 90.0 / ft if ft > 0 else 0.0
        if minutes <= 0 and acc is None:
            continue
        acc = acc or _Acc()
        acc.add("min", round(minutes, 1))
        if minutes > 0:
            acc.add("apps")
            acc.add("starts", p["start"])
            acc.add("sub_on", not p["start"])
            acc.add("sub_off", p["off"] is not None and p["off"] >= 0 and not p["red"])
            acc.add("gf_on", sum(1 for t, s, _og in goals if s == tm and start <= t <= end))
            acc.add("ga_on", sum(1 for t, s, _og in goals if s != tm and start <= t <= end))
            acc.add("clean_sheet", p["pos"] == "GK" and minutes >= 60 and gf[1 - tm] == 0)
        if p["rating"] is not None and minutes > 0:
            acc.add("rating", p["rating"])
            acc.add("rated")
        acc.add("motm", p["motm"])
        saves = acc.c.get("gk_saves", 0)
        if saves or p["pos"] == "GK":
            conceded = sum(1 for t, s, og in goals if s != tm and not og and start <= t <= end)
            acc.add("sot_faced", saves + conceded)
        rows.append({"id": pid, "name": p["name"], "tm": tm, "pos": p["pos"], "start": p["start"], "c": acc.out()})

    out_teams = []
    for idx, t in enumerate(m.teams):
        formations: dict[str, int] = defaultdict(int)
        for f in t["formations"]:
            if f["name"] and f["end"] > f["start"]:
                formations[f["name"]] += f["end"] - f["start"]
        main = max(formations, key=formations.get) if formations else None
        out_teams.append({"id": t["id"], "name": t["name"], "side": t["side"], "manager": t["manager"], "avg_age": t["avg_age"], "formation": main,
                          "formations": dict(formations), "gf": gf[idx], "ga": gf[1 - idx], "c": teams[idx].out()})
    return {"v": GOLD_VERSION, "game": m.game, "date": (m.info.get("start") or "")[:10], "ft": ft, "score": m.info.get("ft"), "teams": out_teams, "players": rows}


def merge(parts: Iterable[dict[str, float]]) -> dict[str, float]:
    """Add counter dicts together (a player's season is the sum of his matches)."""
    out: dict[str, float] = defaultdict(float)
    for part in parts:
        for key, value in part.items():
            out[key] += value
    return {k: (round(v, 2) if isinstance(v, float) and not float(v).is_integer() else int(v)) for k, v in out.items()}
