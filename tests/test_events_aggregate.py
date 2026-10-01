"""WhoScored events -> per-player rows (pure, no network)."""

from __future__ import annotations

import math

import pytest

from app.events.aggregate import aggregate_match


def ev(kind, pid, *, team="Reds", x=50.0, y=50.0, end_x=None, end_y=None, minute=10, outcome="Successful", quals=(), period="FirstHalf", touch=True):
    return {
        "type": kind, "outcome_type": outcome, "player_id": float(pid), "player": f"Player {pid}", "team": team, "team_id": 1,
        "x": x, "y": y, "end_x": end_x if end_x is not None else math.nan, "end_y": end_y if end_y is not None else math.nan,
        "expanded_minute": minute, "period": period, "is_touch": touch,
        "qualifiers": [{"type": {"displayName": q, "value": 1}} for q in quals],
    }


def end_of_match(minute=100):
    return {"type": "End", "outcome_type": "Successful", "player_id": math.nan, "team": "", "x": math.nan, "y": math.nan, "end_x": math.nan,
            "end_y": math.nan, "expanded_minute": minute, "period": "SecondHalf", "is_touch": False, "qualifiers": []}


def by_id(rows):
    return {r["id"]: r for r in rows}


def test_pass_counts_forward_progressive_and_restarts():
    events = [
        ev("Pass", 1, x=30, end_x=33),                       # 3 forward: not forward
        ev("Pass", 1, x=30, end_x=36),                       # +6: forward, not progressive
        ev("Pass", 1, x=30, end_x=45),                       # +15 into the attacking 60%: forward and progressive
        ev("Pass", 1, x=30, end_x=45, outcome="Unsuccessful"),  # forward but not completed: not progressive
        ev("Pass", 1, x=10, end_x=22),                       # +12 but ends in our own half: forward, not progressive
        ev("Pass", 1, x=60, end_x=50),                       # backward
        ev("Pass", 1, x=0, end_x=60, quals=("GoalKick",)),   # restarts are not play
        ev("Pass", 1, x=40, end_x=45, quals=("ThrowIn",)),
        ev("Pass", 1, x=95, end_x=90, quals=("CornerTaken",)),
        ev("Pass", 1, x=5, end_x=40, quals=("KeeperThrow",)),
        ev("Pass", 1, x=80, end_x=95, quals=("Cross",)),     # a cross is chance creation, counted on its own
        end_of_match(),
    ]
    p = by_id(aggregate_match(events))[1]
    assert p["passes"] == 6 and p["pass_ok"] == 5 and p["crosses"] == 1
    assert p["fwd"] == 4 and p["prog"] == 1
    assert p["touches"] == 11  # every touch counts, restarts and crosses included


def test_defensive_duels_are_tackles_challenges_and_defending_aerials():
    events = [
        # a Tackle is a duel won whatever its outcome says (that is only about keeping the ball); a Challenge is a duel lost
        ev("Tackle", 2, outcome="Successful"), ev("Tackle", 2, outcome="Unsuccessful"),
        ev("Challenge", 2, outcome="Unsuccessful"),
        ev("Aerial", 2, x=20, outcome="Successful", quals=("Defensive",)), ev("Aerial", 2, x=30, outcome="Unsuccessful", quals=("Defensive",)),
        ev("Aerial", 2, x=80, outcome="Successful", quals=("Offensive",)),  # the attacking side of a duel is not a defensive duel
        ev("Interception", 2), ev("BallRecovery", 2), ev("BallRecovery", 2),
        ev("TakeOn", 2, outcome="Successful"), ev("TakeOn", 2, outcome="Unsuccessful"), ev("Dispossessed", 2),
        end_of_match(),
    ]
    p = by_id(aggregate_match(events))[2]
    assert (p["tackles"], p["challenges"]) == (2, 1)
    assert (p["aer"], p["aer_won"], p["aer_def"], p["aer_def_won"]) == (3, 2, 2, 1)
    assert (p["int"], p["rec"], p["takeons"], p["takeons_won"], p["disp"]) == (1, 2, 2, 1, 1)


