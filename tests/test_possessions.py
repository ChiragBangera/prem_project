"""Possessions: where one move ends and the next begins, who lost the ball and who took it."""

from __future__ import annotations

from app.analytics.match_centre import build_centre
from app.events.possessions import K_CARRY, K_PASS, K_SHOT, K_TAKEON, K_TOUCH, SF_CROSS, build_possessions, led_to_shot

from .events_kit import AWAY, counters, end, ev, silver


def moves(events):
    return build_possessions(silver([*events, end()]))


def players(move, kind=None):
    return [s[1] for s in move["steps"] if kind is None or s[0] == kind]


def test_a_move_runs_until_the_shot_and_a_goal_ends_it():
    m, = moves([
        ev("Pass", 1, x=50, y=50, end_x=30, end_y=50, minute=0, second=0),                       # kick-off
        ev("Pass", 2, x=30, y=50, end_x=70, end_y=40, minute=0, second=3),
        ev("Pass", 3, x=70, y=40, end_x=90, end_y=50, minute=0, second=6, quals=("KeyPass",)),
        ev("Goal", 4, x=90, y=50, minute=0, second=8, isShot=True, isGoal=True),
    ])
    assert (m["tm"], m["st"], m["end"], m["n"]) == (0, "kickoff", "goal", 3)
    assert players(m, K_PASS) == [1, 2, 3] and m["steps"][-1][:2] == [K_SHOT, 4]
    assert m["f3"] and m["box"] and m["lost"] == 0 and m["by"] == 0
    assert m["steps"][0][2:6] == [500, 500, 300, 500]             # tenths; y flipped so the left wing is at the top


def test_a_tackle_names_who_lost_it_and_who_took_it():
    first, second = moves([
        ev("Pass", 1, x=40, y=50, end_x=60, end_y=50, minute=5, second=0),
        ev("Dispossessed", 2, x=60, y=50, minute=5, second=3),
        ev("Tackle", 9, team=AWAY, x=40, y=50, minute=5, second=3),
        ev("Pass", 9, team=AWAY, x=40, y=50, end_x=55, end_y=50, minute=5, second=5, outcome=0),
        ev("Pass", 1, x=45, y=50, end_x=40, end_y=50, minute=5, second=40, quals=("ThrowIn",)),
    ])[:2]
    assert (first["end"], first["lost"], first["by"], first["how"]) == ("lost", 2, 9, "tackle")
    assert first["at"] == [600, 500]                               # the tackle, in the direction of the move it ended
    assert (second["tm"], second["st"], second["sp"]) == (1, "tackle", 9)
    assert (second["end"], second["lost"], second["by"], second["keep"], second["re"]) == ("out", 9, 0, False, "throw_in")   # played out: nobody broke it


def test_a_deflection_that_stays_with_the_same_side_does_not_end_the_move():
    m, = moves([
        ev("Pass", 1, x=40, y=50, end_x=60, end_y=50, minute=5, second=0, outcome=0),
        ev("BallTouch", 9, team=AWAY, x=45, y=50, minute=5, second=1),
        ev("Pass", 2, x=58, y=50, end_x=70, end_y=50, minute=5, second=3),
        ev("TakeOn", 3, x=70, y=50, minute=5, second=6, outcome=0),
        ev("Tackle", 9, team=AWAY, x=30, y=50, minute=5, second=6, outcome=0),               # a tackle that did not win it
        ev("BallTouch", 3, x=72, y=50, minute=5, second=7),
        ev("MissedShots", 3, x=85, y=50, minute=5, second=9, isShot=True),
    ])
    assert m["end"] == "shot_off" and m["n"] == 1
    assert [s[:2] for s in m["steps"]] == [[K_PASS, 1], [K_PASS, 2], [K_TAKEON, 3], [K_TOUCH, 3], [K_CARRY, 3], [K_SHOT, 3]]


def test_a_stray_touch_takes_the_ball_when_that_side_plays_next():
    lost, taken = moves([
        ev("Pass", 1, x=40, y=50, end_x=60, end_y=50, minute=5, second=0, outcome=0),
        ev("BallTouch", 9, team=AWAY, x=45, y=50, minute=5, second=1),
        ev("Pass", 8, team=AWAY, x=47, y=50, end_x=60, end_y=50, minute=5, second=3),
        ev("SavedShot", 9, team=AWAY, x=80, y=50, minute=5, second=9, isShot=True),
    ])
    assert (lost["end"], lost["lost"], lost["by"], lost["how"]) == ("lost", 1, 9, "touch")
    assert (taken["st"], taken["sp"], taken["end"]) == ("loose", 9, "shot_on")


