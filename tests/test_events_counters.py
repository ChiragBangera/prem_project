"""Event definitions: raw WhoScored events -> silver -> per-player counters. Pure, no network.

Each test names a definition the app relies on and pins it down on a handful of hand-made events. The first block is the original
event pipeline's behaviour, kept exactly (existing metrics must not drift); the rest covers what the richer pipeline adds.
"""

from __future__ import annotations

import pytest

from app.events import counters as C
from app.events import silver as SV

from .events_kit import AWAY, HOME, counters, end, ev, gold, match, player, silver


# ------------------------------------------------------------------ the original definitions, kept


def test_pass_counts_forward_progressive_and_restarts():
    events = [
        ev("Pass", 1, x=30, end_x=33),                          # 3 forward: not forward
        ev("Pass", 1, x=30, end_x=36),                          # +6: forward, not progressive
        ev("Pass", 1, x=30, end_x=45),                          # +15 into the attacking 60%: forward and progressive
        ev("Pass", 1, x=30, end_x=45, outcome=0),               # forward but not completed: not progressive
        ev("Pass", 1, x=10, end_x=22),                          # +12 but ends in our own half: forward, not progressive
        ev("Pass", 1, x=60, end_x=50),                          # backward
        ev("Pass", 1, x=0, end_x=60, quals=("GoalKick",)),      # restarts are not play
        ev("Pass", 1, x=40, end_x=45, quals=("ThrowIn",)),
        ev("Pass", 1, x=95, end_x=90, quals=("CornerTaken",)),
        ev("Pass", 1, x=5, end_x=40, quals=("KeeperThrow",)),
        ev("Pass", 1, x=80, end_x=95, quals=("Cross",)),        # a cross is chance creation, counted on its own
        end(),
    ]
    p = counters(events)[1]
    assert p["passes"] == 6 and p["pass_ok"] == 5 and p["crosses"] == 1
    assert p["fwd"] == 4 and p["prog"] == 1 and p["bwd"] == 1
    assert p["touches"] == 11  # every touch counts, restarts and crosses included
    assert p["throwins"] == 1 and p["goal_kicks"] == 1 and p["corners"] == 1 and p["gk_throws"] == 1


def test_defensive_duels_are_tackles_challenges_and_defending_aerials():
    events = [
        # a Tackle is a duel won whatever its outcome says (that is only about keeping the ball); a Challenge is a duel lost
        ev("Tackle", 2, outcome=1), ev("Tackle", 2, outcome=0), ev("Challenge", 2, outcome=0),
        ev("Aerial", 2, x=20, outcome=1, quals=("Defensive",)), ev("Aerial", 2, x=30, outcome=0, quals=("Defensive",)),
        ev("Aerial", 2, x=80, outcome=1, quals=("Offensive",)),   # the attacking side of a duel is not a defensive duel
        ev("Interception", 2), ev("BallRecovery", 2), ev("BallRecovery", 2),
        ev("TakeOn", 2, outcome=1), ev("TakeOn", 2, outcome=0), ev("Dispossessed", 2), end(),
    ]
    p = counters(events)[2]
    assert (p["tackles"], p["challenges"], p["tackles_kept"]) == (2, 1, 1)
    assert (p["aerials"], p["aerial_won"], p["aerial_def"], p["aerial_def_won"]) == (3, 2, 2, 1)
    assert (p["interceptions"], p["recoveries"], p["takeons"], p["takeons_won"], p["dispossessed"]) == (1, 2, 2, 1, 1)


def test_minutes_are_scaled_so_a_full_match_is_ninety():
    events = [
        ev("Pass", 1, minute=5), ev("Pass", 1, minute=95),                              # starts and plays on
        ev("Pass", 2, minute=10), ev("SubstitutionOff", 2, minute=63),                  # off at 63 of 100
        ev("SubstitutionOn", 3, minute=63), ev("Pass", 3, minute=70),                   # on at 63, plays to the end
        ev("Pass", 4, minute=20), ev("Card", 4, minute=70, quals=("Red",), cardType={"displayName": "Red", "value": 2}),   # sent off at 70
        end(100),
    ]
    c = counters(events)
    assert c[1]["min"] == 90.0 and c[1]["starts"] == 1
    assert c[2]["min"] == pytest.approx(63 * 0.9, abs=0.1) and c[2]["starts"] == 1
    assert c[3]["min"] == pytest.approx(37 * 0.9, abs=0.1) and c[3].get("starts", 0) == 0 and c[3]["sub_on"] == 1
    assert c[4]["min"] == pytest.approx(70 * 0.9, abs=0.1)
    # extra stoppage time does not change what "90" means
    assert counters([ev("Pass", 1, minute=5), end(110)])[1]["min"] == 90.0


