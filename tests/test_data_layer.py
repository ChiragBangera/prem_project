"""Normalizers, the SQLite store and the repository's caching behaviour."""

from __future__ import annotations

import asyncio
import zlib

import pytest

from app.config import Settings
from app.data.normalize import (
    normalize_league,
    normalize_match_page,
    normalize_player_page,
    normalize_team_page,
)
from app.data.repository import Repository
from app.data.store import Store
from app.errors import DataUnavailable, NotFound, UpstreamError
from tests.conftest import FakeProvider, raw_league, raw_match_page, raw_player_page

# ------------------------------------------------------------------ normalizers


def test_league_normalizes_types_and_joins_opponents():
    ls = normalize_league(raw_league(), "EPL", 2025)
    assert set(ls.teams) == {"Alpha FC", "Beta United", "Gamma City", "Delta Town"}
    assert len(ls.fixtures) == 12 and ls.n_played == 12

    alpha = ls.teams["Alpha FC"]
    assert len(alpha.history) == 6
    assert [m.matchweek for m in alpha.history] == [1, 2, 3, 4, 5, 6]
    assert all(isinstance(m.xg, float) and isinstance(m.gf, int) for m in alpha.history)
    # opponent + match id resolved from the fixture list (history rows carry neither)
    assert all(m.opponent and m.opponent != "Alpha FC" and m.match_id for m in alpha.history)
    assert alpha.short == "ALP"
    assert alpha.history[0].ppda == pytest.approx(alpha.history[0].ppda_att / alpha.history[0].ppda_def)


def test_players_parse_strings_and_multi_team_rows():
    ls = normalize_league(raw_league(), "EPL", 2025)
    by_name = {p.name: p for p in ls.players}
    ann = by_name["Ann Striker"]
    assert (ann.goals, ann.minutes, ann.shots) == (6, 640, 22)
    assert ann.xg == pytest.approx(4.8) and ann.position == "F S"
    cy = by_name["Cy Traveller"]
    assert cy.teams == ["Beta United", "Gamma City"] and cy.team == "Beta United / Gamma City"
    assert ann.league == "EPL" and ann.season == 2025


def test_fixture_rounds():
    payload = raw_league(played=4)
    ls = normalize_league(payload, "EPL", 2025)
    assert ls.n_played == 4 and len(ls.upcoming) == 8
    assert [f.round for f in ls.fixtures][:2] == [1, 1]
    assert ls.upcoming[0].hg is None and ls.upcoming[0].hxg is None


def test_html_entities_in_names_are_decoded_everywhere():
    """Understat occasionally sends names such as ``N&#039;Golo``; they must read (and join) as plain text."""
    raw = raw_league()
    for entry in raw["teams"].values() if isinstance(raw["teams"], dict) else raw["teams"]:
        if entry["title"] == "Alpha FC":
            entry["title"] = "Alpha &amp; Sons FC"
    for fixture in raw["dates"]:
        for side in ("h", "a"):
            if fixture[side]["title"] == "Alpha FC":
                fixture[side]["title"] = "Alpha &amp; Sons FC"
    raw["players"][0]["player_name"] = "N&#039;Golo Traor&eacute;"
    ls = normalize_league(raw, "EPL", 2025)
    assert "Alpha & Sons FC" in ls.teams and "Alpha &amp; Sons FC" not in ls.teams
    assert all(m.opponent and m.match_id for m in ls.teams["Alpha & Sons FC"].history)  # still joins to the fixtures
    assert ls.players[0].name == "N'Golo Traoré"

    shots = normalize_player_page({"shots": [{"id": "1", "minute": "5", "X": "0.9", "Y": "0.5", "xG": "0.1", "result": "Goal", "player": "D&#039;Arcy", "player_assisted": "O&#039;Neil", "h_team": "A", "a_team": "B", "h_a": "h", "date": "2025-08-16 15:00:00"}], "groups": {}}, 1)
    assert shots.shots[0].player == "D'Arcy" and shots.shots[0].assisted_by == "O'Neil"


def test_bad_rows_are_skipped_not_fatal():
    payload = raw_league()
    payload["players"].append({"id": "", "player_name": ""})
    payload["dates"].append({"id": "1", "isResult": True})  # no teams
    payload["teams"]["9"] = {"id": "9", "history": []}  # no title
    ls = normalize_league(payload, "EPL", 2025)
    assert len(ls.players) == 4 and len(ls.fixtures) == 12
    assert len(ls.warnings) == 3


def test_teams_may_arrive_as_a_list():
    payload = raw_league()
    payload["teams"] = list(payload["teams"].values())
    assert len(normalize_league(payload, "EPL", 2025).teams) == 4


