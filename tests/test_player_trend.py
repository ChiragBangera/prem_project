"""One player's season, match by match: the three lines of every metric, the opponent behind each match, the splits, and the route that serves them.

A hand-built league (four clubs, twelve fixtures) has numbers that can be checked on paper; the demo world checks the property that matters most:
the last point of every season-to-date line is the number on his profile.
"""

from __future__ import annotations

import pytest
from app.analytics.player_trend import build_trend, his_matches, opponent_context, role_reference, tier_bounds
from app.analytics.players import applies
from app.data.models import MatchPage, RosterEntry
from app.data.normalize import normalize_league
from app.metrics.player import PLAYER_METRICS
from app.metrics.registry import SEASON_LONG

from .conftest import raw_league

BO, CY, OTHER = 102, 103, 999     # Bo plays for Alpha FC all season; Cy moves from Beta United to Gamma City; Other is somebody else


def entry(pid: int, minutes: int, *, position: str = "MC", venue: str = "h", **counters) -> RosterEntry:
    base = {"player_id": pid, "player": f"Player {pid}", "position": position, "minutes": minutes, "goals": 0, "own_goals": 0, "shots": 0, "xg": 0.0, "key_passes": 0,
            "assists": 0, "xa": 0.0, "xgchain": 0.0, "xgbuildup": 0.0, "yellow": 0, "red": 0, "venue": venue}
    return RosterEntry(**{**base, **counters})


def page(fixture_id: int, *, home: tuple = (), away: tuple = ()) -> MatchPage:
    return MatchPage(id=fixture_id, shots={"h": [], "a": []}, rosters={"h": list(home), "a": list(away)})


@pytest.fixture(scope="module")
def league():
    return normalize_league(raw_league(played=True), "EPL", 2025)


def bo_pages() -> dict[int, MatchPage]:
    """Alpha FC's six matches, in order: home v Delta 1000, away at Gamma 1002, home v Beta 1004, away at Delta 1006, home v Gamma 1008, away at Beta 1010."""
    return {
        1000: page(1000, home=(entry(BO, 90, shots=2, xg=0.6, key_passes=3),)),                                  # a full match
        1002: page(1002, away=(entry(BO, 30, position="Sub", venue="a", shots=1, xg=0.3, key_passes=1),)),       # off the bench
        # 1004: no page stored
        1006: page(1006, away=(entry(OTHER, 90, venue="a"),)),                                                   # a page, and he is not in it
        1008: page(1008, home=(entry(BO, 10, position="Sub", shots=3, xg=0.9),)),                                # ten minutes
        1010: page(1010, away=(entry(BO, 90, venue="a", shots=4, xg=0.4, key_passes=2),)),                       # a full match
    }


def cy_pages() -> dict[int, MatchPage]:
    """Beta United (until round 3), then Gamma City: 1001 and 1008 have no page, the rest is his."""
    return {
        1003: page(1003, away=(entry(CY, 90, venue="a", shots=1, key_passes=1),)),                                # Beta at Delta
        1004: page(1004, away=(entry(CY, 90, venue="a", shots=3),)),                                              # Beta at Alpha
        1007: page(1007, away=(entry(CY, 60, venue="a", shots=2),)),                                              # Gamma at Beta
        1011: page(1011, home=(entry(CY, 90, shots=0),)),                                                         # Gamma v Delta
    }


# ---------------------------------------------------------------------- opponents


@pytest.mark.parametrize("n", range(2, 25))
def test_the_tiers_split_every_league_size_into_three_ranges_without_gaps_or_overlaps(n):
    ranks = sorted(rank for lo, hi in tier_bounds(n).values() for rank in range(lo, hi + 1))
    assert ranks == list(range(1, n + 1))


def test_tiers_for_the_leagues_the_app_covers():
    assert tier_bounds(20) == {"top": (1, 6), "mid": (7, 14), "bottom": (15, 20)}
    assert tier_bounds(18) == {"top": (1, 5), "mid": (6, 13), "bottom": (14, 18)}


def test_every_club_gets_a_strength_tier_and_attack_and_defence_ranks(league):
    ctx = opponent_context(league)
    assert set(ctx) == set(league.teams) and all(c["n_teams"] == 4 for c in ctx.values())
    for key in ("rank", "rank_xpts", "attack_rank", "defence_rank"):
        assert sorted(c[key] for c in ctx.values()) == [1, 2, 3, 4]
    assert {c["tier"] for c in ctx.values()} == {"top", "mid", "bottom"}
    assert ctx["Beta United"]["tier"] == "top" and ctx["Alpha FC"]["tier"] == "bottom"      # strength is by expected points, not by the points the table shows


