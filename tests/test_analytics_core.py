"""Statistics helpers, league tables, team profiles, matches, similarity and player detail."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.analytics.match import match_report
from app.analytics.player_detail import finishing, player_detail, zone_of
from app.analytics.players import build_dataset
from app.analytics.similarity import similar_players
from app.analytics.table import (
    compute_table,
    league_context,
    rank_trajectories,
    rolling,
    strengths,
    team_percentiles,
)
from app.analytics.chances import chance_insights, compare_to_league, league_baseline, prepare_breakdowns
from app.analytics.team import find_team, team_history, team_profile
from app.data.models import Shot
from app.data.normalize import normalize_match_page, normalize_player_page
from app.errors import NotFound
from app.stats import (
    outcome_probs,
    per90,
    percentile_rank,
    percentile_ranks,
    poisson_binomial,
    shot_luck,
    zscore,
)

# ------------------------------------------------------------------ stats


def test_poisson_binomial_exact_small_cases():
    assert list(poisson_binomial([])) == [1.0]
    assert list(poisson_binomial([0.5, 0.5])) == pytest.approx([0.25, 0.5, 0.25])
    pmf = poisson_binomial([0.9, 0.2, 0.05])
    assert pmf.sum() == pytest.approx(1.0) and pmf[0] == pytest.approx(0.1 * 0.8 * 0.95)


def test_outcome_probs_are_a_distribution_and_ordered():
    strong = poisson_binomial([0.4, 0.3, 0.3, 0.2, 0.1])
    weak = poisson_binomial([0.1, 0.05])
    h, d, a = outcome_probs(strong, weak)
    assert h + d + a == pytest.approx(1.0) and h > a
    h2, d2, a2 = outcome_probs(weak, strong)
    assert (h2, a2) == pytest.approx((a, h))


def test_shot_luck_flags_surprise_by_sample_size():
    few = shot_luck(3, [0.1] * 5)  # 3 goals from 0.5 xG
    many = shot_luck(30, [0.1] * 250)  # +5 over expectation, but on many shots
    assert few["p_at_least"] < 0.01 < many["p_at_least"] and few["z"] > many["z"] > 0
    assert shot_luck(0, [])["shots"] == 0


def test_percentile_rank_mid_rank_ties():
    sample = [1, 2, 2, 3, 4]
    assert percentile_rank(2, sample) == pytest.approx(100 * (1 + 1) / 5)
    assert percentile_rank(10, sample) == 100.0 and percentile_rank(0, sample) == 0.0
    assert percentile_rank(5, []) == 50.0
    assert percentile_ranks([10, 20, 30]) == pytest.approx([100 / 6, 50, 100 * 5 / 6])
    assert zscore(5, [1, 2, 3, 4, 5]) > 1 and per90(9, 450) == 1.8 and per90(1, 0) == 0.0


def test_rolling_mean_waits_for_a_full_window():
    assert rolling([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    assert rolling([5], 3) == [None]


# ------------------------------------------------------------------ table


def test_table_is_consistent_and_ranked(demo_league):
    table = compute_table(demo_league)
    assert [r["rank"] for r in table] == list(range(1, 21))
    for r in table:
        assert r["w"] * 3 + r["d"] == r["pts"] and r["w"] + r["d"] + r["l"] == r["played"] == 38
        assert r["gd"] == r["gf"] - r["ga"] and r["xgd"] == pytest.approx(r["xg"] - r["xga"])
        assert r["xpts_gap"] == pytest.approx(r["pts"] - r["xpts"])
    assert table == sorted(table, key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
    assert sorted(r["rank_xpts"] for r in table) == list(range(1, 21))
    assert sum(r["pts"] for r in table) == sum(r["pts"] for r in table)


def test_table_filters_partition_the_season(demo_league):
    overall = {r["team"]: r for r in compute_table(demo_league)}
    home = {r["team"]: r for r in compute_table(demo_league, venue="h")}
    away = {r["team"]: r for r in compute_table(demo_league, venue="a")}
    for team, row in overall.items():
        assert home[team]["pts"] + away[team]["pts"] == row["pts"]
        assert home[team]["xg"] + away[team]["xg"] == pytest.approx(row["xg"])
    last5 = compute_table(demo_league, last_n=5)
    assert all(r["played"] == 5 for r in last5)
    later = compute_table(demo_league, date_from="2020-01-01")
    assert all(0 < r["played"] < 38 for r in later)


def test_ppda_is_a_ratio_of_sums_not_a_mean_of_ratios(demo_league):
    team = next(iter(demo_league.teams.values()))
    row = next(r for r in compute_table(demo_league) if r["team"] == team.name)
    expected = sum(m.ppda_att for m in team.history) / sum(m.ppda_def for m in team.history)
    assert row["ppda"] == pytest.approx(expected)


def test_league_context_and_progress(demo_league, demo_league_partial):
    full = league_context(demo_league)
    assert full["complete"] and full["progress"] == 1.0 and full["rounds_played"] == 38 == full["rounds_total"]
    assert full["home_win"] + full["draw"] + full["away_win"] == pytest.approx(1.0)
    assert 2.4 < full["goals_pg"] < 3.4 and full["home_xg_edge"] > 0
    partial = league_context(demo_league_partial)
    assert not partial["complete"] and 0 < partial["progress"] < 1 and partial["next_kickoff"]


def test_rank_trajectories_end_at_the_final_table(demo_league):
    table = compute_table(demo_league)
    paths = rank_trajectories(demo_league)
    assert paths["rounds"] == 38
    for r in table:
        assert paths["rank"][r["team"]][-1] == r["rank"]
        assert paths["points"][r["team"]][-1] == r["pts"]
        assert paths["xpts"][r["team"]][-1] == pytest.approx(r["xpts"], abs=0.05)
        assert len(paths["rank"][r["team"]]) == 38
    first_round_ranks = sorted(p[0] for p in paths["rank"].values())
    assert first_round_ranks == list(range(1, 21))


def test_team_percentiles_orientation(demo_league):
    table = compute_table(demo_league)
    best = max(table, key=lambda r: r["xgd_pg"])
    percentiles = {p["key"]: p for p in team_percentiles(table, best["team"])}
    assert percentiles["xgd_pg"]["percentile"] > 90
    worst_defence = max(table, key=lambda r: r["xga_pg"])
    assert {p["key"]: p for p in team_percentiles(table, worst_defence["team"])}["xga_pg"]["percentile"] < 10  # lower is better
    assert len(percentiles) == 8 and team_percentiles(table, "Nobody") == []


# ------------------------------------------------------------------ team


def test_team_profile_shape_and_invariants(demo_league):
    top = compute_table(demo_league)[0]["team"]
    profile = team_profile(demo_league, top)
    assert profile["team"]["rank"] == 1 and len(profile["matches"]) == 38
    assert [m["n"] for m in profile["matches"]] == list(range(1, 39))
    splits = profile["splits"]
    assert splits["home"]["played"] + splits["away"]["played"] == 38
    assert splits["first_half"]["played"] + splits["second_half"]["played"] == 38
    assert splits["vs_stronger"]["played"] + splits["vs_weaker"]["played"] <= 38
    assert profile["cumulative"][-1]["pts"] == profile["team"]["pts"]
    assert profile["rank_path"][-1] == 1 and len(profile["rank_path"]) == 38
    assert sum(1 for v in profile["rolling"]["xg"] if v is None) == 4  # window of 5
    share = sum(p["share_npxg"] for p in profile["squad"])
    assert share == pytest.approx(1.0, abs=0.01)  # every chance belongs to a player
    assert profile["concentration"]["top1_share"] <= profile["concentration"]["top3_share"] <= 1
    assert all(m["opponent"] for m in profile["matches"])


def test_team_lookup_accepts_short_names_and_reports_unknowns(demo_league):
    arsenal = find_team(demo_league, "arsenal")
    assert arsenal.name == "Arsenal" and find_team(demo_league, "ARS").name == "Arsenal"
    with pytest.raises(NotFound):
        find_team(demo_league, "Not A Team")


def test_team_history_series_line_up_with_the_table(demo_league):
    top = compute_table(demo_league)[0]
    h = team_history(demo_league, top["team"])
    assert h["played"] == 38 and h["complete"] and h["n_teams"] == 20 and h["rounds_total"] == 38
    for key in ("points", "xpts_cum", "rank", "xg_cum", "xga_cum", "xgd_cum", "xgd_roll"):
        assert len(h[key]) == 38, key
    assert h["final_rank"] == h["rank"][-1] == 1
    assert h["points"][-1] == h["pts"] == top["pts"]
    assert all(b >= a for a, b in zip(h["points"], h["points"][1:]))  # points only ever go up
    assert h["xgd_cum"][-1] == pytest.approx(h["xg_cum"][-1] - h["xga_cum"][-1], abs=0.01) == pytest.approx(h["xgd"], abs=0.01)
    assert sum(1 for v in h["xgd_roll"] if v is None) == 4 and h["xgd_roll"][-1] is not None  # window of 5
    assert h["gd"] == top["gd"]


def test_team_history_of_a_season_in_progress_is_shorter(demo_league_partial):
    h = team_history(demo_league_partial, "Arsenal")
    assert not h["complete"] and h["played"] < h["rounds_total"]
    assert len(h["points"]) == len(h["rank"]) == len(h["xgd_cum"]) == h["played"]
    with pytest.raises(NotFound):
        team_history(demo_league_partial, "Not A Team")


def test_partial_season_team_profile_has_upcoming_and_schedule(demo_league_partial):
    profile = team_profile(demo_league_partial, "Arsenal")
    assert profile["upcoming"] and profile["schedule"]["remaining"] > 0
    first = profile["upcoming"][0]
    assert first["venue"] in ("h", "a") and abs(sum(first["forecast"].values()) - 1) < 1e-6
    assert profile["schedule"]["remaining_avg_opp"] is not None


def test_manager_eras_split_a_season(demo_league):
    team = demo_league.teams["Arsenal"]
    mid = team.history[19].date
    eras = [
        {"manager": "A. Boss", "team": "Arsenal", "start": "2019-01-01", "end": mid},
        {"manager": "B. Coach", "team": "Arsenal", "start": mid, "end": None},
        {"manager": "Somebody", "team": "Chelsea", "start": "2019-01-01", "end": None},
    ]
    splits = team_profile(demo_league, "Arsenal", eras=eras)["eras"]
    assert [s["manager"] for s in splits] == ["A. Boss", "B. Coach"]
    assert sum(s["played"] for s in splits) >= 38


def test_strengths_center_around_zero(demo_league):
    values = list(strengths(demo_league).values())
    assert abs(sum(values) / len(values)) < 0.05 and max(values) > 0.3 > -0.2 > min(values) - 0.5


# ------------------------------------------------------------------ match


def test_match_report_is_coherent(demo_provider, demo_league):
    fixture = demo_league.played[42]
    page = normalize_match_page(asyncio.run(demo_provider.match(fixture.id)), fixture.id)
    report = match_report(fixture, page)
    assert report["fixture"]["home"] == fixture.home
    d = report["deserved"]
    assert d["home"] + d["draw"] + d["away"] == pytest.approx(1.0, abs=1e-3)
    assert d["home_expected"] == pytest.approx(fixture.hxg, abs=0.01)
    for side in ("home", "away"):
        line = report["timeline"][side]
        assert line[0] == {"minute": 0, "xg": 0.0, "goal": None}
        assert [p["xg"] for p in line] == sorted(p["xg"] for p in line)  # cumulative, never decreasing
        assert sum(report["buckets"][side]) == pytest.approx(report["summary"][side]["xg"], abs=0.01)
        assert report["summary"][side]["shots"] == len(report["shots"][side])
    assert report["own_goals"]["home"] >= 0 and report["own_goals"]["away"] >= 0
    assert report["key_chances"][0]["xg"] == max(s["xg"] for s in report["shots"]["home"] + report["shots"]["away"])
    assert report["players"]["home"] and report["deserved"]["actual"] in ("home", "draw", "away")


# ------------------------------------------------------------------ finishing / player detail


def shot(xg, goal=False, situation="OpenPlay", x=0.9, y=0.5, kind="RightFoot"):
    return Shot(1, 10, xg, "Goal" if goal else "SavedShot", x, y, situation, kind, "Pass", "P", 1, "h", 2025, 1, "A", "B", "2025-09-01")


def test_zone_geometry():
    assert zone_of(shot(0.5, x=0.97, y=0.5)) == "Six-yard box"
    assert zone_of(shot(0.2, x=0.9, y=0.5)) == "Penalty area"
    assert zone_of(shot(0.05, x=0.7, y=0.5)) == "Outside the box"
    assert zone_of(shot(0.05, x=0.97, y=0.25)) == "Penalty area"  # 17 m wide: past the six-yard box, inside the area
    assert zone_of(shot(0.02, x=0.97, y=0.05)) == "Outside the box"  # by the touchline


def test_finishing_splits_penalties_and_reports_exact_luck():
    shots = [shot(0.76, True, "Penalty")] + [shot(0.1, i < 3) for i in range(10)]
    f = finishing(shots)
    assert f["shots"] == 11 and f["goals"] == 4 and f["np_goals"] == 3 and f["penalties"] == {"taken": 1, "scored": 1}
    assert f["np_xg"] == pytest.approx(1.0) and f["luck_np"]["expected"] == pytest.approx(1.0)
    assert f["luck_np"]["z"] > 1.5 and f["luck_np"]["p_at_least"] < 0.1
    assert {r["name"] for r in f["by_situation"]} == {"Penalty", "OpenPlay"}
    assert f["big_chances"] == 1 and f["by_foot"][0]["name"] == "Right foot"


def test_similarity_and_player_detail_on_demo_data(demo_provider, demo_league):
    ds = build_dataset([demo_league], today=date(2020, 6, 1))
    star = max((r for r in ds.rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: r["output"])
    twins = similar_players(star, ds.rows, limit=6)
    assert len(twins) == 6 and all(t["id"] != star["id"] and t["group"] == "ATT" for t in twins)
    assert [t["similarity"] for t in twins] == sorted((t["similarity"] for t in twins), reverse=True)
    assert all(0 <= t["similarity"] <= 100 and t["avg_gap"] == pytest.approx(100 - t["similarity"], abs=0.11) for t in twins)

    dob = next(iter(ds.rows))["dob"]
    young = similar_players(star, [{**r, "age": 21 if i % 2 else 33} for i, r in enumerate(ds.rows)], max_age=22)
    assert young and all(t["age"] == 21 for t in young)

    page = normalize_player_page(asyncio.run(demo_provider.player(star["id"])), star["id"])
    detail = player_detail(star, page, [2019], team_context={"team": star["team"]})
    assert detail["player"]["name"] == star["name"] and detail["group_label"] == "Attacker"
    assert detail["finishing"]["shots"] == star["shots"] and detail["finishing"]["goals"] == star["goals"]
    assert detail["finishing"]["xg"] == pytest.approx(star["xg"], abs=0.02)
    assert [b["category"] for b in detail["blocks"]] == ["Shooting", "Creation", "Involvement", "Availability", "Discipline"]
    assert len(detail["profile"]) == 7 and all(0 <= p["pct"] <= 100 for p in detail["profile"])
    assert detail["career"] and detail["career"][0]["season"] == 2019
    assert len(detail["shots"]) == star["shots"] and detail["shots"][0]["opponent"]


def test_similarity_skips_goalkeepers_and_low_minutes(demo_league):
    ds = build_dataset([demo_league], today=date(2020, 6, 1))
    keeper = next(r for r in ds.rows if r["group"] == "GK")
    assert similar_players(keeper, ds.rows) == []
    star = next(r for r in ds.rows if r["group"] == "MID" and r["in_pool"])
    assert all(t["minutes"] >= 2500 for t in similar_players(star, ds.rows, min_minutes=2500))


# ------------------------------------------------------------------ chances tab


def _row(name, shots, xg, a_shots, a_xg, goals=0, a_goals=0, time=None):
    return {"name": name, "time": time, "shots": shots, "goals": goals, "xg": xg, "against": {"shots": a_shots, "goals": a_goals, "xg": a_xg}}


def test_prepare_breakdowns_orders_rows_names_them_and_drops_own_goals():
    groups = {
        "shotZone": [_row("ownGoals", 5, 5.0, 1, 1.0, goals=5, a_goals=1), _row("shotSixYardBox", 80, 30.0, 30, 10.0), _row("shotOboxTotal", 150, 5.0, 110, 3.5), _row("shotPenaltyArea", 320, 44.0, 170, 20.0)],
        "timing": [_row("76+", 100, 18.0, 70, 10.0), _row("1-15", 90, 13.0, 34, 5.0)],
        "formation": [_row("4-4-2", 10, 1.0, 8, 1.0, time=100), _row("4-3-3", 340, 50.0, 210, 23.0, time=2270)],
    }
    out = {b["key"]: b for b in prepare_breakdowns(groups, games=38)}
    zone = out["shotZone"]
    assert [r["label"] for r in zone["rows"]] == ["Outside the box", "Penalty area", "Six-yard box"]
    assert zone["note"] and "own" in zone["note"].lower()
    assert sum(r["share_for"] for r in zone["rows"]) == pytest.approx(1.0, abs=0.001)
    six = zone["rows"][-1]
    assert six["xg_shot"] == pytest.approx(30 / 80, abs=1e-3) and six["per_for"] == pytest.approx(30 / 38, abs=1e-3) and zone["unit"] == "game"
    assert [r["label"] for r in out["timing"]["rows"]] == ["1–15 min", "76+ min"]
    formation = out["formation"]
    assert formation["unit"] == "90" and [r["name"] for r in formation["rows"]] == ["4-3-3", "4-4-2"]
    assert formation["rows"][0]["per_for"] == pytest.approx(50 / 2270 * 90, abs=1e-3)
    assert formation["rows"][1]["small"] and not formation["rows"][0]["small"]  # 100 minutes is too little to trust


def test_rows_measured_per_90_need_minutes_behind_them():
    groups = {"gameState": [_row("Goal diff 0", 271, 39.0, 153, 19.7, time=1931), _row("Goal diff -1", 59, 8.7, 16, 1.3, time=40)]}
    rows = {r["name"]: r for r in prepare_breakdowns(groups, games=38)[0]["rows"]}
    assert not rows["Goal diff 0"]["small"]
    assert rows["Goal diff -1"]["small"]  # 40 minutes makes 8.7 xG look like 19 per 90: noise, not a finding


def test_league_comparison_ranks_and_insights_use_the_league_not_a_guess():
    def team(corner_xg):
        return prepare_breakdowns({"situation": [_row("OpenPlay", 300, 40.0, 200, 25.0, goals=40), _row("FromCorner", 60, corner_xg, 40, 5.0, goals=round(corner_xg))]}, games=38)

    teams = {f"T{i}": team(5.0 + 0.2 * i) for i in range(1, 12)}
    teams["Corner FC"] = team(22.0)  # far more corner xG than anyone
    comparison = compare_to_league("Corner FC", teams["Corner FC"], league_baseline(teams))
    stat = comparison["situation"]["FromCorner"]["per_for"]
    assert stat["rank"] == 1 and stat["of"] == 12 and stat["z"] > 2
    against = comparison["situation"]["FromCorner"]["per_against"]
    assert against["rank"] <= 12  # 'low is better' ranks are computed too

    headlines = [i["headline"] for i in chance_insights("Corner FC", teams["Corner FC"], comparison)["situation"]]
    assert any("from corners" in h and "1st of 12" in h and "from from" not in h for h in headlines)
    assert all(i["evidence"] for i in chance_insights("Corner FC", teams["Corner FC"], comparison)["situation"])


def test_chance_insights_without_a_league_make_no_league_claims_and_ignore_tiny_rows():
    prepared = prepare_breakdowns({
        "situation": [_row("OpenPlay", 300, 40.0, 200, 25.0, goals=40), _row("FromCorner", 3, 0.3, 2, 0.2)],
        "result": [_row("Goal", 71, 28.0, 27, 8.0, goals=71), _row("BlockedShot", 175, 14.0, 111, 9.0), _row("SavedShot", 111, 17.0, 61, 8.0), _row("MissedShots", 189, 22.0, 104, 8.0)],
    }, games=38)
    out = chance_insights("Test FC", prepared)
    assert all("league" not in i["headline"].lower() and "of 20" not in i["headline"] for ins in out.values() for i in ins)
    assert not any("corner" in i["headline"].lower() for i in out["situation"])  # 5 shots is noise
    assert any("on target" in i["headline"] for i in out["result"])