def test_a_booked_substitute_who_never_played_gets_his_card_but_no_minutes():
    """A bench player can be shown a card from the bench. He played no minutes and made no appearance."""
    bench = player(7, start=False)
    events = [ev("Pass", 1, minute=5), ev("Card", 7, minute=93, outcome=1, cardType={"displayName": "Yellow", "value": 1}), end(100)]
    c = counters(events, home_players=[player(1), bench])
    assert c[7]["yellow"] == 1 and c[7].get("min", 0) == 0 and c[7].get("apps", 0) == 0
    assert c[1]["apps"] == 1


def test_pre_and_post_match_noise_and_events_without_a_player_are_ignored():
    events = [
        ev("Pass", 1, minute=10),
        ev("Pass", 9, minute=0, period=16), ev("Pass", 9, minute=10, period=14),
        ev("FormationSet", None, x=None, y=None, minute=0, period=16, touch=False),
        end(100),
    ]
    assert set(counters(events)) == {1}


def test_missing_coordinates_still_count_as_a_pass_but_not_a_forward_one():
    p = counters([ev("Pass", 1, x=None, y=None), end()])[1]
    assert p["passes"] == 1 and p.get("fwd", 0) == 0 and p.get("prog", 0) == 0


def test_an_aerial_foul_is_an_aerial_duel_won_by_the_player_fouled_and_lost_by_the_one_who_fouled():
    events = [
        ev("Foul", 1, x=4, outcome=1, quals=("Foul", "AerialFoul")),      # the keeper is fouled going up for the ball in his own box
        ev("Foul", 2, x=96, outcome=0, quals=("Foul", "AerialFoul")),     # the attacker who fouled him, in the far half of the pitch
        ev("Foul", 3, x=30, outcome=0, quals=("Foul",)),                  # an ordinary foul is not a duel
        end(),
    ]
    c = counters(events)
    assert (c[1]["aerials"], c[1]["aerial_won"], c[1]["aerial_def"], c[1]["aerial_def_won"]) == (1, 1, 1, 1)
    assert (c[2]["aerials"], c[2].get("aerial_won", 0), c[2].get("aerial_def", 0)) == (1, 0, 0)
    assert c[3].get("aerials", 0) == 0
    assert c[1]["fouled"] == 1 and c[2]["fouls"] == 1 and c[3]["fouls"] == 1   # in the air or not, it is still a foul


def test_a_defensive_aerial_is_the_defending_side_not_a_place_on_the_pitch():
    events = [
        ev("Aerial", 1, x=70, outcome=0, quals=("Defensive",)),   # a forward defending a long clearance in the opponent's half still defends
        ev("Aerial", 1, x=20, outcome=1, quals=("Offensive",)),   # a centre-back attacking a set piece in his own half does not
        ev("Aerial", 1, x=20, outcome=1),                         # no marking at all: fall back to the half-way line
        ev("Aerial", 1, x=80, outcome=1), end(),
    ]
    p = counters(events)[1]
    assert (p["aerials"], p["aerial_def"], p["aerial_def_won"]) == (4, 2, 1)


# ------------------------------------------------------------------ what the richer pipeline adds


def test_passing_zones_lengths_and_kinds():
    events = [
        ev("Pass", 1, x=50, y=50, end_x=70, end_y=50, quals=(("Length", 21.0),)),                            # into the final third
        ev("Pass", 1, x=70, y=50, end_x=90, end_y=50, quals=(("Length", 21.0),)),                            # into the box (x >= 83.3, central)
        ev("Pass", 1, x=40, y=50, end_x=70, end_y=50, outcome=0, quals=("Longball", ("Length", 31.5))),      # a long ball that failed
        ev("Pass", 1, x=40, y=50, end_x=60, end_y=50, quals=("Throughball", ("Length", 21.0))),
        ev("Pass", 1, x=30, y=50, end_x=33, end_y=50, quals=(("Length", 3.0),)),                             # short
        end(),
    ]
    p = counters(events)[1]
    assert p["passes"] == 5 and p["pass_f3"] == 2 and p["pass_f3_ok"] == 1 and p["pass_box"] == 1   # a pass that starts inside the final third does not enter it
    assert (p["pass_long"], p.get("pass_long_ok", 0), p["pass_through"], p["pass_through_ok"]) == (1, 0, 1, 1)
    assert p["pass_len_n"] == 5 and p["pass_len"] == pytest.approx(21 + 21 + 31.5 + 21 + 3)
    assert p["pass_short"] == 1 and p["pass_short_ok"] == 1
    assert p["pass_fwd_m"] == pytest.approx((20 + 20 + 20 + 3) * 1.05, abs=0.2)  # completed passes only, in metres


