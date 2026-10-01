"""One match of WhoScored events -> one compact row per player. Pure: no network, no pandas.

Input is the event table ``soccerdata`` returns, as a list of dicts (``DataFrame.to_dict("records")``):
``type``, ``outcome_type``, ``team``, ``player``, ``player_id``, ``x``/``y``/``end_x``/``end_y`` (0-100,
always in the acting team's attacking direction, so x < 50 is that team's own half), ``expanded_minute``
(a continuous clock where a full match runs to about 100), ``period`` and ``qualifiers``.

Definitions (also shown in the app):

* a *forward pass* advances the ball at least ``FORWARD_MIN`` (5% of the pitch);
* a *progressive pass* is a completed pass that advances it at least ``PROGRESSIVE_MIN`` (10%) and ends in the
  attacking 60% of the pitch;
* passes are open-play passes: throw-ins, goal kicks, corners and keeper throws are restarts, and crosses are
  chance creation, so all of those are left out (crosses are counted on their own). WhoScored's own pass totals
  leave out throw-ins, keeper throws and crosses;
* a *tackle* is Opta's ``Tackle`` event: the defender took the ball off the opponent. A *challenge* is the
  opposite, a defender beaten by a dribble, so tackles + challenges are all the tackle attempts (WhoScored's
  "tackles" total is exactly that);
* an *aerial duel* is an ``Aerial`` event, plus an ``AerialFoul`` (a foul committed in the air counts as won for the player
  fouled and lost for the player who fouled, as in WhoScored's own totals);
* a *defensive duel* is a tackle, a challenge or an aerial duel in which he was the defending side. WhoScored marks
  each aerial duel with a ``Defensive`` and an ``Offensive`` player, and its own ``defensiveAerials`` counts exactly
  the ``Defensive`` ones (the own-half rule is only a fallback if the marking is ever missing). WhoScored has no
  event called a defensive duel, so this is our own definition: a duel is won by a tackle or a won aerial, lost by a
  challenge or a lost aerial;
* playing time is scaled so a full match is 90 minutes, whatever the stoppage time.
"""

from __future__ import annotations

from typing import Iterable

FORWARD_MIN = 5.0
PROGRESSIVE_MIN = 10.0
PROGRESSIVE_END_X = 40.0
OWN_HALF = 50.0
RESTARTS = {"ThrowIn", "GoalKick", "CornerTaken", "KeeperThrow"}
CROSS = "Cross"
AERIAL_FOUL = "AerialFoul"
RED_CARD = {"Red", "SecondYellow"}
PLAY_PERIODS = {"FirstHalf", "SecondHalf"}
MATCH_ROW_VERSION = 3  # 2: aerial fouls count as aerial duels; 3: a defensive aerial is the defending side of the duel, as WhoScored marks it

COUNTS = (
    "passes", "pass_ok", "fwd", "prog", "crosses", "tackles", "challenges", "aer", "aer_won",
    "aer_def", "aer_def_won", "int", "rec", "takeons", "takeons_won", "disp", "touches",
)


def _num(value) -> float | None:
    """A float, or None for missing values (pandas hands back NaN)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _qualifiers(event: dict) -> set[str]:
    names = set()
    for q in event.get("qualifiers") or []:
        try:
            names.add(q["type"]["displayName"])
        except (KeyError, TypeError):
            continue
    return names


def _won(event: dict) -> bool:
    return event.get("outcome_type") == "Successful"


def aggregate_match(events: Iterable[dict]) -> list[dict]:
    """The per-player rows for one match, sorted by team then id. Players with no minutes and no events are absent."""
    events = [e for e in events if e.get("period") in PLAY_PERIODS or e.get("period") is None]
    full_time = max((_num(e.get("expanded_minute")) or 0.0 for e in events), default=0.0)
    if full_time <= 0:
        return []

    rows: dict[int, dict] = {}
    on_at: dict[int, float] = {}
    off_at: dict[int, float] = {}
    for e in events:
        pid = _num(e.get("player_id"))
        if pid is None:
            continue
        pid = int(pid)
        minute = _num(e.get("expanded_minute")) or 0.0
        kind = e.get("type")
        marks = _qualifiers(e)
        row = rows.get(pid)
        if row is None:
            row = rows[pid] = {"id": pid, "name": e.get("player") or "", "team": e.get("team") or "", **{k: 0 for k in COUNTS}}
        if kind == "SubstitutionOn":
            on_at[pid] = minute
        elif kind == "SubstitutionOff":
            off_at[pid] = minute
        elif kind == "Card" and marks & RED_CARD:
            off_at[pid] = min(off_at.get(pid, full_time), minute)
        if e.get("is_touch"):
            row["touches"] += 1

        x, end_x = _num(e.get("x")), _num(e.get("end_x"))
        if kind == "Pass":
            if marks & RESTARTS:
                continue
            if CROSS in marks:
                row["crosses"] += 1
                continue
            row["passes"] += 1
            done = _won(e)
            row["pass_ok"] += done
            if x is not None and end_x is not None:
                gain = end_x - x
                row["fwd"] += gain >= FORWARD_MIN
                row["prog"] += done and gain >= PROGRESSIVE_MIN and end_x >= PROGRESSIVE_END_X
        elif kind == "Tackle":
            row["tackles"] += 1  # the outcome only says whether his team kept the ball; the tackle itself was won
        elif kind == "Challenge":
            row["challenges"] += 1  # always lost: the defender was dribbled past
        elif kind == "Aerial" or (kind == "Foul" and AERIAL_FOUL in marks):
            row["aer"] += 1
            row["aer_won"] += _won(e)  # for an aerial foul: Successful is the player fouled, Unsuccessful the one who fouled
            defending = ("Defensive" in marks) if marks & {"Defensive", "Offensive"} else (x is not None and x < OWN_HALF)
            if defending:
                row["aer_def"] += 1
                row["aer_def_won"] += _won(e)
        elif kind == "Interception":
            row["int"] += 1
        elif kind == "BallRecovery":
            row["rec"] += 1
        elif kind == "TakeOn":
            row["takeons"] += 1
            row["takeons_won"] += _won(e)
        elif kind == "Dispossessed":
            row["disp"] += 1

    out = []
    for pid, row in rows.items():
        start = on_at.get(pid, 0.0)  # anyone with events who was never subbed on started the match
        end = off_at.get(pid, full_time)
        minutes = max(0.0, min(end, full_time) - start) * 90.0 / full_time
        if minutes <= 0 and not any(row[k] for k in COUNTS):
            continue
        row["min"] = round(minutes, 1)
        row["start"] = int(pid not in on_at)
        out.append(row)
    return sorted(out, key=lambda r: (r["team"], r["id"]))
