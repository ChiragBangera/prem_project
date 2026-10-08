"""Pitch maps: which events land on which layer, in which direction, with which flags, and that a payload stays small."""

from __future__ import annotations

import itertools

from app.events import maps as M

from .events_kit import AWAY, end, ev, player, silver


def fixture():
    """Home: 1 (central mid), 2 (winger), 5 (keeper). Away: 9. Every event is chosen to land on exactly one layer."""
    events = [
        ev("Pass", 1, x=30, y=50, end_x=60, end_y=50, minute=1),                                            # progressive, stays out of the final third
        ev("Pass", 1, x=60, y=50, end_x=70, end_y=50, minute=2),                                            # progressive, enters the final third
        ev("Pass", 1, x=75, y=40, end_x=90, end_y=50, minute=3, quals=("KeyPass",)),                        # key pass into the box
        ev("Pass", 2, x=80, y=5, end_x=90, end_y=50, minute=4, quals=("Cross",)),                           # cross into the box: never "progressive"
        ev("Pass", 1, x=20, y=50, end_x=60, end_y=50, minute=5, quals=("Longball",)),                       # long
        ev("Pass", 1, x=50, y=50, end_x=70, end_y=50, minute=6, quals=("Throughball",)),                    # through ball
        ev("Pass", 1, x=0, y=100, end_x=30, end_y=70, minute=7, quals=("ThrowIn",)),                        # a restart: drawn, but not counted
        ev("Pass", 1, x=40, y=50, end_x=45, end_y=50, minute=8, outcome=0),                                  # incomplete
        ev("Pass", 1, x=40, y=50, end_x=None, end_y=None, minute=9),                                         # no end point recorded: unusable, skipped
        ev("Tackle", 1, x=40, y=60, minute=10),
        ev("Interception", 1, x=35, y=45, minute=11),
        ev("Clearance", 1, x=10, y=50, minute=12),
        ev("BallRecovery", 2, x=50, y=20, minute=13),
        ev("Aerial", 1, x=20, y=50, minute=14, quals=("Defensive",)),                                       # defensive aerial: counts
        ev("Aerial", 1, x=70, y=50, minute=15, quals=("Offensive",)),                                       # offensive aerial: not a defensive action
        ev("Save", 5, x=3, y=50, minute=16),                                                                # keeper save
        ev("Save", 2, x=5, y=50, minute=17, quals=("OutfielderBlock",)),                                    # a block by an outfielder
        ev("TakeOn", 2, x=70, y=30, minute=18),
        ev("Pass", 9, team=AWAY, x=30, y=50, end_x=60, end_y=50, minute=19),                                # the other side
        ev("Tackle", 9, team=AWAY, x=40, y=60, minute=20),
        end(),
    ]
    return silver(events, home_players=[player(1), player(2, position="AMR"), player(5, position="GK")], away_players=[player(9, team_side="away")])


def layer(**selection):
    return M.collect([(3, fixture())], M.Selection(**selection))


def test_passes_carry_the_flags_a_viewer_filters_on_and_use_display_coordinates():
    passes = {tuple(p[:4]): p for p in layer(player=1)["passes"]}
    assert len(passes) == 7                                                                       # the one with no end point is gone
    prog = passes[(300, 500, 600, 500)]
    assert prog[5] == M.PF_PROG and prog[4] == 1 and prog[6] == 1 and prog[7] == 3               # flags, outcome, minute, the match index shown on the map
    assert passes[(600, 500, 700, 500)][5] == M.PF_PROG | M.PF_F3
    assert passes[(750, 600, 900, 500)][5] == M.PF_PROG | M.PF_KEY | M.PF_BOX                       # y is flipped: the pitch is drawn with the left wing on top
    assert passes[(200, 500, 600, 500)][5] & M.PF_LONG and passes[(500, 500, 700, 500)][5] & M.PF_THROUGH
    assert passes[(0, 0, 300, 300)][5] == M.PF_RESTART                                              # a throw-in: kept for the picture, flagged so it can be hidden
    assert passes[(400, 500, 450, 500)][4] == 0 and passes[(400, 500, 450, 500)][5] == 0


