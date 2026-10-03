"""Stored Understat match pages: scorers, positions, shot aggregates, and the bulk fetcher's policy (what to fetch, when a page is final)."""

from __future__ import annotations

import asyncio

import pytest

from app.analytics import matchsum as M
from app.data.matchbook import MatchBook
from app.data.matchsync import SETTLE_HOURS, MatchSync
from app.data.models import Fixture, MatchPage, RosterEntry, Shot
from app.data.normalize import normalize_league, normalize_match_page
from app.errors import UpstreamError

from .conftest import raw_league, raw_match_page


def shot(minute, xg, result, side, player="P", pid=1, x=0.9, y=0.5, situation="OpenPlay", shot_type="RightFoot", assist=None):
    return Shot(id=minute, minute=minute, xg=xg, result=result, x=x, y=y, situation=situation, shot_type=shot_type, last_action="Pass", player=player, player_id=pid, venue=side,
                season=2025, match_id=1, home="Reds", away="Blues", date="2025-08-16", assisted_by=assist)


def roster(pid, name, pos, minutes, side="h", **kw):
    base = {"player_id": pid, "player": name, "position": pos, "minutes": minutes, "goals": 0, "own_goals": 0, "shots": 0, "xg": 0.0, "key_passes": 0, "assists": 0, "xa": 0.0, "xgchain": 0.0, "xgbuildup": 0.0, "yellow": 0, "red": 0, "venue": side}
    base.update(kw)
    return RosterEntry(**base)


def page(shots_h=(), shots_a=(), rosters_h=(), rosters_a=()):
    return MatchPage(id=1, shots={"h": list(shots_h), "a": list(shots_a)}, rosters={"h": list(rosters_h), "a": list(rosters_a)})


# ------------------------------------------------------------------ scorers


def test_scorers_credit_goals_penalties_and_own_goals_to_the_right_side_in_match_order():
    p = page(
        shots_h=[shot(70, 0.7, "Goal", "h", "Ann", 1, situation="Penalty"), shot(10, 0.3, "Goal", "h", "Bo", 2, assist="Cy"), shot(40, 0.1, "SavedShot", "h", "Bo", 2),
                 shot(55, 0.0, "OwnGoal", "h", "Hapless", 9)],      # an own goal carries the scorer's own side: it counts for the away team
        shots_a=[shot(20, 0.4, "Goal", "a", "Dee", 3)],
    )
    s = M.scorers(p)
    assert [(g["player"], g["minute"], g["kind"]) for g in s["h"]] == [("Bo", 10, "goal"), ("Ann", 70, "pen")]
    assert [(g["player"], g["minute"], g["kind"]) for g in s["a"]] == [("Dee", 20, "goal"), ("Hapless", 55, "og")]
    assert s["h"][0]["assist"] == "Cy" and s["a"][1]["assist"] is None
    summary = M.fixture_summary(Fixture(id=1, dt="2025-08-16 14:00:00", home="Reds", away="Blues", home_short="RED", away_short="BLU", played=True, hg=2, ag=2), p)
    assert summary["shots"] == {"h": 3, "a": 1} and summary["sot"] == {"h": 3, "a": 1}          # the own goal is not a shot
    assert M.sent_off(page(rosters_h=[roster(1, "A", "DC", 60, red=1), roster(2, "B", "GK", 90)])) == {"h": [{"player": "A", "id": 1}], "a": []}


# ------------------------------------------------------------------ positions


def test_positions_are_the_minutes_actually_started_at_each_one():
    p1 = page(rosters_h=[roster(1, "Rice", "DMC", 90), roster(2, "Sub", "Sub", 20), roster(3, "Bench", "Sub", 0)], rosters_a=[roster(4, "Away", "GK", 90, "a")])
    p2 = page(rosters_h=[roster(1, "Rice", "MC", 90), roster(2, "Sub", "Sub", 30)])
    p3 = page(rosters_h=[roster(1, "Rice", "MC", 75)])
    pm = M.position_minutes([p1, p2, p3])
    assert pm[1] == {"pos": {"DMC": 90, "MC": 165}, "starts": 3, "subs": 0} and M.modal_position(pm[1]["pos"]) == "MC"
    assert pm[2] == {"pos": {}, "starts": 0, "subs": 2}            # a substitute's position is not recorded: nothing is invented for him
    assert 3 not in pm and pm[4]["pos"] == {"GK": 90} and M.modal_position({}) is None


# ------------------------------------------------------------------ shot aggregates