def test_player_page():
    page = normalize_player_page(raw_player_page(), 101)
    assert page.favorite_position == "FW" and page.name == "Ann Striker"
    assert [s.season for s in page.shots] == [2024, 2025]
    goal = page.shots[1]
    assert goal.is_goal and goal.x == pytest.approx(0.912) and goal.assisted_by == "Bo Playmaker"
    assert [c.season for c in page.career] == [2024, 2025] and page.career[1].goals == 6
    assert page.splits[2025]["situations"][0].name == "OpenPlay"
    assert page.splits[2025]["zones"][0].name == "shotPenaltyArea"
    assert page.splits[2025]["types"][0].name == "RightFoot"  # dict-keyed rows tolerated
    assert page.positions_minutes[2025][0]["minutes"] == 640


def test_shot_coordinates_are_clamped():
    raw = raw_player_page()
    raw["shots"][0]["X"], raw["shots"][0]["Y"] = "1.4", "-0.2"
    page = normalize_player_page(raw, 101)
    assert (page.shots[1].x, page.shots[1].y) == (1.0, 0.0)


def test_match_page():
    page = normalize_match_page(raw_match_page(), 1000)
    assert [s.minute for s in page.shots["h"]] == [10, 55]
    assert sum(s.xg for s in page.shots["a"]) == pytest.approx(0.65)
    assert page.rosters["a"][0].player == "Eve Winger" and page.rosters["a"][0].yellow == 1


def test_team_page_flattens_for_and_against():
    raw = {"statistics": {"situation": {"OpenPlay": {"shots": 100, "goals": 10, "xG": 9.5, "against": {"shots": 90, "goals": 8, "xG": 8.1}}},
                          "formation": {"4-3-3": {"stat": "4-3-3", "time": 900, "shots": 30, "goals": 3, "xG": 2.9, "against": {}}}}}
    page = normalize_team_page(raw, "Alpha FC", 2025)
    assert page.groups["situation"][0]["against"]["xg"] == pytest.approx(8.1)
    assert page.groups["formation"][0]["time"] == 900


def test_non_object_payloads_raise_value_error():
    with pytest.raises(ValueError):
        normalize_league([], "EPL", 2025)
    with pytest.raises(ValueError):
        normalize_player_page("nope", 1)


# ------------------------------------------------------------------ store


def test_store_roundtrip_and_metadata(store):
    stamp = store.put("league", "EPL:2025", {"a": [1, 2, "é"]}, source="understat", complete=True)
    record = store.get("league", "EPL:2025")
    assert record.body == {"a": [1, 2, "é"]} and record.complete and record.source == "understat"
    assert record.fetched_at == stamp
    assert store.get("league", "missing") is None
    assert store.keys("league")[0][0] == "EPL:2025"
    stats = store.stats()
    assert stats["kinds"]["league"]["count"] == 1 and stats["total_bytes"] > 0


def test_store_corrupt_row_is_a_miss(store):
    store.put("league", "x", {"ok": 1}, source="demo")
    store._db.execute("UPDATE payload SET body=? WHERE key='x'", (zlib.compress(b"{not json"),))
    store._db.commit()
    assert store.get("league", "x") is None


def test_store_kv_and_delete(store):
    store.kv_set("shortlist", [1, 2, 3])
    assert store.kv_get("shortlist") == [1, 2, 3] and store.kv_get("nope", "d") == "d"
    store.put("player", "1", {}, source="demo")
    store.put("player", "2", {}, source="demo")
    assert store.delete("player", "1") == 1 and store.delete("player") == 1


def test_store_persists_across_connections(tmp_path):
    first = Store(tmp_path / "p.sqlite")
    first.put("league", "k", {"v": 1}, source="demo")
    first.close()
    second = Store(tmp_path / "p.sqlite")
    assert second.get("league", "k").body == {"v": 1}
    second.close()


# ------------------------------------------------------------------ repository


async def test_first_read_fetches_then_serves_from_cache(repo, provider):
    first = await repo.league("EPL", 2025)
    second = await repo.league("EPL", 2025)
    assert len(provider.calls) == 1
    assert first.data is second.data  # same typed object from the in-memory cache
    assert first.meta.source == "understat" and not first.meta.stale and first.meta.complete


async def test_cache_survives_a_new_repository(store, provider, settings, clock):
    await Repository(store, provider, settings, clock=clock).league("EPL", 2025)
    provider.calls.clear()
    fresh = Repository(store, provider, settings, clock=clock)
    result = await fresh.league("EPL", 2025)
    assert provider.calls == [] and result.data.n_played == 12


async def test_concurrent_requests_share_one_upstream_call(repo, provider):
    provider.delay = 0.05
    results = await asyncio.gather(*(repo.league("EPL", 2025) for _ in range(12)))
    assert len(provider.calls) == 1
    assert all(r.data is results[0].data for r in results)


async def test_live_season_expires_and_refetches(store, settings, clock):
    provider = FakeProvider(raw_league(played=6))  # season still has fixtures to play
    repo = Repository(store, provider, settings, clock=clock)
    first = await repo.league("EPL", 2025)
    assert not first.meta.complete
    clock.advance(60)
    await repo.league("EPL", 2025)
    assert len(provider.calls) == 1  # still fresh
    clock.advance(24 * 3600)
    await repo.league("EPL", 2025)
    assert len(provider.calls) == 2  # expired -> refetched