def test_minutes_are_scaled_so_a_full_match_is_ninety():
    events = [
        ev("Pass", 1, minute=5), ev("Pass", 1, minute=95),                                  # starts and plays on
        ev("Pass", 2, minute=10), ev("SubstitutionOff", 2, minute=63),                       # off at 63 of 100
        ev("SubstitutionOn", 3, minute=63), ev("Pass", 3, minute=70),                        # on at 63, plays to the end
        ev("Pass", 4, minute=20), ev("Card", 4, minute=70, quals=("Red",)),                  # sent off at 70
        end_of_match(100),
    ]
    rows = by_id(aggregate_match(events))
    assert rows[1]["min"] == 90.0 and rows[1]["start"] == 1
    assert rows[2]["min"] == pytest.approx(63 * 0.9, abs=0.1) and rows[2]["start"] == 1
    assert rows[3]["min"] == pytest.approx(37 * 0.9, abs=0.1) and rows[3]["start"] == 0
    assert rows[4]["min"] == pytest.approx(70 * 0.9, abs=0.1)
    # extra stoppage time does not change what "90" means
    long = by_id(aggregate_match([ev("Pass", 1, minute=5), end_of_match(110)]))
    assert long[1]["min"] == 90.0


def test_pre_and_post_match_noise_and_events_without_a_player_are_ignored():
    events = [
        ev("Pass", 1, minute=10),
        ev("Pass", 9, minute=0, period="PreMatch"), ev("Pass", 9, minute=10, period="PostGame"),
        {**end_of_match(), "type": "FormationSet"},
        end_of_match(100),
    ]
    rows = by_id(aggregate_match(events))
    assert set(rows) == {1}
    assert aggregate_match([]) == []


def test_missing_coordinates_still_count_as_a_pass_but_not_a_forward_one():
    events = [{**ev("Pass", 1), "end_x": math.nan, "x": math.nan}, end_of_match()]
    p = by_id(aggregate_match(events))[1]
    assert p["passes"] == 1 and p["fwd"] == 0 and p["prog"] == 0


def test_an_aerial_foul_is_an_aerial_duel_won_by_the_player_fouled_and_lost_by_the_one_who_fouled():
    events = [
        ev("Foul", 1, x=4, outcome="Successful", quals=("Foul", "AerialFoul")),      # the keeper is fouled going up for the ball in his own box
        ev("Foul", 2, x=96, outcome="Unsuccessful", quals=("Foul", "AerialFoul")),   # the attacker who fouled him, in the far half of the pitch
        ev("Foul", 3, x=30, outcome="Unsuccessful", quals=("Foul",)),                # an ordinary foul is not a duel
        end_of_match(),
    ]
    rows = by_id(aggregate_match(events))
    assert (rows[1]["aer"], rows[1]["aer_won"], rows[1]["aer_def"], rows[1]["aer_def_won"]) == (1, 1, 1, 1)
    assert (rows[2]["aer"], rows[2]["aer_won"], rows[2]["aer_def"], rows[2]["aer_def_won"]) == (1, 0, 0, 0)
    assert rows[3]["aer"] == 0


def test_a_defensive_aerial_is_the_defending_side_not_a_place_on_the_pitch():
    events = [
        ev("Aerial", 1, x=70, outcome="Unsuccessful", quals=("Defensive",)),   # a forward defending a long clearance in the opponent's half still defends
        ev("Aerial", 1, x=20, outcome="Successful", quals=("Offensive",)),    # a centre-back attacking a set piece in his own half does not
        ev("Aerial", 1, x=20, outcome="Successful"),                           # no marking at all: fall back to the half-way line
        ev("Aerial", 1, x=80, outcome="Successful"),
        end_of_match(),
    ]
    p = by_id(aggregate_match(events))[1]
    assert (p["aer"], p["aer_def"], p["aer_def_won"]) == (4, 2, 1)
