"""The demo world must be coherent (all endpoints agree) and statistically plausible."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.data.demo import DemoProvider
from app.data.normalize import normalize_league, normalize_match_page, normalize_player_page, normalize_team_page
from app.errors import UpstreamError


@pytest.fixture(scope="module")
def provider():
    return DemoProvider(today=date(2021, 1, 15))  # 2019 complete, 2020 part-way


@pytest.fixture(scope="module")
def league_2019(provider):
    raw = asyncio.run(provider.league("EPL", 2019))
    return raw, normalize_league(raw, "EPL", 2019)


def test_full_season_shape(league_2019):
    _raw, ls = league_2019
    assert not ls.warnings
    assert len(ls.teams) == 20 and len(ls.fixtures) == 380 and ls.n_played == 380
    assert all(len(t.history) == 38 for t in ls.teams.values())
    assert all(m.opponent and m.match_id for t in ls.teams.values() for m in t.history)


def test_partial_current_season(provider):
    ls = normalize_league(asyncio.run(provider.league("EPL", 2020)), "EPL", 2020)
    assert 0 < ls.n_played < 380 and len(ls.fixtures) == 380
    played_dates = [f.date for f in ls.played]
    assert max(played_dates) < "2021-01-15"
    assert all(f.hg is None for f in ls.upcoming)


def test_base_rates_are_realistic(league_2019):
    _, ls = league_2019
    played = ls.played
    goals = sum(f.hg + f.ag for f in played) / len(played)
    home = sum(f.hg > f.ag for f in played) / len(played)
    draw = sum(f.hg == f.ag for f in played) / len(played)
    xg = sum(f.hxg + f.axg for f in played) / len(played)
    assert 2.4 <= goals <= 3.4 and 2.4 <= xg <= 3.3
    assert 0.38 <= home <= 0.52 and 0.18 <= draw <= 0.32
    points = sorted(sum(m.pts for m in t.history) for t in ls.teams.values())
    assert 60 <= points[-1] <= 100 and 18 <= points[0] <= 45


def test_team_history_agrees_with_fixtures(league_2019):
    _, ls = league_2019
    fixture_xg = sum(f.hxg + f.axg for f in ls.played)
    history_xg = sum(m.xg for t in ls.teams.values() for m in t.history)
    assert history_xg == pytest.approx(fixture_xg, rel=1e-9)
    total_gf = sum(m.gf for t in ls.teams.values() for m in t.history)
    assert total_gf == sum(f.hg + f.ag for f in ls.played)


def test_player_totals_match_team_totals(league_2019):
    _, ls = league_2019
    team_xg = sum(m.xg for t in ls.teams.values() for m in t.history)
    player_xg = sum(p.xg for p in ls.players)
    assert player_xg == pytest.approx(team_xg, rel=1e-6)  # every shot belongs to a player
    own_goals = sum(f.hg + f.ag for f in ls.played) - sum(p.goals for p in ls.players)
    assert 0 <= own_goals <= 40
    assert all(p.npg <= p.goals and p.npxg <= p.xg + 1e-9 for p in ls.players)
    assert all(p.minutes <= 38 * 90 + 1 for p in ls.players)


def test_player_page_matches_league_row(provider, league_2019):
    _, ls = league_2019
    star = max(ls.players, key=lambda p: p.goals)
    page = normalize_player_page(asyncio.run(provider.player(star.id)), star.id)
    season_shots = [s for s in page.shots if s.season == 2019]
    assert len(season_shots) == star.shots
    assert sum(s.is_goal for s in season_shots) == star.goals
    assert sum(s.xg for s in season_shots) == pytest.approx(star.xg, rel=1e-6)
    career = next(c for c in page.career if c.season == 2019)
    assert (career.goals, career.minutes, career.games) == (star.goals, star.minutes, star.games)
    assert page.favorite_position and page.name == star.name
    assert 2019 in page.splits and page.splits[2019]["situations"]


def test_match_page_matches_fixture(provider, league_2019):
    _, ls = league_2019
    fixture = ls.played[10]
    page = normalize_match_page(asyncio.run(provider.match(fixture.id)), fixture.id)
    assert sum(s.xg for s in page.shots["h"]) == pytest.approx(fixture.hxg)
    assert sum(s.xg for s in page.shots["a"]) == pytest.approx(fixture.axg)
    shot_goals = sum(s.is_goal for s in page.shots["h"])
    assert shot_goals <= fixture.hg and fixture.hg - shot_goals <= 1  # own goals only
    for side in ("h", "a"):
        assert 11 <= len(page.rosters[side]) <= 16
        assert sum(r.minutes for r in page.rosters[side]) == pytest.approx(11 * 90, abs=1)
        assert sum(r.goals for r in page.rosters[side]) == sum(s.is_goal for s in page.shots[side])


def test_team_page_statistics(provider, league_2019):
    page = normalize_team_page(asyncio.run(provider.team("Arsenal", 2019)), "Arsenal", 2019)
    assert set(page.groups) >= {"situation", "formation", "gameState", "timing", "shotZone", "attackSpeed", "result"}
    situations = {r["name"]: r for r in page.groups["situation"]}
    assert situations["OpenPlay"]["shots"] > 150
    assert sum(r["shots"] for r in page.groups["timing"]) == sum(r["shots"] for r in page.groups["situation"])
    assert sum(r["time"] for r in page.groups["formation"]) == 38 * 90


def test_players_persist_across_seasons_and_age(provider):
    a = normalize_league(asyncio.run(provider.league("EPL", 2019)), "EPL", 2019)
    b = normalize_league(asyncio.run(provider.league("EPL", 2020)), "EPL", 2020)
    shared = {p.id for p in a.players} & {p.id for p in b.players}
    assert len(shared) > 250  # most of a squad carries over
    veteran = next(iter(shared))
    page = normalize_player_page(asyncio.run(provider.player(veteran)), veteran)
    assert {c.season for c in page.career} >= {2019, 2020}


def test_determinism_and_seed_sensitivity():
    today = date(2020, 6, 1)
    one = asyncio.run(DemoProvider(today=today, seed=7).league("Serie_A", 2019))
    two = asyncio.run(DemoProvider(today=today, seed=7).league("Serie_A", 2019))
    other = asyncio.run(DemoProvider(today=today, seed=8).league("Serie_A", 2019))
    assert one == two and one != other


def test_names_are_unique_and_birthdates_exposed(provider, league_2019):
    _, ls = league_2019
    names = [p.name for p in ls.players]
    assert len(names) == len(set(names))
    assert provider.birthdate(names[0]) and provider.birthdate("Nobody Here") is None
    dob = date.fromisoformat(provider.birthdate(names[0]))
    assert 1975 <= dob.year <= 2004


def test_search_folds_accents(provider, league_2019):
    _, ls = league_2019
    accented = next((p.name for p in ls.players if any(ord(c) > 127 for c in p.name)), None)
    assert accented
    hits = asyncio.run(provider.search_players(accented.split()[0].lower()))
    assert hits and all("id" in h and "player" in h for h in hits)


def test_out_of_range_requests_are_404(provider):
    for coro in (provider.league("EPL", 2010), provider.league("EPL", 2035), provider.league("Nope", 2019), provider.player(5), provider.match(5)):
        with pytest.raises(UpstreamError) as caught:
            asyncio.run(coro)
        assert caught.value.upstream_status == 404


def test_all_five_leagues_generate(provider):
    sizes = {}
    for code in ("EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"):
        ls = normalize_league(asyncio.run(provider.league(code, 2019)), code, 2019)
        sizes[code] = (len(ls.teams), len(ls.fixtures))
    assert sizes["Bundesliga"] == (18, 306) and sizes["Ligue_1"] == (18, 306) and sizes["Serie_A"] == (20, 380)