async def test_finished_season_never_expires(repo, provider, clock):
    await repo.league("EPL", 2025)
    clock.advance(400 * 24 * 3600)
    result = await repo.league("EPL", 2025)
    assert len(provider.calls) == 1 and result.meta.complete


async def test_refresh_skips_complete_unless_forced(repo, provider):
    await repo.league("EPL", 2025)
    await repo.league("EPL", 2025, refresh=True)
    assert len(provider.calls) == 1
    await repo.league("EPL", 2025, refresh=True, force=True)
    assert len(provider.calls) == 2


async def test_stale_data_is_served_when_refresh_fails(store, settings, clock):
    provider = FakeProvider(raw_league(played=6))
    repo = Repository(store, provider, settings, clock=clock)
    await repo.league("EPL", 2025)
    clock.advance(3 * 24 * 3600)
    provider.fail = UpstreamError("Understat returned HTTP 503.", upstream_status=503)
    result = await repo.league("EPL", 2025)
    assert result.meta.stale and "503" in result.meta.error
    assert result.data.n_played == 6  # still usable


async def test_no_cache_and_upstream_down_raises_clear_error(repo, provider):
    provider.fail = UpstreamError("Could not connect to Understat.")
    with pytest.raises(UpstreamError):
        await repo.league("EPL", 2025)


async def test_404_becomes_not_found(repo, provider):
    provider.fail = UpstreamError("HTTP 404", upstream_status=404)
    with pytest.raises(NotFound):
        await repo.player(999)


async def test_slow_refresh_serves_stale_and_still_completes_in_background(store, settings, clock, monkeypatch):
    import app.data.repository as repository_module

    monkeypatch.setattr(repository_module, "REFRESH_WAIT", 0.05)
    provider = FakeProvider(raw_league(played=6))
    repo = Repository(store, provider, settings, clock=clock)
    await repo.league("EPL", 2025)
    clock.advance(3 * 24 * 3600)
    provider.delay = 0.2
    slow = await repo.league("EPL", 2025)
    assert slow.meta.stale and "taking too long" in slow.meta.error
    await asyncio.sleep(0.3)  # the background refresh lands
    provider.delay = 0
    fresh = await repo.league("EPL", 2025)
    assert not fresh.meta.stale and len(provider.calls) == 2


async def test_offline_mode_never_calls_provider(store, provider, tmp_path, clock):
    online = Repository(store, provider, Settings(data_dir=tmp_path, min_interval=0), clock=clock)
    await online.league("EPL", 2025)
    provider.calls.clear()

    offline = Repository(store, provider, Settings(data_dir=tmp_path, offline=True, min_interval=0), clock=clock)
    cached = await offline.league("EPL", 2025)
    assert cached.data.n_played == 12 and provider.calls == []
    with pytest.raises(DataUnavailable) as caught:
        await offline.league("La_liga", 2025)
    assert "sync" in caught.value.hint and provider.calls == []


async def test_player_match_and_team_pages(repo, provider):
    player = (await repo.player(101)).data
    match = (await repo.match(1000)).data
    team = (await repo.team_page("Alpha FC", 2025)).data
    assert player.favorite_position == "FW" and len(match.shots["h"]) == 2
    assert team.groups["situation"][0]["name"] == "OpenPlay"
    await repo.match(1000)
    assert [c[0] for c in provider.calls] == ["player", "match", "team"]  # match served from cache


async def test_unreadable_cached_payload_is_refetched(store, provider, settings, clock):
    store.put("league", "EPL:2025", {"teams": "garbage", "dates": 5}, source="understat")
    store.put("league", "EPL:2024", "not-an-object", source="understat")
    repo = Repository(store, provider, settings, clock=clock)
    result = await repo.league("EPL", 2024)  # normalize raises -> treated as a miss
    assert result.data.n_played == 12 and len(provider.calls) == 1


async def test_version_changes_when_data_is_replaced(store, settings, clock):
    provider = FakeProvider(raw_league(played=6))
    repo = Repository(store, provider, settings, clock=clock)
    assert repo.version("league", "EPL:2025") == 0.0
    await repo.league("EPL", 2025)
    first = repo.version("league", "EPL:2025")
    clock.advance(24 * 3600)
    await repo.league("EPL", 2025)
    assert repo.version("league", "EPL:2025") > first


async def test_memory_cache_is_bounded(store, provider, settings, clock):
    repo = Repository(store, provider, settings, clock=clock, memory_budget=25)
    for season in range(2018, 2024):  # league weight is 10 -> at most 2 stay in memory
        await repo.league("EPL", season)
    assert len(repo._mem) <= 2
    provider.calls.clear()
    await repo.league("EPL", 2018)  # evicted from memory, still in SQLite
    assert provider.calls == []
