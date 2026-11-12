"""Moves summed over matches: how a team's end, where the ball is lost, who lost it and who took it. Counted by hand on one small match."""

from __future__ import annotations

from app.events import movestats as MS
from app.events.possessions import build_possessions

from .events_kit import AWAY, end, ev, player, silver


def match():
    """Reds (home, players 1-4) have three moves, Blues (away, 9) one:
    1. kick-off, three passes, a goal;
    2. a throw-in in the middle third, then 2 is tackled by 9 in the final third (x=70);
    3. Blues' move: 9 passes, 3 cuts it out in Reds' own third;
    4. Reds from there: one pass that finds nobody, picked up by 9."""
    return silver([
        ev("Pass", 1, x=50, y=50, end_x=30, end_y=50, minute=0, second=0),
        ev("Pass", 2, x=30, y=50, end_x=70, end_y=40, minute=0, second=3),
        ev("Pass", 3, x=70, y=40, end_x=90, end_y=50, minute=0, second=6, quals=("KeyPass",)),
        ev("Goal", 4, x=90, y=50, minute=0, second=8, isShot=True, isGoal=True),
        ev("Pass", 1, x=45, y=10, end_x=65, end_y=30, minute=5, second=0, quals=("ThrowIn",)),
        ev("Dispossessed", 2, x=70, y=30, minute=5, second=3),
        ev("Tackle", 9, team=AWAY, x=30, y=70, minute=5, second=3),
        ev("Pass", 9, team=AWAY, x=30, y=70, end_x=75, end_y=50, minute=5, second=5, outcome=0),
        ev("Interception", 3, x=25, y=50, minute=5, second=7),
        ev("Pass", 3, x=25, y=50, end_x=45, end_y=50, minute=5, second=9, outcome=0),
        ev("BallRecovery", 9, team=AWAY, x=55, y=50, minute=5, second=11),
        ev("Pass", 9, team=AWAY, x=55, y=50, end_x=60, end_y=50, minute=5, second=13),
        end(),
    ], home_players=[player(i, name=f"Red {i}") for i in (1, 2, 3, 4)], away_players=[player(9, team_side="away", name="Blue 9")])


def test_the_moves_are_what_the_match_page_lists():
    assert [(m["tm"], m["st"], m["end"]) for m in build_possessions(match())][:4] == [(0, "kickoff", "goal"), (0, "throw_in", "lost"), (1, "tackle", "lost"), (0, "interception", "lost")]


def test_a_teams_moves_by_how_they_end_where_they_began_and_who_was_on_the_ball():
    out = MS.team_moves([match()], "Reds")
    assert (out["n"], out["matches"], out["shot"]) == (3, 1, 1)
    assert out["ends"] == {"shot": 1, "lost": 2, "gave": 0, "kept": 0, "other": 0}
    zones = {z["key"]: z for z in out["zones"]}
    assert (zones["mid"]["n"], zones["mid"]["shot"], zones["mid"]["lost"]) == (2, 1, 1)          # the kick-off and the throw-in
    assert (zones["own"]["n"], zones["own"]["shot"], zones["own"]["lost"]) == (1, 0, 1)          # the ball won in their own third
    assert {s["key"]: (s["n"], s["shot"]) for s in out["starts"]} == {"won": (1, 0), "throw_in": (1, 0), "kickoff": (1, 1)}
    assert [(p["name"], p["n"], p["own_half"]) for p in out["losers"]] == [("Red 2", 1, 0), ("Red 3", 1, 1)]
    assert [(p["name"], p["n"], p["how"]) for p in out["winners"]] == [("Red 3", 1, "interception")]
    assert sum(out["lost_grid"]) == 2 and len(out["lost_grid"]) == MS.NX * MS.NY
    assert MS.team_moves([match()], "Nobody")["n"] == 0


def test_a_players_part_in_the_moves_and_where_he_lost_and_won_the_ball():
    two = MS.player_moves([(0, match())], 2)
    assert (two["n"], two["shot"], two["lost_n"], two["won_n"]) == (2, 1, 1, 0)
    assert two["lost"] == [[700, 700, "tackle", 0]]                                              # where the tackle was, in his own direction of play
    assert [(z["key"], z["n"]) for z in two["lost_zone"]] == [("own", 0), ("mid", 0), ("final", 1)]
    three = MS.player_moves([(0, match())], 3)
    assert (three["lost_n"], three["won_n"]) == (1, 1) and three["lost_how"][0]["key"] in ("recovery", "pass")
    assert three["won"] == [[250, 500, "interception", 0]]                                       # deep in his own third, drawn on the left
    assert MS.player_moves([(0, match())], 77) == {"matches": 0, "n": 0, "shot": 0, "lost_n": 0, "won_n": 0, "lost": [], "won": [], "lost_how": [], "lost_zone": [
        {"key": "own", "label": "Own third", "n": 0}, {"key": "mid", "label": "Middle third", "n": 0}, {"key": "final", "label": "Final third", "n": 0}]}
