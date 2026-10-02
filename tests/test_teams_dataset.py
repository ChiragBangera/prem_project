"""The team dataset: every team metric of the registry, ranked inside the team's own league and season, blank where unknown."""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from app.analytics.teams import MIN_POOL_MATCHES, TeamInput, build_team_dataset, squad_ages
from app.data.normalize import normalize_league
from app.events import counters as C
from app.metrics.team import TEAM_METRICS

from .conftest import raw_league

EPL = ("Alpha FC", "Beta United", "Gamma City", "Delta Town")
LIGA = ("Real Uno", "Real Dos", "Real Tres", "Real Cuatro")


def season(league, season_year, teams, played=True):
    return normalize_league(raw_league(teams=teams, played=played), league, season_year)


def dataset(inputs):
    return build_team_dataset(inputs)


def row(ds, team):
    return next(r for r in ds.rows if r["team"] == team)


def events_for(names, matches=6, scale=1.0):
    """What the store's season roll-up gives for a team: counters for and against, in the shape ``TeamInput.events`` takes."""
    out = {}
    for k, name in enumerate(names):
        counters = {key: 0 for key in C.COUNTERS}
        counters.update({"passes": 500 * matches * scale + 10 * k, "pass_ok": 400 * matches * scale + 10 * k, "tackles": 18 * matches, "touches": 600 * matches})
        against = {key: 0 for key in C.COUNTERS}
        against.update({"passes": 400 * matches, "pass_ok": 300 * matches, "tackles": 15 * matches, "touches": 500 * matches})
        out[name] = {"c": counters, "a": against, "matches": matches, "formations": {"4-3-3": matches}, "managers": {f"Boss {k}": matches}}
    return out


def test_one_row_per_team_season_and_every_metric_key_is_declared():
    ds = dataset([TeamInput(season("EPL", 2025, EPL)), TeamInput(season("La_liga", 2025, LIGA))])
    assert len(ds.rows) == 8 and ds.keys == [m.key for m in TEAM_METRICS] and ds.leagues == ["EPL", "La_liga"] and ds.seasons == [2025]
    assert all(set(r["values"]) <= set(ds.keys) and set(r["pct"]) <= set(ds.keys) for r in ds.rows)
    assert {r["key"] for r in ds.rows} == {f"{lg}:2025:{t}" for lg, ts in (("EPL", EPL), ("La_liga", LIGA)) for t in ts}
    assert all(isinstance(k, str) and type(k) is str for k in ds.pools)                                  # plain strings: they go straight into JSON


def test_percentiles_compare_a_team_only_with_its_own_league_and_season():
    strong, weak = season("EPL", 2025, EPL), season("La_liga", 2025, LIGA)
    for team in weak.teams.values():                                                                      # a league in which every side scores and wins far more
        for m in team.history:
            m.gf, m.xg, m.pts = m.gf + 5, m.xg + 5, 3
    ds = dataset([TeamInput(strong), TeamInput(weak)])
    assert ds.pools == {"EPL:2025": 4, "La_liga:2025": 4}
    epl_best = max((r for r in ds.rows if r["league"] == "EPL"), key=lambda r: r["values"]["gf"])
    assert epl_best["pct"]["gf"] > 60                                                                    # best of its own four, even though every Spanish side outscores it
    assert row(ds, "Real Uno")["values"]["gf"] > epl_best["values"]["gf"]
    for league in ("EPL", "La_liga"):
        for key in ("gf", "ga", "xg_pg"):
            pcts = sorted(r["pct"][key] for r in ds.rows if r["league"] == league)
            assert pcts[0] < 50 < pcts[-1] or len(set(r["values"][key] for r in ds.rows if r["league"] == league)) == 1       # each league spreads over its own range
    a, b = row(ds, "Alpha FC"), row(ds, "Beta United")
    assert (a["values"]["ga"] < b["values"]["ga"]) == (a["pct"]["ga"] > b["pct"]["ga"])                  # fewer conceded reads as better: a higher percentile


def test_unknown_is_blank_not_zero_for_event_and_shot_metrics():
    ds = dataset([TeamInput(season("EPL", 2025, EPL))])
    r = ds.rows[0]
    assert "poss" not in r["values"] and "pass_acc" not in r["values"] and "tackles_pg" not in r["values"]    # no event data stored: nothing to show
    assert "shots_pg" not in r["values"] and not r["shots_ok"] and r["ev_matches"] == 0 and r["formation"] is None and r["manager"] is None
    assert "ppg" in r["values"] and "xg_pg" in r["values"]                                                # what Understat's history gives is always there
    assert ds.coverage == {"event_teams": 0, "teams": 4, "shot_teams": 0}