# ---------------------------------------------------------------------- his matches


def test_a_player_who_stayed_has_all_of_his_clubs_matches_and_those_he_did_not_play_are_kept_as_gaps(league):
    got = his_matches(BO, league, bo_pages())
    assert [f.id for f, *_ in got] == [1000, 1002, 1004, 1006, 1008, 1010]
    assert [side for _f, side, *_ in got] == ["h", "a", "h", "a", "h", "a"]
    assert [p is not None for _f, _s, p, _e in got] == [True, True, False, True, True, True]          # 1004 has no stored page
    assert [e is not None for *_x, e in got] == [True, True, False, False, True, True]                # and in 1006 he is not in the page


def test_a_player_who_moved_has_each_clubs_matches_from_where_he_actually_played(league):
    got = his_matches(CY, league, cy_pages())
    assert [f.id for f, *_ in got] == [1001, 1003, 1004, 1007, 1008, 1011]
    assert [side for _f, side, *_ in got] == ["a", "a", "a", "a", "a", "h"]
    assert [e is not None for *_x, e in got] == [False, True, True, True, False, True]
    # Gamma's 1002 and 1005 were played before he joined them: not his matches. 1008 was after, so it is, as a match he did not play


def test_nobody_is_drawn_without_a_single_appearance(league):
    assert his_matches(BO, league, {}) == []
    assert his_matches(BO, league, {1006: bo_pages()[1006]}) == []


# ---------------------------------------------------------------------- the three lines


def test_each_match_the_season_so_far_and_his_recent_form(league):
    out = build_trend(BO, league, bo_pages(), group="MID", name="Bo Playmaker", team="Alpha FC", window=2)
    assert out["available"] and out["coverage"] == {"matches": 6, "played": 4, "pages": 5, "events": 0}
    s = out["series"]["shots90"]
    assert s["m"] == [2.0, 3.0, None, None, 27.0, 4.0]                                  # shots × 90 ÷ minutes, a match at a time; blank where he did not play
    assert s["n"] == [90.0, 30.0, None, None, 10.0, 90.0]                               # the minutes behind each bar, so a ten-minute cameo can be shown as thin
    assert s["c"] == [2.0, 2.25, 2.25, 2.25, 4.154, 4.091]                              # 3 in 120, 6 in 130, 10 in 220 minutes; a match with no page changes nothing
    assert s["r"] == [2.0, 2.25, 2.25, 2.25, 9.0, 6.3]                                  # his last two appearances: 4 in 40 minutes, then 7 in 100
    kp = out["series"]["kp90"]
    assert kp["c"][-1] == pytest.approx(6 * 90 / 220, abs=0.001)                        # the same formula as his profile, over the same counters


def test_what_a_match_says_about_the_opponent(league):
    out = build_trend(BO, league, bo_pages(), group="MID", team="Alpha FC")
    rows = out["matches"]
    assert [(m["opp"], m["home"], m["result"], m["gf"], m["ga"]) for m in rows] == [
        ("Delta Town", True, "l", 0, 1), ("Gamma City", False, "l", 1, 2), ("Beta United", True, "d", 1, 1),
        ("Delta Town", False, "w", 1, 0), ("Gamma City", True, "w", 2, 1), ("Beta United", False, "d", 1, 1)]
    assert [m["opp_short"] for m in rows] == ["DEL", "GAM", "BET", "DEL", "GAM", "BET"]
    assert [m["opp_ctx"]["tier"] for m in rows] == ["mid", "mid", "top", "mid", "mid", "top"]
    assert [m["played"] for m in rows] == [True, True, False, False, True, True] and [m["minutes"] for m in rows] == [90, 30, 0, 0, 10, 90]
    assert [m["started"] for m in rows] == [True, False, None, None, False, True]
    assert [m["page"] for m in rows] == [True, True, False, True, True, True]
    assert [m["i"] for m in rows] == list(range(6)) and [m["match_id"] for m in rows] == [1000, 1002, 1004, 1006, 1008, 1010]
    assert out["tiers"] == {"top": [1, 1], "mid": [2, 3], "bottom": [4, 4]}