def test_a_cross_is_not_progressive_even_when_it_gains_ground():
    cross = next(p for p in layer(player=2)["passes"] if p[5] & M.PF_CROSS)
    assert cross[5] == M.PF_CROSS | M.PF_BOX and not cross[5] & M.PF_PROG


def test_counts_exclude_restarts_and_unusable_passes_and_grids_count_touches():
    out = layer(player=1)
    assert out["n"]["passes"] == 6 and out["n"]["pass_ok"] == 5                                    # 7 drawn, minus the throw-in; 5 of those 6 completed
    assert sum(out["touches"]) == out["n"]["touches"] > 0 and len(out["touches"]) == M.NX * M.NY
    assert sum(out["pass_from"]) == 5                                                              # where completed open-play passes started
    assert out["touches"][M._cell(300, 500)] >= 1                                                  # the first pass began in the middle third, central lane


def test_a_player_selection_takes_only_that_player_and_a_team_selection_takes_the_team():
    one, team = layer(player=1), layer(team="Reds")
    assert len(team["passes"]) == len(one["passes"]) + 1                                           # the winger's cross
    assert not layer(team="Nobody FC")["passes"] and layer(team="Nobody FC")["n"]["touches"] == 0  # a team that was not in the match contributes nothing
    other = layer(team="Blues")
    assert len(other["passes"]) == 1 and other["passes"][0][:4] == [300, 500, 600, 500] and len(other["def"]) == 1       # the opponent attacks the same way: every team goes left to right
    assert layer(player=424242)["passes"] == []                                                    # an unknown player is an empty map, not an error


def test_defensive_actions_are_typed_and_goalkeeper_actions_are_kept_apart():
    team = layer(team="Reds")
    kinds = sorted(d[2] for d in team["def"])
    assert kinds == sorted([M.D_TACKLE, M.D_INTERCEPT, M.D_CLEAR, M.D_RECOVER, M.D_AERIAL, M.D_BLOCK_SHOT])    # the offensive aerial is not a defensive action
    assert team["n"]["def"] == 6 and sum(team["def_grid"]) == 6 and sum(team["recover_grid"]) == 1
    assert [g[2] for g in team["gk"]] == [M.G_SAVE] and team["gk"][0][:2] == [30, 500]                  # the keeper's save, not the outfielder's block
    assert [t[:3] for t in team["takeons"]] == [[700, 700, 1]]


def test_carries_come_from_the_gaps_between_a_players_touches_and_flag_progressive_ones():
    events = [ev("Pass", 2, x=20, y=50, end_x=22, end_y=50, minute=1, second=0), ev("Pass", 1, x=40, y=50, end_x=50, end_y=50, minute=1, second=5), ev("Tackle", 9, team=AWAY, x=10, y=10, minute=3), end()]
    m = silver(events, home_players=[player(1), player(2)], away_players=[player(9, team_side="away")])
    carries = M.collect([(1, m)], M.Selection(player=1))["carries"]
    assert len(carries) == 1 and carries[0][:4] == [220, 500, 400, 500] and carries[0][4] == 1      # 18 units ~ 19 m up the pitch ending in the attacking 60 %: progressive


def test_thinning_is_even_deterministic_and_never_exceeds_the_cap():
    items = list(range(1000))
    a, b = M.thin(items, 100), M.thin(items, 100)
    assert a == b and len(a) == 100 and a[0] == 0 and a[-1] >= 980 and all(x < y for x, y in itertools.pairwise(a))
    assert M.thin(items[:5], 100) == items[:5]


def test_a_big_selection_is_capped_so_the_payload_stays_small():
    events = [ev("Pass", 1, x=10 + i % 80, y=10 + i % 70, end_x=20 + i % 70, end_y=15 + i % 60, minute=1 + i % 90) for i in range(4000)] + [end()]
    m = silver(events, home_players=[player(1)], away_players=[player(9, team_side="away")])
    out = M.collect([(1, m)], M.Selection(player=1))
    assert len(out["passes"]) <= M.MAX_LINES * 3 and out["n"]["passes"] == 4000                        # the line sample is capped; the count is not
    assert len(M.lines_view(out)) <= M.MAX_LINES