def test_a_completed_pass_nobody_received_names_no_loser():
    m = moves([
        ev("Pass", 1, x=40, y=50, end_x=60, end_y=50, minute=5, second=0),
        ev("BallRecovery", 9, team=AWAY, x=40, y=50, minute=5, second=2, touch=False),
        ev("Pass", 9, team=AWAY, x=40, y=50, end_x=45, end_y=50, minute=5, second=3),
    ])[0]
    assert (m["end"], m["lost"], m["by"], m["how"]) == ("lost", 0, 9, "recovery")


def test_set_pieces_start_moves_and_fouls_and_offside_end_them():
    corner, won, gave, off = moves([
        ev("Pass", 1, x=99, y=1, end_x=92, end_y=45, minute=10, second=0, quals=("CornerTaken", "Cross")),
        ev("SavedShot", 2, x=92, y=45, minute=10, second=2, quals=("Blocked",), isShot=True),
        ev("Pass", 1, x=50, y=50, end_x=55, end_y=50, minute=12, second=0),
        ev("Foul", 2, x=55, y=50, minute=12, second=3, outcome=1),
        ev("Foul", 9, team=AWAY, x=45, y=50, minute=12, second=3, outcome=0, touch=False),
        ev("Pass", 1, x=55, y=50, end_x=60, end_y=50, minute=13, second=0, quals=("FreekickTaken",)),
        ev("Foul", 9, team=AWAY, x=40, y=50, minute=13, second=4, outcome=1),
        ev("Foul", 2, x=60, y=50, minute=13, second=4, outcome=0, touch=False),
        ev("Pass", 9, team=AWAY, x=40, y=50, end_x=60, end_y=50, minute=14, second=0, quals=("FreekickTaken",)),
        ev("OffsidePass", 8, team=AWAY, x=60, y=50, end_x=80, end_y=50, minute=14, second=3),
    ])
    assert (corner["st"], corner["end"], corner["steps"][0][8] & SF_CROSS) == ("corner", "shot_blocked", SF_CROSS)
    assert (won["end"], won["by"], won["how"], won["keep"]) == ("foul_won", 9, "foul", True)
    assert (gave["st"], gave["end"], gave["lost"]) == ("free_kick", "foul", 2)
    assert (off["tm"], off["end"], off["steps"][-1][6]) == (1, "offside", 0)


def test_carries_are_steps_and_halves_do_not_run_together():
    first, second = moves([
        ev("Pass", 1, x=30, y=50, end_x=40, end_y=50, minute=44, second=0),
        ev("Pass", 2, x=55, y=50, end_x=60, end_y=50, minute=44, second=4),                   # 2 took it 15 units on before passing
        ev("Pass", 1, x=50, y=50, end_x=40, end_y=50, minute=45, second=0, period=2),
    ])
    assert [s[0] for s in first["steps"]] == [K_PASS, K_CARRY, K_PASS] and first["steps"][1][1:6] == [2, 400, 500, 550, 500]
    assert first["end"] == "whistle" and (second["pe"], second["st"]) == (2, "kickoff")


def test_the_centre_carries_the_moves_with_the_shot_they_ended_in():
    events = [
        ev("Pass", 9, team=AWAY, x=50, y=50, end_x=70, end_y=50, minute=3, second=0),
        ev("MissedShots", 8, team=AWAY, x=80, y=50, minute=3, second=4, isShot=True),
        ev("Pass", 1, x=50, y=50, end_x=80, end_y=50, minute=4, second=0),
        ev("Goal", 2, x=88, y=50, minute=4, second=3, isShot=True, isGoal=True),
        end(),
    ]
    c = build_centre(silver(events), final=True)
    assert [(p["tm"], p["end"], p["si"]) for p in c["possessions"]] == [(1, "shot_off", 0), (0, "goal", 1)]
    assert all("shot" not in p for p in c["possessions"])
    flipped = build_centre(silver(events), final=True, flip=True)
    assert [p["tm"] for p in flipped["possessions"]] == [0, 1]