def test_key_passes_count_on_any_action_that_set_up_a_shot_and_assists_follow_the_goal():
    events = [
        ev("Pass", 1, x=70, end_x=85, quals=("KeyPass", "BigChanceCreated"), eid=10),
        ev("Goal", 2, x=90, y=50, quals=("Assisted", "BigChance", ("RelatedEventId", 10)), isGoal=True, isShot=True),
        ev("Pass", 3, x=60, end_x=75, quals=("KeyPass",), eid=11),                   # a key pass whose shot was missed: no assist
        ev("MissedShots", 4, x=88, y=40, quals=("Assisted", ("RelatedEventId", 11)), isShot=True),
        ev("Tackle", 5, x=60, quals=("KeyPass",)),                                   # a tackle that led to a shot also counts as a chance created
        end(),
    ]
    c = counters(events)
    assert c[1]["key_passes"] == 1 and c[1]["assists"] == 1 and c[1]["bc_created"] == 1
    assert c[3]["key_passes"] == 1 and c[3].get("assists", 0) == 0
    assert c[5]["key_passes"] == 1
    assert c[2]["goals"] == 1 and c[2]["sot"] == 1 and c[2]["bigch"] == 1 and c[2]["bigch_goals"] == 1


def test_shots_goals_own_goals_penalties_and_blocks():
    events = [
        ev("Goal", 1, x=92, y=50, isGoal=True, isShot=True, quals=("Penalty",)),
        ev("SavedShot", 1, x=85, y=45, isShot=True),                                    # on target
        ev("SavedShot", 1, x=80, y=50, isShot=True, quals=("Blocked",)),                # blocked: not on target
        ev("MissedShots", 1, x=75, y=70, isShot=True), ev("ShotOnPost", 1, x=88, y=55, isShot=True),
        ev("Goal", 9, team=AWAY, x=5, y=50, isGoal=True, isShot=True, isOwnGoal=True, quals=("OwnGoal",)),   # an own goal is not a shot
        end(),
    ]
    c = counters(events, home_players=[player(1)], away_players=[player(9, team_side="away")])
    p = c[1]
    assert (p["shots"], p["goals"], p["sot"], p["shots_blocked"], p["shots_off"], p["shots_post"]) == (5, 1, 2, 1, 1, 1)
    assert (p["pen_taken"], p["pen_goals"]) == (1, 1) and p["shots_box"] == 3
    assert c[9]["own_goals"] == 1 and c[9].get("shots", 0) == 0


def test_a_save_is_the_keepers_unless_it_carries_the_outfield_block_marker():
    events = [
        ev("Save", 20, x=3, y=50, quals=("KeeperSaveInTheBox", "DivingSave")), ev("Save", 20, x=1, y=50, quals=("KeeperSaveObox",)),
        ev("Save", 5, x=15, y=50, quals=("OutfielderBlock",)),                          # a defender blocked a shot
        ev("Claim", 20, x=6), ev("Punch", 20, x=5), ev("KeeperSweeper", 20, x=20), ev("KeeperPickup", 20, x=4), end(),
    ]
    c = counters(events)
    g = c[20]
    assert (g["gk_saves"], g["gk_saves_box"], g["gk_saves_out"], g["gk_dive"]) == (2, 1, 1, 1)
    assert (g["gk_claims"], g["gk_punches"], g["gk_sweeper"], g["gk_pickups"]) == (1, 1, 1, 1)
    assert c[5]["blocks_shot"] == 1 and c[5].get("gk_saves", 0) == 0