def test_before_his_first_appearance_there_is_no_season_and_no_form_only_the_match_he_did_not_play(league):
    out = build_trend(CY, league, cy_pages(), group="MID", team="Beta United")
    s = out["series"]["shots90"]
    assert [m["played"] for m in out["matches"]] == [False, True, True, True, False, True]
    assert s["m"] == [None, 1.0, 3.0, 3.0, None, 0.0]                                  # 2 in 60 minutes is 3 per 90; the last match was a blank shot sheet, which is zero
    assert s["c"] == [None, 1.0, 2.0, 2.25, 2.25, 1.636] and s["r"][0] is None and s["r"][1] == 1.0


def test_a_match_without_event_data_is_unknown_not_zero_and_leaves_the_season_alone(league):
    events = {1003: {"min": 90, "tackles": 3}, 1004: {"min": 90, "tackles": 1}, 1011: {"min": 90, "tackles": 5}}      # nothing is stored for 1007
    out = build_trend(CY, league, cy_pages(), group="DEF", team="Beta United", event_counters=lambda fixture: events.get(fixture))
    s = out["series"]["tackles90"]
    assert s["m"] == [None, 3.0, 1.0, None, None, 5.0]
    assert s["c"] == [None, 3.0, 2.0, 2.0, 2.0, 3.0]                                   # 1007 neither adds a zero nor dilutes what he did in the matches that have data
    assert [m["events"] for m in out["matches"]] == [False, True, True, False, False, True] and out["coverage"]["events"] == 3
    assert out["series"]["shots90"]["c"][-1] == 1.636                                  # the Understat lines do not care that the events are incomplete


def test_a_metric_with_nothing_stored_behind_it_is_left_out_rather_than_sent_as_blanks(league):
    out = build_trend(BO, league, bo_pages(), group="MID")                              # no event data at all
    assert "tackles90" not in out["series"] and "tackles90" not in out["keys"] and "pass_acc" not in out["keys"]
    assert out["keys"] and set(out["keys"]) == set(out["series"])


def test_only_metrics_that_mean_something_for_one_match_and_his_role_are_offered(league):
    out = build_trend(BO, league, bo_pages(), group="MID")
    assert not SEASON_LONG & set(out["keys"])                                        # an age, a season-long z-score, appearances: not a line
    by_key = {m.key: m for m in PLAYER_METRICS}
    assert all(applies(by_key[k], "MID") for k in out["keys"])


def test_the_splits_are_the_formula_over_the_pooled_minutes_not_an_average_of_matches(league):
    out = build_trend(BO, league, bo_pages(), group="MID")
    venue, tier = out["splits"]["venue"], out["splits"]["tier"]
    assert (venue["home"]["matches"], venue["home"]["minutes"], venue["home"]["v"]["shots90"]) == (2, 100, 4.5)       # 5 shots in 100 minutes; the mean of 2 and 27 would be 14.5
    assert (venue["away"]["matches"], venue["away"]["minutes"], venue["away"]["v"]["shots90"]) == (2, 120, 3.75)
    assert (tier["top"]["matches"], tier["top"]["minutes"], tier["top"]["v"]["shots90"]) == (1, 90, 4.0)             # 1004 v Beta has no page: it is not here
    assert (tier["mid"]["matches"], tier["mid"]["minutes"], tier["mid"]["v"]["shots90"]) == (3, 130, 4.154)
    assert tier["bottom"]["matches"] == 0 and tier["bottom"]["v"]["shots90"] is None                                  # he never met a bottom side: blank, not zero


def test_nothing_is_drawn_when_no_stored_page_has_him_in_it(league):
    out = build_trend(BO, league, {}, group="MID")
    assert out["available"] is False and out["matches"] == [] and "stored match page" in out["reason"]
    assert build_trend(BO, league, {1006: bo_pages()[1006]}, group="MID")["available"] is False


# ---------------------------------------------------------------------- what is typical for the role


def test_the_role_band_is_the_middle_half_of_the_peers_who_played_enough():
    rows = [{"group": "MID", "in_pool": True, "shots90": float(v)} for v in range(1, 11)]
    rows += [{"group": "MID", "in_pool": False, "shots90": 100.0}, {"group": "ATT", "in_pool": True, "shots90": 100.0}, {"group": "MID", "in_pool": True, "shots90": None}]
    ref = role_reference(rows, "MID", ["shots90", "kp90"], minimum=8)
    assert ref["shots90"] == {"n": 10, "p25": 3.25, "p50": 5.5, "p75": 7.75, "p90": 9.1}          # not the cameo men, not the other roles, not the blanks
    assert "kp90" not in ref                                                                     # nobody has a value
    assert role_reference(rows, "MID", ["shots90"], minimum=11) == {}                            # too few peers to call anything typical
