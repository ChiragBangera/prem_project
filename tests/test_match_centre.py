"""The match centre document: which events become which rows, in whose direction, and what is left for the browser to work out."""

from __future__ import annotations

from types import SimpleNamespace

from app.analytics.match_centre import PF_ASSIST, attach_xg, build_centre
from app.events.maps import D_AERIAL, D_RECOVER, D_TACKLE, PF_BOX, PF_F3, PF_KEY, PF_PROG, PF_RESTART

from .events_kit import AWAY, end, ev, player, silver


def fixture(**kw):
    """Home: 1 and 2 start, 3 comes on for 2. Away: 9. The second half starts at minute 46."""
    events = [
        ev("Pass", 1, x=30, y=20, end_x=70, end_y=40, minute=1, second=0),                                   # progressive, into the final third; 2 touches next
        ev("Pass", 2, x=70, y=40, end_x=90, end_y=50, minute=1, second=4, quals=("KeyPass", "IntentionalGoalAssist")),   # into the box, sets up the goal
        ev("Goal", 1, x=90, y=50, minute=1, second=6, quals=("BigChance", "RightFoot", ("RelatedEventId", 2)), isShot=True, isGoal=True, goalMouthY=50.0, goalMouthZ=10.0),
        ev("Pass", 1, x=0, y=0, end_x=20, end_y=20, minute=5, quals=("ThrowIn",)),                           # a restart
        ev("Pass", 1, x=40, y=50, end_x=45, end_y=50, minute=6, outcome=0),                                  # lost
        ev("Tackle", 1, x=60, y=50, minute=7),
        ev("BallRecovery", 2, x=70, y=50, minute=8),
        ev("Aerial", 1, x=30, y=50, minute=9, outcome=0),
        ev("Foul", 1, x=45, y=50, minute=10, outcome=0, touch=False),
        ev("Foul", 9, team=AWAY, x=55, y=50, minute=10, outcome=1, touch=False),                              # the same foul, as won: not listed
        ev("Card", 1, x=45, y=50, minute=10, touch=False, cardType={"displayName": "Yellow", "value": 1}),
        ev("SavedShot", 9, team=AWAY, x=80, y=30, minute=20, quals=("Blocked",), isShot=True),
        ev("SubstitutionOff", 2, x=None, y=None, minute=60, period=2, touch=False),
        ev("SubstitutionOn", 3, x=None, y=None, minute=60, period=2, touch=False, relatedPlayerId=2),
        ev("TakeOn", 3, x=75, y=80, minute=70, period=2),
        ev("MissedShots", 3, x=85, y=60, minute=80, period=2, isShot=True),
        end(),
    ]
    home = [player(1), player(2, position="FW"), player(3, start=False)]
    return silver(events, home_players=home, away_players=[player(9, team_side="away")], **kw)


def test_rows_are_in_each_sides_own_direction_with_the_left_wing_at_the_top():
    c = build_centre(fixture(), final=True)
    first = c["passes"][0]
    assert first[:8] == [0, 1, 1, 300, 800, 700, 600, 1]            # y is flipped: WhoScored's 20 (the right) is drawn at 800
    assert first[8] & PF_PROG and first[8] & PF_F3 and first[9] == 1 and first[10] == 2   # the receiver is the next team-mate to touch it
    key = c["passes"][1]
    assert key[8] & PF_KEY and key[8] & PF_BOX and key[8] & PF_ASSIST
    assert c["passes"][2][8] & PF_RESTART
    assert c["passes"][3][7] == 0 and c["passes"][3][10] == 0        # a lost pass has no receiver


def test_shots_timeline_and_defending():
    c = build_centre(fixture(), final=True)
    goal, blocked, miss = c["shots"]
    assert (goal["result"], goal["big"], goal["body"], goal["assist"], goal["gy"], goal["gz"]) == ("Goal", True, "RightFoot", 2, 500, 100)
    assert (blocked["tm"], blocked["result"]) == (1, "BlockedShot") and (miss["pe"], miss["result"]) == (2, "MissedShots")
    assert [(t["kind"], t["tm"], t["p"], t["other"]) for t in c["timeline"]] == [("goal", 0, 1, 2), ("yellow", 0, 1, 0), ("sub", 0, 3, 2)]
    assert sorted(d[5] for d in c["def"]) == sorted([D_TACKLE, D_RECOVER, D_AERIAL])
    assert [f[5] for f in c["fouls"]] == [1]                         # the foul committed, once
    assert c["takeons"] == [[0, 2, 70, 750, 200, 1, 3]]
    assert c["clock"] == {"end": 100, "ht": 20, "second_from": 60, "status": "FT"}
    bench = [p for p in c["teams"][0]["players"] if not p["start"]]
    assert [p["id"] for p in bench] == [3] and c["names"]["9"] == "Player 9"


def test_flip_swaps_the_sides_everywhere():
    c = build_centre(fixture(), final=True, flip=True)
    assert c["teams"][0]["name"] == "Blues" and c["passes"][0][0] == 1 and c["shots"][0]["tm"] == 1 and c["timeline"][0]["tm"] == 1


def test_xg_is_attached_to_the_matching_shot_only():
    c = build_centre(fixture(), final=True)
    shot = lambda minute, x, y, xg, result="Goal": SimpleNamespace(minute=minute, x=x, y=y, xg=xg, result=result)   # noqa: E731
    attach_xg(c, {"h": [shot(1, 0.90, 0.50, 0.41), shot(44, 0.9, 0.5, 0.2)], "a": [shot(20, 0.80, 0.30, 0.05, "BlockedShot")]})
    assert [s["xg"] for s in c["shots"]] == [0.41, 0.05, None]       # the 80th-minute miss has no Understat shot near it: left empty, not guessed