def test_shot_aggregates_split_situations_body_parts_and_distance():
    shots = [
        shot(1, 0.76, "Goal", "h", pid=1, situation="Penalty", x=0.89),
        shot(2, 0.10, "SavedShot", "h", pid=1, x=0.92, y=0.5),                                  # in the box, on target
        shot(3, 0.05, "MissedShots", "h", pid=1, x=0.70, y=0.9, shot_type="Head"),                 # outside the box, a header
        shot(4, 0.40, "Goal", "h", pid=1, situation="FromCorner", shot_type="Head", x=0.95),
        shot(5, 0.02, "BlockedShot", "h", pid=1, situation="DirectFreekick", x=0.75),
        shot(6, 0.0, "OwnGoal", "h", pid=1),                                                         # not a shot
    ]
    t = M.player_shots([page(shots_h=shots)])[1]
    assert (t["n"], t["goals"], t["sot"], t["blocked"], t["off"]) == (5, 2, 3, 1, 1)
    assert t["pens"] == 1 and t["pen_goals"] == 1 and t["pen_xg"] == pytest.approx(0.76) and t["xg"] == pytest.approx(1.33)
    assert t["sp_shots"] == 2 and t["sp_xg"] == pytest.approx(0.42) and t["op_shots"] == 2 and t["op_xg"] == pytest.approx(0.15)    # the penalty is neither
    assert t["head"] == 2 and t["head_goals"] == 1 and t["fk"] == 1 and t["big"] == 2 and t["big_goals"] == 2
    assert t["box"] == 3 and t["xg_np"] == pytest.approx(0.57) and 8 < t["dist"] / t["n"] < 30


def test_team_shots_are_for_and_against():
    f = Fixture(id=1, dt="2025-08-16 14:00:00", home="Reds", away="Blues", home_short="RED", away_short="BLU", played=True, hg=1, ag=0)
    out = M.team_shots([(f, page(shots_h=[shot(1, 0.3, "Goal", "h")], shots_a=[shot(2, 0.1, "SavedShot", "a"), shot(3, 0.2, "MissedShots", "a")]))])
    assert out["Reds"]["for"]["n"] == 1 and out["Reds"]["against"]["n"] == 2 and out["Blues"]["for"]["xg"] == pytest.approx(0.3) and out["Blues"]["against"]["goals"] == 1


def test_a_players_season_log_is_in_date_order_with_his_team_and_minutes():
    pages = [(Fixture(id=2, dt="2025-08-23 14:00:00", home="Blues", away="Reds", home_short="BLU", away_short="RED", played=True, hg=0, ag=2), page(rosters_a=[roster(1, "A", "FW", 80, "a", goals=2, xg=1.1)])),
             (Fixture(id=1, dt="2025-08-16 14:00:00", home="Reds", away="Blues", home_short="RED", away_short="BLU", played=True, hg=1, ag=1), page(rosters_h=[roster(1, "A", "Sub", 15, xg=0.2)]))]
    log = M.season_log(pages, 1)
    assert [(r["date"], r["opponent"], r["home"], r["minutes"], r["goals"]) for r in log] == [("2025-08-16", "Blues", True, 15, 0), ("2025-08-23", "Blues", False, 80, 2)]
    assert log[1]["gf"] == 2 and log[1]["ga"] == 0


def test_real_shaped_payloads_round_trip_through_the_normalizer():
    p = normalize_match_page(raw_match_page(), 1000)
    s = M.scorers(p)
    assert [g["player"] for g in s["h"]] == ["Ann Striker"] and [g["player"] for g in s["a"]] == ["Eve Winger"]
    assert M.position_minutes([p]) == {101: {"pos": {"FW": 90}, "starts": 1, "subs": 0}, 201: {"pos": {"AMR": 90}, "starts": 1, "subs": 0}}


# ------------------------------------------------------------------ the bulk fetcher


def season(played=4):
    return normalize_league(raw_league(played=played), "EPL", 2025)


@pytest.fixture
def sync(repo, clock):
    ms = MatchSync(repo, clock=clock)
    clock.now = 1_757_000_000.0   # a few days after the fixtures' 2025-08/09 kickoffs
    return ms