def test_event_metrics_show_for_the_teams_that_have_them_and_stay_blank_for_the_rest():
    ls = season("EPL", 2025, EPL)
    partial = events_for(EPL[:3])                                                                         # the fourth team has no stored events yet
    ds = dataset([TeamInput(ls, events=partial)])
    have, lacking = row(ds, "Alpha FC"), row(ds, "Delta Town")
    assert have["ev_matches"] == 6 and have["formation"] == "4-3-3" and have["manager"] == "Boss 0" and "pass_acc" in have["values"]
    assert have["values"]["pass_acc"] == pytest.approx(0.8, abs=0.001)
    assert lacking["ev_matches"] == 0 and "pass_acc" not in lacking["values"] and "pass_acc" not in lacking["pct"]
    assert ds.coverage["event_teams"] == 3


def test_event_percentiles_come_from_the_teams_that_have_them():
    ls = season("EPL", 2025, EPL)
    ds = dataset([TeamInput(ls, events=events_for(EPL))])
    pcts = {r["team"]: r["pct"]["pass_acc"] for r in ds.rows}
    assert pcts["Delta Town"] > pcts["Alpha FC"] and len(set(pcts.values())) == 4                         # the pass_acc gradient built into the fixture: more passes completed, higher rank
    three = dataset([TeamInput(ls, events=events_for(EPL[:3]))])
    assert not any("pass_acc" in r["pct"] for r in three.rows) and all("pass_acc" in r["values"] for r in three.rows if r["ev_matches"])     # three teams are not a league: the values show, nothing is ranked


def test_a_pool_needs_at_least_four_teams_to_rank_anyone():
    small = season("EPL", 2025, EPL[:3] + ("Epsilon",))
    del small.teams["Epsilon"]                                                                            # only three teams left with a history
    ds = dataset([TeamInput(small)])
    assert len(ds.rows) == 3 and ds.pools["EPL:2025"] == 3 and all(r["pct"] == {} for r in ds.rows)     # three teams do not make a ranking


def test_a_team_that_has_barely_played_is_shown_but_not_counted_in_the_pool():
    ls = season("EPL", 2025, EPL, played=2)                                                              # two matches played: fewer than the minimum to be ranked
    ds = dataset([TeamInput(ls)])
    assert MIN_POOL_MATCHES > 1 and all(not r["in_pool"] for r in ds.rows) and ds.pools == {"EPL:2025": 0}
    assert all(r["values"] for r in ds.rows)                                                              # their figures are still there to read


def test_shots_make_the_shooting_metrics_available_only_for_teams_with_complete_match_pages():
    ls = season("EPL", 2025, EPL)
    shot = lambda n: {"for": {"n": 12 * n, "goals": 1.0 * n, "xg": 1.4 * n, "sot": 4.0 * n}, "against": {"n": 10 * n, "goals": 1.0 * n, "xg": 1.1 * n, "sot": 3.0 * n}, "matches": n}  # noqa: E731
    ds = dataset([TeamInput(ls, shots={name: shot(6) for name in EPL[:2]})])
    with_shots, without = row(ds, "Alpha FC"), row(ds, "Gamma City")
    assert with_shots["shots_ok"] and with_shots["values"]["shots_pg"] == pytest.approx(12.0) and with_shots["values"]["sot_pg"] == pytest.approx(4.0)
    assert not without["shots_ok"] and "shots_pg" not in without["values"]
    assert ds.coverage["shot_teams"] == 2


def test_the_row_carries_what_the_table_and_the_team_page_show_around_the_numbers():
    ls = season("EPL", 2025, EPL)
    r = dataset([TeamInput(ls)]).rows[0]
    assert {"team", "short", "league", "season", "key", "rank", "rank_xpts", "form", "trend_xgd", "matches", "in_pool"} <= set(r)
    assert r["matches"] == 6 and 1 <= r["rank"] <= 4 and len(r["form"]) <= 6
    assert all(not math.isnan(v) and not math.isinf(v) for v in (*r["values"].values(), *r["pct"].values()))      # nothing that cannot be JSON


def test_squad_age_is_minutes_weighted_uses_only_confirmed_ages_and_leaves_out_unknowns():
    ls = season("EPL", 2025, EPL)

    def player(pid, team, minutes):
        return replace(ls.players[0], id=pid, name=f"P{pid}", teams=[team], minutes=minutes)

    ls.players = [player(1, "Alpha FC", 900), player(2, "Alpha FC", 300), player(3, "Alpha FC", 600), player(4, "Beta United", 40)]
    ages = {1: 20, 2: 30, 3: None, 4: 25}
    out = squad_ages(ls, lambda p: ages[p.id])
    assert out == {"Alpha FC": pytest.approx((20 * 900 + 30 * 300) / 1200)}                                 # the player with no confirmed age is not guessed at, and a team with too little evidence is left out
    assert dataset([TeamInput(ls, ages=out)]).rows[0]["values"].get("squad_age") is not None