def test_fouls_who_committed_and_who_suffered_and_penalties_and_cards():
    events = [
        ev("Foul", 1, outcome=0, quals=("Penalty",)), ev("Foul", 2, team=AWAY, outcome=1, quals=("Penalty",)),     # 1 gave a penalty away, 2 won it
        ev("Card", 1, outcome=1, cardType={"displayName": "Yellow", "value": 1}),
        ev("Card", 1, outcome=1, cardType={"displayName": "Yellow", "value": 1}, quals=("VoidYellowCard",)),     # rescinded after a review: not a card
        ev("Card", 3, outcome=1, cardType={"displayName": "SecondYellow", "value": 3}),
        ev("Card", 4, outcome=1, cardType={"displayName": "Red", "value": 2}),
        ev("OffsideGiven", 5, outcome=0), ev("OffsideProvoked", 6, team=AWAY), end(),
    ]
    c = counters(events)
    assert (c[1]["fouls"], c[1]["pen_conceded"], c[1]["yellow"]) == (1, 1, 1)
    assert (c[2]["fouled"], c[2]["pen_won"]) == (1, 1)
    assert (c[3].get("yellow", 0), c[3]["second_yellow"], c[3]["red"]) == (0, 1, 1)   # a second yellow is a red, not another yellow
    assert c[4]["red"] == 1 and c[5]["offsides"] == 1 and c[6]["offside_won"] == 1


def test_touches_by_third_and_box_and_defensive_height():
    events = [ev("Pass", 1, x=10, end_x=20), ev("Pass", 1, x=50, end_x=60), ev("Pass", 1, x=80, end_x=90), ev("Pass", 1, x=90, y=50, end_x=95),
              ev("Tackle", 1, x=30), ev("Interception", 1, x=50), ev("BlockedPass", 1, x=40), end()]
    p = counters(events)[1]
    assert (p["touch_def3"], p["touch_mid3"], p["touch_att3"], p["touch_box"]) == (2, 3, 2, 1)
    assert p["defx_n"] == 3 and p["defx"] == pytest.approx(120.0)


def test_carries_are_estimated_from_consecutive_touches_by_the_same_team():
    events = [
        ev("Pass", 1, x=30, y=50, end_x=40, end_y=50, minute=10, second=0),
        ev("Pass", 2, x=52, y=50, end_x=70, end_y=50, minute=10, second=4),     # player 2 had it at 40, was next seen at 52: carried 12 units (12.6 m)
        ev("Pass", 3, x=70.5, y=50, end_x=75, end_y=50, minute=10, second=6),   # 0.5 units: not a carry
        ev("Pass", 4, team=AWAY, x=20, y=50, end_x=30, end_y=50, minute=10, second=8),
        ev("Pass", 5, x=60, y=50, end_x=70, end_y=50, minute=10, second=30),    # too long since the last event of his team: no carry
        end(),
    ]
    c = counters(events, away_players=[player(4, team_side="away")])
    assert c[2]["carries"] == 1 and c[2]["carry_m"] == pytest.approx(12.6, abs=0.1) and c[2]["carry_prog"] == 1 and c[2]["carry_prog_m"] == pytest.approx(12.6, abs=0.1)
    assert c[3].get("carries", 0) == 0 and c[5].get("carries", 0) == 0 and c[1].get("carries", 0) == 0


def test_team_totals_and_possession_sequences():
    events = [
        ev("Pass", 1, x=10, end_x=30, minute=1), ev("Pass", 2, x=30, end_x=60, minute=1, second=3), ev("Pass", 3, x=60, y=50, end_x=88, end_y=50, minute=1, second=5),   # reaches the final third and the box
        ev("MissedShots", 3, x=90, y=50, isShot=True, minute=1, second=6),
        ev("Pass", 9, team=AWAY, x=30, end_x=20, minute=1, second=20),     # the other side has it: sequence over
        ev("Pass", 1, x=40, end_x=45, minute=2), end(),
    ]
    g = gold(events, away_players=[player(9, team_side="away")])
    home = g["teams"][0]["c"]
    assert home["passes"] == 4 and home["seq"] == 2 and home["seq_f3"] == 1 and home["seq_box"] == 1 and home["seq_shot"] == 1
    assert home["seq_passes"] == 4 and home["seq_start_x"] == pytest.approx(10 + 40)
    assert g["teams"][1]["c"]["passes"] == 1 and g["teams"][1]["c"]["seq"] == 1