def test_only_finished_matches_whose_page_is_missing_or_not_final_are_wanted(sync, repo, provider, clock):
    ls = season(played=4)
    assert [f.id for f in sync.pending(ls)] == [1000, 1001, 1002, 1003]       # nothing stored yet; the 8 unplayed fixtures are never asked for
    run = asyncio.run(sync.run(ls))
    assert run == {"fetched": 4, "failed": 0, "remaining": 0} and sorted(c for c in provider.calls if c[0] == "match") == [("match", 1000 + i) for i in range(4)]   # concurrent: the order is not defined
    assert sync.pending(ls) == [] and sync.coverage(ls) == (4, 4)
    again = asyncio.run(sync.run(ls))
    assert again["fetched"] == 0 and len([c for c in provider.calls if c[0] == "match"]) == 4          # a final page is never fetched twice


def test_a_page_fetched_too_soon_after_the_whistle_is_looked_at_again_once_it_has_settled(repo, provider, clock):
    ls = season(played=1)
    fixture = ls.played[0]
    kickoff = 1_755_356_400.0            # 2025-08-16 15:00 UTC
    clock.now = kickoff + 3 * 3600       # three hours after: Understat is still revising shots
    sync = MatchSync(repo, clock=clock)
    assert not sync.is_final(fixture)
    asyncio.run(sync.run(ls))
    assert repo.match_status(fixture.id) == (clock.now, False)                  # stored, but not for good
    assert sync.pending(ls) == []                                               # ...and not hammered: it is only revisited after the open-match window
    clock.advance(repo.settings.ttl_match_open + 1)
    assert [f.id for f in sync.pending(ls)] == [fixture.id]
    clock.now = kickoff + (SETTLE_HOURS + 1) * 3600
    assert sync.is_final(fixture)
    asyncio.run(sync.run(ls))
    assert repo.match_status(fixture.id)[1] is True and sync.pending(ls) == []   # now final: never again


def test_a_page_with_no_shots_for_a_match_that_had_chances_is_not_frozen_empty(repo, provider, clock):
    ls = season(played=1)
    clock.now = 1_757_000_000.0
    sync = MatchSync(repo, clock=clock)
    provider.match = lambda mid: _empty_page()
    asyncio.run(sync.run(ls))
    assert repo.match_status(ls.played[0].id)[1] is False                       # xG says there were shots; the page has none yet: ask again later


async def _empty_page():
    return {"shots": {"h": [], "a": []}, "rosters": {"h": {}, "a": {}}}


def test_one_failing_page_does_not_stop_the_rest_and_the_error_is_kept(sync, repo, provider):
    ls = season(played=4)
    original = provider.match

    async def flaky(mid):
        if mid == 1001:
            raise UpstreamError("Understat returned HTTP 500.", upstream_status=500)
        return await original(mid)

    provider.match = flaky
    run = asyncio.run(sync.run(ls))
    assert run == {"fetched": 3, "failed": 1, "remaining": 1} and "1001" in sync.last_error and sync.coverage(ls) == (3, 4)
    provider.match = original
    assert asyncio.run(sync.run(ls))["fetched"] == 1                             # the retry picks up only what is missing


def test_limit_and_stop_bound_a_run_and_offline_never_fetches(sync, repo, provider):
    ls = season(played=6)
    assert asyncio.run(sync.run(ls, limit=2))["fetched"] == 2 and sync.coverage(ls) == (2, 6)
    stop_after = iter([False, True, True, True])
    run = asyncio.run(MatchSync(repo, clock=sync._clock).run(ls, stop=lambda: next(stop_after)))
    assert run["fetched"] <= 4 and run["remaining"] == 6 - 2 - run["fetched"]
    repo.settings = type(repo.settings)(**{**repo.settings.__dict__, "offline": True})
    calls = len(provider.calls)
    assert asyncio.run(sync.run(ls)) == {"fetched": 0, "failed": 0, "remaining": len(sync.pending(ls))} and len(provider.calls) == calls


# ------------------------------------------------------------------ the book


def test_a_book_reads_only_what_is_stored_and_says_how_complete_it_is(sync, repo, provider):
    ls = season(played=4)
    book = MatchBook(repo)
    assert book.pages(ls) == {} and book.coverage(ls) == (0, 4) and not book.complete(ls)
    asyncio.run(sync.run(ls, limit=3))
    assert sorted(book.pages(ls)) == [1000, 1001, 1002] and book.coverage(ls) == (3, 4) and not book.complete(ls)
    asyncio.run(sync.run(ls))
    assert book.complete(ls) and [f.id for f, _p in book.fixtures_with_pages(ls)] == [1000, 1001, 1002, 1003]
    before = len(provider.calls)
    book.pages(ls)
    assert len(provider.calls) == before                                         # reading the book never touches the provider
    assert book.complete(ls, threshold=1.0) and not MatchBook(repo).complete(season(played=0))