def test_lines_view_picks_by_flag_and_hides_restarts_unless_asked():
    out = layer(player=1)
    assert len(M.lines_view(out)) == 6                                                              # every open-play pass, restarts hidden
    assert len(M.lines_view(out, flags=M.PF_RESTART)) == 1
    assert {tuple(p[:4]) for p in M.lines_view(out, flags=M.PF_KEY | M.PF_F3)} == {(750, 600, 900, 500), (600, 500, 700, 500), (500, 500, 700, 500)}      # any of the flags (the through ball also enters the final third)
    assert len(M.lines_view(out, limit=2)) == 2


def test_lines_view_can_keep_only_completed_or_only_lost_passes_and_thins_after_choosing():
    out = layer(player=1)
    every, lost, done = M.lines_view(out), M.lines_view(out, ok=False), M.lines_view(out, ok=True)
    assert len(lost) + len(done) == len(every) and all(not p[4] for p in lost) and all(p[4] for p in done)
    assert len(M.lines_view(out, ok=False, limit=1)) <= 1
    big = [ev("Pass", 1, x=10 + i % 80, y=10 + i % 70, end_x=20 + i % 70, end_y=15 + i % 60, minute=1 + i % 90, outcome=1 if i % 10 else 0) for i in range(4000)] + [end()]
    out = M.collect([(1, silver(big, home_players=[player(1)], away_players=[player(9, team_side="away")]))], M.Selection(player=1))
    sample_lost = sum(1 for p in M.lines_view(out, limit=600) if not p[4])
    assert len(M.lines_view(out, ok=False, limit=600)) > sample_lost * 2                              # a map of lost passes alone has far more than a few left over from a mixed sample


def test_the_pass_network_needs_enough_passing_and_says_who_gave_it_to_whom():
    events = []
    for i in range(30):                                                                             # 1 -> 2 -> 1 -> 2 ..., three seconds apart, with a third player who barely touches the ball
        events.append(ev("Pass", 1 if i % 2 == 0 else 2, x=40, y=50, end_x=50, end_y=50, minute=1 + (i * 3) // 60, second=(i * 3) % 60))
    events.append(ev("Pass", 3, x=10, y=10, end_x=12, end_y=10, minute=40))
    events.append(end())
    m = silver(events, home_players=[player(1), player(2), player(3)], away_players=[player(9, team_side="away")])
    net = M.pass_network([(1, m)], "Reds")
    assert net["matches"] == 1 and {n["id"] for n in net["nodes"]} == {1, 2}                         # the bit-part player is left off: too few touches to place him
    assert [(e["a"], e["b"]) for e in net["edges"]] == [(1, 2)] and net["edges"][0]["n"] == 29
    assert all(0 <= n["x"] <= 1000 and 0 <= n["y"] <= 1000 for n in net["nodes"]) and net["nodes"][0]["touches"] >= 15
    assert M.pass_network([(1, m)], "Nobody FC") == {"nodes": [], "edges": [], "matches": 0}


def test_an_opponent_touch_ends_a_move_so_nothing_is_credited_across_it():
    events = []
    for i in range(20):
        events += [ev("Pass", 1, x=40, y=50, end_x=50, end_y=50, minute=1 + i, second=0), ev("Tackle", 9, team=AWAY, x=50, y=50, minute=1 + i, second=2), ev("Pass", 2, x=50, y=50, end_x=60, end_y=50, minute=1 + i, second=6)]
    events.append(end())
    m = silver(events, home_players=[player(1), player(2)], away_players=[player(9, team_side="away")])
    assert M.pass_network([(1, m)], "Reds")["edges"] == []


def test_zone_shares_split_touches_into_thirds_and_lanes():
    out = layer(team="Reds")
    shares = M.zone_shares(out)
    assert sum(shares["thirds"]) == sum(shares["lanes"]) == out["n"]["touches"] and len(shares["thirds"]) == len(shares["lanes"]) == 3
    assert shares["thirds"][0] > 0 and shares["thirds"][2] > 0
    empty = M.zone_shares({"touches": [0] * (M.NX * M.NY)})
    assert empty == {"thirds": [0, 0, 0], "lanes": [0, 0, 0]}