def test_goals_while_on_the_pitch_and_the_keepers_shots_faced_and_clean_sheet():
    events = [
        ev("Save", 20, x=3, quals=("KeeperSaveInTheBox",), minute=20),
        ev("Goal", 9, team=AWAY, x=95, y=50, isGoal=True, isShot=True, minute=60),         # conceded at 60
        ev("Goal", 8, team=HOME, x=95, y=50, isGoal=True, isShot=True, minute=70),         # scored at 70
        ev("SubstitutionOff", 20, minute=65), ev("SubstitutionOn", 21, minute=65), ev("Pass", 21, x=10, end_x=20, minute=70), end(100),
    ]
    home = [player(20, position="GK"), player(8), player(21, start=False, position="GK")]
    c = counters(events, home_players=home, away_players=[player(9, team_side="away")], score="1 : 1")
    assert c[20]["ga_on"] == 1 and c[20].get("gf_on", 0) == 0 and c[20]["gk_saves"] == 1 and c[20]["sot_faced"] == 2 and c[20].get("clean_sheet", 0) == 0
    assert c[21].get("ga_on", 0) == 0 and c[21]["gf_on"] == 1 and c[21].get("clean_sheet", 0) == 0   # on at 65: under 60 minutes played
    clean = counters([ev("Pass", 20, minute=5), end(100)], home_players=[player(20, position="GK")], score="0 : 0")
    assert clean[20]["clean_sheet"] == 1


def test_every_counter_a_match_produces_is_declared():
    """The dictionary lists the counters from one table; a counter that is produced but undeclared would be invisible to it."""
    events = [ev("Pass", 1, x=50, end_x=70, quals=("KeyPass", "Longball", ("Length", 25.0))), ev("Tackle", 1), ev("Goal", 1, isGoal=True, isShot=True), end()]
    produced = {k for c in counters(events).values() for k in c}
    assert produced <= set(C.COUNTERS), produced - set(C.COUNTERS)


# ------------------------------------------------------------------ silver


def test_silver_columns_have_one_entry_per_event_and_related_events_are_resolved():
    events = [ev("Pass", 1, x=70, end_x=85, quals=("KeyPass", ("Length", 15.5), ("Zone", "Center")), eid=5),
              ev("Goal", 2, x=90, quals=("Assisted", ("RelatedEventId", 5)), isGoal=True, isShot=True, eid=6),
              ev("Save", 20, team=AWAY, x=2, quals=(("OppositeRelatedEvent", 6),), eid=7), end()]
    m = silver(events)
    assert all(len(col) == m.n for col in m.ev.values()) and set(m.ev) == set(SV.COLUMNS)
    assert m.ev["rs"][1] == 0 and m.ev["ro"][2] == 1          # the goal points at its pass; the save at the shot, on the other side
    assert m.ev["ln"][0] == 155 and m.ev["z"][0] == 3 and m.ev["x"][0] == 700 and m.ev["ex"][0] == 850
    assert m.has_flag(0, "KeyPass") and not m.has_flag(0, "Longball") and m.row(0)["type"] == "Pass"


def test_silver_is_a_pure_function_of_the_raw_document_and_json_safe():
    import json

    events = [ev("Pass", 1, quals=("KeyPass",)), ev("Pass", 2, quals=("Longball",)), end()]
    a, b = SV.parse_match(match(events), league="EPL", season=2025, game_id=1), SV.parse_match(match(events), league="EPL", season=2025, game_id=1)
    assert a == b and json.loads(json.dumps(a)) == a
    assert SV.parse_match({"events": []}) is None and SV.parse_match({"events": [{}], "home": {}, "away": {}}) is None


def test_lineups_give_start_bench_and_timing_and_unknown_qualifiers_are_reported_not_lost():
    events = [ev("Pass", 1, quals=("BrandNewQualifier",)), ev("SubstitutionOff", 2, minute=60), ev("SubstitutionOn", 3, minute=60), end(100)]
    m = silver(events, home_players=[player(1), player(2), player(3, start=False)])
    by = m.by_id
    assert by[1]["start"] and by[2]["off"] == 60 and by[3]["on"] == 60 and not by[3]["start"] and by[2]["rating"] == 6.5
    assert m.doc["unknown"] == ["BrandNewQualifier"] and m.info["full_time"] == 100 and m.info["referee"] == "A. Ref"
