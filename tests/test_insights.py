"""Insight generators: thresholds, wording contracts and ranking."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.analytics.match import match_report
from app.analytics.players import build_dataset
from app.analytics.table import compute_table, league_context
from app.analytics.team import team_profile
from app.data.models import Fixture
from app.data.normalize import normalize_match_page
from app.insights.briefing import compose_insights, movers, recent_matches, result_probabilities
from app.insights.core import Insight, confidence_from_matches, ordinal, plural, pct, rank, signed
from app.insights.league import league_insights
from app.insights.match import match_insights
from app.insights.player import player_insights, scouting_highlights
from app.insights.team import team_insights

# ------------------------------------------------------------------ helpers


def test_formatting_helpers():
    assert signed(2.34) == "+2.3" and signed(-2.34) == "−2.3" and signed(0) == "0.0" and signed(1.234, 2) == "+1.23"
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 101, 112)] == ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st", "112th"]
    assert plural(1, "point") == "1 point" and plural(3, "match", "matches") == "3 matches" and pct(0.256) == "26%"
    assert [confidence_from_matches(n) for n in (3, 10, 30)] == ["low", "medium", "high"]


def test_rank_orders_by_score_and_caps_per_kind():
    items = [Insight("a", "table", "A", score=90), Insight("b", "table", "B", score=80), Insight("c", "table", "C", score=70),
             Insight("d", "form", "D", score=60), Insight("e", "style", "E", score=50)]
    assert [i.id for i in rank(items)] == ["a", "b", "c", "d", "e"]
    assert [i.id for i in rank(items, per_kind=2)] == ["a", "b", "d", "e"]
    assert [i.id for i in rank(items, limit=2, per_kind=1)] == ["a", "d"]
    d = items[0].to_dict()
    assert set(d) >= {"id", "kind", "headline", "detail", "tone", "score", "confidence", "evidence", "entities", "link"}


# ------------------------------------------------------------------ league


def row(team, played=20, pts=40, xpts=40.0, xg=30.0, xga=25.0, gf=30, ga=25, rank_=1, rank_xpts=1, ppda=10.0, trend=None):
    return {
        "team": team, "played": played, "pts": pts, "xpts": xpts, "xpts_gap": pts - xpts, "gf": gf, "ga": ga, "gd": gf - ga,
        "xg": xg, "xga": xga, "xgd": xg - xga, "xg_pg": xg / played, "xga_pg": xga / played, "xgd_pg": (xg - xga) / played,
        "g_xg": gf - xg, "xga_ga": xga - ga, "rank": rank_, "rank_xpts": rank_xpts, "ppda": ppda, "form": ["w", "d", "w", "l", "w"],
        "trend_xgd": trend or [], "w": 0, "d": 0, "l": 0,
    }


CTX = {"rounds_played": 20, "matches_played": 200, "goals_pg": 2.8, "xg_pg": 2.7, "home_win": 0.44, "draw": 0.25, "complete": False}


def test_early_season_gets_one_honest_note():
    (only,) = league_insights([row("A", played=2), row("B", played=2), row("C", played=2), row("D", played=2)], {**CTX, "rounds_played": 2})
    assert only.kind == "info" and "round 6" in only.detail and only.confidence == "low"


def test_points_gap_insight_needs_a_gap_beyond_noise():
    calm = [row("A", pts=41, xpts=40.0, rank_=1), row("B", pts=39, xpts=39.5, rank_=2, rank_xpts=2), row("C", pts=30, xpts=30.4, rank_=3, rank_xpts=3), row("D", pts=20, xpts=20.0, rank_=4, rank_xpts=4)]
    assert not [i for i in league_insights(calm, CTX) if i.id.startswith("league.gap")]

    lucky = [row("A", pts=41, xpts=40.0, rank_=1), row("B", pts=39, xpts=27.0, rank_=2, rank_xpts=6), row("C", pts=30, xpts=30.4, rank_=3, rank_xpts=3), row("D", pts=20, xpts=20.0, rank_=4, rank_xpts=4)]
    gap = next(i for i in league_insights(lucky, CTX) if i.id == "league.gap.B")
    assert "12.0 more points than their chances deserve" in gap.headline
    assert gap.tone == "warning" and "tend to shrink" in gap.detail and gap.link == {"route": "team", "params": {"team": "B"}}
    assert {e["label"] for e in gap.evidence} >= {"Points", "xPTS", "Gap"}


def test_unlucky_team_gets_a_positive_tone():
    rows = [row("A", pts=30, xpts=42.0, rank_=5, rank_xpts=1), row("B", pts=41, xpts=30.0, rank_=1, rank_xpts=3), row("C", pts=35, xpts=31, rank_=2, rank_xpts=2), row("D", pts=20, xpts=21, rank_=4, rank_xpts=4)]
    gap = next(i for i in league_insights(rows, CTX) if i.id == "league.gap.A")
    assert gap.tone == "positive" and "fewer points" in gap.headline


def test_title_race_flags_when_process_disagrees_with_the_table():
    rows = [row("Leader", pts=50, xg=30, xga=28, rank_=1), row("Better", pts=44, xg=42, xga=20, rank_=2), row("C", pts=30, rank_=3), row("D", pts=20, rank_=4)]
    split = next(i for i in league_insights(rows, CTX) if i.id == "league.title.split")
    assert "Leader lead the table, but Better have the best underlying numbers" in split.headline and split.tone == "warning"
    agree = league_insights([row("Leader", pts=50, xg=42, xga=20), row("B", pts=44, xg=30, xga=28, rank_=2), row("C", pts=30, rank_=3), row("D", pts=20, rank_=4)], CTX)
    assert any(i.id == "league.title.agree" for i in agree)
    finished = league_insights(rows, {**CTX, "complete": True})
    assert not any(i.id.startswith("league.title") for i in finished)


def test_finishing_luck_uses_a_significance_threshold():
    normal = [row("A", gf=31, xg=30.0), row("B", gf=29, xg=30.0, rank_=2), row("C", rank_=3), row("D", rank_=4)]
    assert not [i for i in league_insights(normal, CTX) if i.id.startswith("league.finish")]
    hot = [row("A", gf=42, xg=30.0), row("B", rank_=2), row("C", rank_=3), row("D", rank_=4)]
    assert next(i for i in league_insights(hot, CTX) if i.id == "league.finish.A").tone == "warning"


def test_relegation_escape_insight():
    rows = [row("A", pts=50, rank_=1), row("B", pts=44, rank_=2, rank_xpts=2), row("C", pts=40, rank_=3, rank_xpts=4), row("D", pts=35, rank_=4, rank_xpts=3),
            row("E", pts=20, rank_=5, rank_xpts=5), row("F", pts=14, xpts=27.0, rank_=6, rank_xpts=1)]
    ids = [i.id for i in league_insights(rows, CTX, relegation_places=2)]
    assert "league.escape.F" in ids


def test_demo_league_insights_are_well_formed(demo_league_partial):
    ctx = league_context(demo_league_partial)
    table = compute_table(demo_league_partial)
    insights = league_insights(table, ctx)
    assert insights and len({i.id for i in insights}) == len(insights)
    for i in insights:
        assert 0 <= i.score <= 100 and i.headline and i.tone in ("positive", "negative", "warning", "neutral", "info")
        assert i.confidence in ("low", "medium", "high")
        assert i.link is None or i.link["route"] in ("team", "player", "match")


# ------------------------------------------------------------------ team


def profile_stub(**overrides):
    base = {
        "team": {"team": "Alpha", "played": 20, "rank": 3, "rank_xpts": 3, "pts": 36, "xpts": 35.0, "xpts_gap": 1.0, "xgd_pg": 0.5, "pts_pg": 1.8},
        "percentiles": [],
        "splits": {"home": {"played": 10, "xgd_pg": 0.9, "pts_pg": 2.2}, "away": {"played": 10, "xgd_pg": 0.1, "pts_pg": 1.4}, "last6": None,
                   "first_half": None, "second_half": None, "vs_stronger": None, "vs_weaker": None},
        "matches": [], "schedule": {"remaining": 0, "remaining_avg_opp": None}, "squad": [], "concentration": None, "eras": [],
    }
    for k, v in overrides.items():
        base[k] = {**base[k], **v} if isinstance(base[k], dict) and isinstance(v, dict) else v
    return base


def test_team_venue_insight_only_claims_fortress_when_points_agree():
    agree = {i.id: i for i in team_insights(profile_stub())}["team.Alpha.venue"]
    assert "fortress at home" in agree.headline
    disagree = profile_stub(splits={"home": {"played": 10, "xgd_pg": 0.9, "pts_pg": 1.5}, "away": {"played": 10, "xgd_pg": 0.1, "pts_pg": 1.6}})
    text = {i.id: i for i in team_insights(disagree)}["team.Alpha.venue"]
    assert "fortress" not in text.headline and "points have not followed" in text.headline


def test_team_strengths_and_weaknesses_come_from_percentiles():
    percentiles = [
        {"key": "xga_pg", "label": "", "value": 0.88, "percentile": 96.0, "league_average": 1.3},
        {"key": "ppda", "label": "", "value": 15.2, "percentile": 8.0, "league_average": 10.5},
        {"key": "xg_pg", "label": "", "value": 1.4, "percentile": 50.0, "league_average": 1.4},
    ]
    ids = {i.id: i for i in team_insights(profile_stub(percentiles=percentiles))}
    assert "allow the fewest chances" in ids["team.Alpha.strength.xga_pg"].headline and "top 4%" in ids["team.Alpha.strength.xga_pg"].headline
    assert "press very little" in ids["team.Alpha.weakness.ppda"].headline and ids["team.Alpha.weakness.ppda"].tone == "negative"
    assert "team.Alpha.strength.xg_pg" not in ids


def test_team_early_season_and_standing_wording():
    (early,) = team_insights(profile_stub(team={"played": 2}))
    assert early.confidence == "low" and "too early" in early.headline
    flattered = {i.id: i for i in team_insights(profile_stub(team={"rank": 2, "rank_xpts": 7, "xpts_gap": 6.5}))}["team.Alpha.standing"]
    assert "2nd in the table but 7th on expected points" in flattered.headline and flattered.tone == "warning"


def test_demo_team_insights(demo_league_partial):
    ctx = compute_table(demo_league_partial)
    profile = team_profile(demo_league_partial, ctx[5]["team"])
    insights = team_insights(profile)
    assert insights and all(i.entities and i.entities[0]["name"] == ctx[5]["team"] for i in insights)


# ------------------------------------------------------------------ player


def prow(**kw):
    base = {
        "id": 7, "name": "Alex Test", "group": "ATT", "minutes": 1800, "games": 22, "mins_per_app": 82, "minutes_share": 0.9, "in_pool": True,
        "pct": {"npxg90": 95.0, "xa90": 40.0, "kp90": 45.0, "shots90": 80.0, "xgps": 70.0, "xgchain90": 60.0, "xgbuildup90": 30.0},
        "rank": {"npxg90": 2}, "pool_n": 40, "npxg90": 0.55, "xa90": 0.1, "kp90": 1.0, "shots90": 3.0, "xgps": 0.12, "xgchain90": 0.6,
        "xgbuildup90": 0.1, "contrib90": 0.65, "age": 20, "output": 72.0, "g_xg": 0.5, "g_xg_z": 0.2, "goals": 9, "xg": 8.5, "shots": 60,
        "team": "Alpha", "yellow90": 0.1,
    }
    base.update(kw)
    return base


def fin(np_goals=8, np_xg=8.0, shots=50, z=0.0, p_least=0.5, p_most=0.5):
    return {"np_shots": shots, "np_goals": np_goals, "np_xg": np_xg, "luck_np": {"z": z, "p_at_least": p_least, "p_at_most": p_most}}


def test_goalkeepers_get_an_honest_note():
    (note,) = player_insights(prow(group="GK"))
    assert "no goalkeeping data" in note.headline


def test_standout_rank_and_percentile_wording():
    ids = {i.id: i for i in player_insights(prow())}
    standout = ids["player.7.standout"]
    assert "Elite for non-penalty xG: 2nd of 40 attackers (0.55 per 90)" in standout.headline and "top 5%" in standout.detail
    assert ids["player.7.young"].headline.startswith("At 20,")


def test_finishing_insight_direction_and_significance():
    hot = {i.id: i for i in player_insights(prow(), finishing=fin(np_goals=14, np_xg=8.0, z=2.4, p_least=0.012))}["player.7.luck"]
    assert hot.tone == "warning" and "about 1% of the time" in hot.headline and "regresses" in hot.detail
    cold = {i.id: i for i in player_insights(prow(), finishing=fin(np_goals=3, np_xg=8.0, z=-2.1, p_most=0.02))}["player.7.luck"]
    assert cold.tone == "positive" and "Scoring only 3" in cold.headline
    fair = {i.id: i for i in player_insights(prow(), finishing=fin())}["player.7.luck"]
    assert "in line with the chances" in fair.headline and fair.tone == "neutral"


def test_small_sample_and_role_notes():
    ids = {i.id: i for i in player_insights(prow(minutes=300, games=5, minutes_share=0.2, mins_per_app=60, in_pool=False, age=27))}
    assert ids["player.7.sample"].tone == "warning" and ids["player.7.sample"].score >= 70
    sub = {i.id: i for i in player_insights(prow(minutes=700, games=14, mins_per_app=30, minutes_share=0.3, age=27))}["player.7.impact"]
    assert "minutes per appearance" in sub.headline and "deserve a longer look" in sub.detail


def test_trend_versus_previous_season():
    career = [{"season": 2024, "minutes": 2000, "npxg90": 0.30, "xa90": 0.1, "xgbuildup90": 0.1}, {"season": 2025, "minutes": 2000, "npxg90": 0.45, "xa90": 0.1, "xgbuildup90": 0.1}]
    trend = {i.id: i for i in player_insights(prow(age=27), career=career)}["player.7.trend"]
    assert "up 50%" in trend.headline and "0.30 → 0.45" in trend.headline


def test_scouting_highlights_pick_the_right_players():
    rows = [
        prow(id=1, name="Prospect", age=19, output=80.0, team="A", contrib90=0.7, minutes=1500),
        prow(id=2, name="Hot", age=27, g_xg=6.0, g_xg_z=2.6, goals=14, xg=8.0, shots=50, team="B"),
        prow(id=3, name="Cold", age=27, g_xg=-5.0, g_xg_z=-2.4, goals=3, xg=8.0, shots=60, team="C"),
        prow(id=4, name="Gem", age=27, output=88.0, minutes=500, minutes_share=0.25, team="D"),
        prow(id=5, name="NotInPool", age=18, output=95.0, in_pool=False, team="E"),
        prow(id=6, name="Keeper", group="GK", team="F"),
    ]
    ids = {i.id for i in scouting_highlights(rows)}
    assert {"scout.young.1", "scout.hot.2", "scout.cold.3", "scout.gem.4"} <= ids
    assert not any(i.endswith((".5", ".6")) for i in ids)


def test_demo_player_and_scouting_insights(demo_league):
    ds = build_dataset([demo_league], today=date(2020, 6, 1))
    star = max((r for r in ds.rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: r["output"])
    assert player_insights(star) and scouting_highlights(ds.rows)


# ------------------------------------------------------------------ match / briefing


def test_match_insights_flag_results_against_the_run_of_play(demo_provider, demo_league):
    fixture = demo_league.played[10]
    report = match_report(fixture, normalize_match_page(asyncio.run(demo_provider.match(fixture.id)), fixture.id))
    assert match_insights(report)
    upset = {**report, "deserved": {**report["deserved"], "actual": "home", "actual_probability": 0.09, "home": 0.09, "away": 0.71, "draw": 0.2}}
    against = next(i for i in match_insights(upset) if i.id.endswith(".against"))
    assert "against the run of play" in against.headline and against.tone == "warning" and "9%" in against.headline
    draw = {**report, "deserved": {**report["deserved"], "actual": "draw", "actual_probability": 0.2, "home": 0.62, "away": 0.18, "draw": 0.2}}
    held = next(i for i in match_insights(draw) if i.id.endswith(".draw"))
    assert "better side on chances and only drew" in held.headline


def test_result_probabilities_and_recent_matches(demo_league_partial):
    h, d, a = result_probabilities(2.5, 0.4)
    assert h > 0.8 and h + d + a == pytest.approx(1.0)
    recent = recent_matches(demo_league_partial, limit=6)
    assert len(recent) == 6 and recent[0]["date"] >= recent[-1]["date"]
    assert all(r["p_home"] + r["p_draw"] + r["p_away"] == pytest.approx(1.0, abs=1e-2) for r in recent)
    fx = Fixture(1, "2025-01-01 15:00:00", "A", "B", "A", "B", True, 0, 1, 2.6, 0.3)  # home lost despite dominating
    from app.data.models import LeagueSeason

    flagged = recent_matches(LeagueSeason("EPL", 2025, {}, [], [fx]))[0]
    assert flagged["flag"] == "against_run_of_play"


def test_movers_and_composed_front_page(demo_league_partial):
    m = movers(demo_league_partial, span=3)
    assert set(m) == {"risers", "fallers", "span"}
    assert all(c["change"] >= 2 for c in m["risers"]) and all(c["change"] <= -2 for c in m["fallers"])
    league_side = league_insights(compute_table(demo_league_partial), league_context(demo_league_partial))
    ds = build_dataset([demo_league_partial], today=date(2021, 1, 15))
    front = compose_insights(league_side, scouting_highlights(ds.rows), limit=8)
    assert 4 <= len(front) <= 8 and [i.score for i in front] == sorted((i.score for i in front), reverse=True)
    assert sum(1 for i in front if i.kind == "table") <= 2 + 1