def test_an_action_came_to_a_shot_when_its_move_did_or_the_corner_it_won_did():
    events = [
        ev("Pass", 1, x=30, y=50, end_x=55, end_y=50, minute=1, second=0),                       # progressive, and the move is lost
        ev("Pass", 2, x=55, y=50, end_x=60, end_y=50, minute=1, second=3, outcome=0),
        ev("Interception", 9, team=AWAY, x=40, y=50, minute=1, second=4),
        ev("Pass", 9, team=AWAY, x=40, y=50, end_x=45, end_y=50, minute=1, second=6, outcome=0),
        ev("Pass", 1, x=30, y=50, end_x=70, end_y=50, minute=2, second=0),                       # progressive, into the final third
        ev("TakeOn", 3, x=70, y=50, minute=2, second=3),
        ev("Pass", 3, x=80, y=20, end_x=92, end_y=50, minute=2, second=6, outcome=0, quals=("Cross",)),
        ev("Pass", 2, x=99, y=1, end_x=90, end_y=50, minute=2, second=40, quals=("CornerTaken",)),   # the cross won a corner
        ev("MissedShots", 4, x=90, y=50, minute=2, second=43, isShot=True),
    ]
    found = moves(events)
    assert led_to_shot(found) == [False, False, True, True]
    c = counters(events)
    assert (c[1]["prog"], c[1]["prog_shot"], c[1]["f3_entry"], c[1]["f3_entry_shot"]) == (2, 1, 1, 1)
    assert (c[3]["takeons_won_shot"], c[3]["crosses_shot"], c[3]["mv_in"], c[3]["mv_shot_in"]) == (1, 1, 1, 1)
    assert (c[1]["mv_in"], c[1]["mv_shot_in"]) == (2, 1) and "prog_shot" not in c[4]              # the shot is not an action that led to one
    assert c[2]["mv_lost"] == 1 and c[9]["mv_broken"] == 1 and c[9]["mv_lost"] == 1


def test_an_action_is_followed_by_a_loss_when_the_side_loses_the_ball_within_three_more_actions():
    from app.events.possessions import lost_soon

    built = moves([
        ev("Pass", 1, x=20, y=50, end_x=30, end_y=50, minute=5, second=0),         # four actions before the loss: too far back
        ev("Pass", 2, x=30, y=50, end_x=45, end_y=50, minute=5, second=2),         # three actions later the ball is gone
        ev("Pass", 3, x=45, y=50, end_x=60, end_y=50, minute=5, second=4),
        ev("Pass", 4, x=60, y=50, end_x=70, end_y=50, minute=5, second=6),
        ev("Dispossessed", 5, x=70, y=50, minute=5, second=8),                     # he lost it himself: not "followed by" a loss
        ev("Tackle", 9, team=AWAY, x=30, y=50, minute=5, second=8),
        ev("Pass", 9, team=AWAY, x=30, y=50, end_x=60, end_y=50, minute=5, second=10),
        ev("MissedShots", 9, team=AWAY, x=85, y=50, minute=5, second=13, isShot=True),   # a move that came to a shot lost nothing
    ])
    first = built[0]
    events, carried = lost_soon(built)
    by_player = {first["steps"][n][1] for n, i in enumerate(first["ix"]) if i in events}
    assert first["end"] == "lost" and by_player == {2, 3, 4} and not carried
    assert not (set(built[1]["ix"]) & events)
    assert lost_soon(built, within=1)[0] == {first["ix"][3]}                       # only the pass straight before the loss


def test_the_counters_keep_what_followed_each_progressive_pass():
    c = counters([
        ev("Pass", 1, x=40, y=50, end_x=75, end_y=50, minute=5, second=0),         # progressive, then lost two actions later
        ev("Pass", 2, x=75, y=50, end_x=80, end_y=50, minute=5, second=2),
        ev("Dispossessed", 3, x=80, y=50, minute=5, second=4),
        ev("Tackle", 9, team=AWAY, x=20, y=50, minute=5, second=4),
    ])
    assert c[1]["prog"] == 1 and c[1]["prog_lost"] == 1 and c[1].get("prog_shot", 0) == 0
