"""The demo world's synthetic event data: deterministic, read by the real parser, consistent with the simulation, and linked to Understat's data."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import date

import pytest
from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.data.demo import DemoProvider
from app.data.demo.events import WS_PLAYER, game_id, synthesize_match
from app.events import counters as C
from app.events import silver as SV
from app.sync.demofeed import DemoEventFeed
from app.workbench import Workbench

TODAY = date(2021, 1, 15)


@pytest.fixture(scope="module")
def world():
    provider = DemoProvider(today=TODAY)
    data = provider.season_data("EPL", 2019)
    return provider, data, sorted(data.matches.values(), key=lambda m: (m.dt, m.id))


def test_a_match_always_yields_the_same_document(world):
    _, data, matches = world
    a, b = synthesize_match(data, matches[3]), synthesize_match(data, matches[3])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert json.dumps(a, sort_keys=True) != json.dumps(synthesize_match(data, matches[4]), sort_keys=True)
    assert game_id(matches[3]) != game_id(matches[4])


def test_the_real_parser_reads_it_and_it_agrees_with_the_simulation(world):
    _, data, matches = world
    for match in matches[:6]:
        doc = synthesize_match(data, match)
        silver = SV.parse_match(doc, league="EPL", season=2019, game_id=game_id(match))
        assert silver is not None
        gold = C.derive_match(SV.Match(silver))
        goals = [e for e in doc["events"] if e.get("isGoal")]
        assert len(goals) == match.hg + match.ag                                    # the simulation's goals, nothing added or lost
        shots = [e for e in doc["events"] if e.get("isShot")]
        assert len(shots) == len(match.shots["h"]) + len(match.shots["a"])
        assert doc["ftScore"] == f"{match.hg} : {match.ag}" and doc["home"]["name"] == match.home and doc["away"]["name"] == match.away
        starters = {v: [a for a in match.lineups[v] if a.code != "Sub"] for v in ("h", "a")}
        assert all(len(starters[v]) == 11 for v in starters)
        assert len(gold["players"]) >= 22


def test_an_own_goal_has_a_scorer_a_minute_and_a_side_in_the_match_page_and_in_the_events(world):
    from app.analytics.matchsum import scorers
    from app.data.normalize import normalize_match_page

    provider, data, matches = world
    own = [m for m in matches if m.own]
    assert own, "a season of the demo world has own goals"
    for m in own[:4]:
        og = m.own[0]
        credited = "a" if og.venue == "h" else "h"
        page = normalize_match_page(asyncio.run(provider.match(m.id)), m.id)
        listed = scorers(page)
        assert [(g["player"], g["minute"]) for g in listed[credited] if g["kind"] == "og"] == [(og.player.name, og.minute)]
        doc = synthesize_match(data, m)
        goals = [e for e in doc["events"] if e.get("isOwnGoal")]
        assert len(goals) == len(m.own) and goals[0]["playerId"] == WS_PLAYER + og.player.id and not goals[0].get("isShot")
        team_id = doc["home"]["teamId"] if og.venue == "h" else doc["away"]["teamId"]
        assert goals[0]["teamId"] == team_id                                       # an own goal belongs to the team of the man who scored it
        gold = C.derive_match(SV.Match(SV.parse_match(doc, league="EPL", season=2019, game_id=game_id(m))))
        assert any(p["c"].get("own_goals") == 1 for p in gold["players"])


def test_every_goal_in_the_score_has_a_scorer_in_the_match_page(world):
    from app.analytics.matchsum import scorers
    from app.data.normalize import normalize_match_page

    provider, _data, matches = world
    for m in matches:
        page = normalize_match_page(asyncio.run(provider.match(m.id)), m.id)
        listed = scorers(page)
        assert (len(listed["h"]), len(listed["a"])) == (m.hg, m.ag), f"match {m.id}"


def test_the_numbers_look_like_football(world):
    _, data, matches = world
    docs = [synthesize_match(data, m) for m in matches[:40]]
    passes, ok, tackles, clearances, aerials, fouls, corners = [], 0, 0, 0, 0, 0, 0
    for doc in docs:
        for e in doc["events"]:
            kind = e["type"]["displayName"]
            if kind == "Pass":
                passes.append(e)
                ok += e["outcomeType"]["value"]
            elif kind == "Tackle":
                tackles += 1
            elif kind == "Clearance":
                clearances += 1
            elif kind == "Aerial":
                aerials += 1
            elif kind == "Foul" and e["outcomeType"]["value"] == 0:          # committed (the other half of each pair is "was fouled")
                fouls += 1
            elif kind == "CornerAwarded":
                corners += 1
    n = len(docs)
    assert 650 <= len(passes) / n <= 1000                                          # both teams together, per match
    assert 0.74 <= ok / len(passes) <= 0.9
    assert 25 <= tackles / n <= 55 and 20 <= clearances / n <= 55 and 25 <= aerials / n <= 70
    assert 15 <= fouls / n <= 32 and 3 <= corners / n <= 14
    assert all(0 <= e["x"] <= 100 and 0 <= e["y"] <= 100 for d in docs for e in d["events"] if "x" in e)
    # the side with the better chances has the ball more, more often than not
    agree = 0
    for m, doc in zip(matches[:40], docs):
        home = sum(1 for e in doc["events"] if e["type"]["displayName"] == "Pass" and e["teamId"] == doc["home"]["teamId"])
        away = sum(1 for e in doc["events"] if e["type"]["displayName"] == "Pass" and e["teamId"] == doc["away"]["teamId"])
        agree += (m.hxg > m.axg) == (home > away)
    assert agree >= 0.65 * 40


def test_players_are_the_demo_players_so_they_can_be_linked(world):
    _, data, matches = world
    doc = synthesize_match(data, matches[0])
    known = {p.id for squad in data.rosters.values() for p in squad}
    ids = {e["playerId"] - WS_PLAYER for e in doc["events"] if "playerId" in e}
    assert ids and ids <= known
    on_pitch = {pl["playerId"] - WS_PLAYER for side in ("home", "away") for pl in doc[side]["players"]}
    assert ids <= on_pitch
    assert sum(1 for side in ("home", "away") for pl in doc[side]["players"] if pl["isManOfTheMatch"]) == 1


async def _fill(tmp_path, *, limit):
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=TODAY)
    feed = DemoEventFeed(wb, limit=limit, seasons_back=0)
    feed.start()
    await feed.wait()
    return wb, feed


def test_the_feed_stores_matches_like_the_real_fetcher_and_never_repeats_itself(tmp_path):
    async def go():
        wb, feed = await _fill(tmp_path, limit=5)
        try:
            for code, season in feed.targets():
                assert len(wb.events.match_ids(code, season)) == 5
                status = wb.events.status(code, season)
                assert status["running"] is False and status["done"] == 5 and status["total"] == 5 and status["finished"] >= status["started"]
            assert wb.events.pending_rebuild() == 0
            for code, season in feed.targets():                                  # the Understat-shaped match pages are stored too: scorers and shot locations
                fetched = await wb.seasons.load(code, season)
                assert wb.matchsync.coverage(fetched.data)[0] == 5
            first = wb.events.match_ids("EPL", 2020)
            stored = wb.store.get("ws_raw", f"EPL:2020:{first[0]}")
            again = DemoEventFeed(wb, limit=5, seasons_back=0)
            again.start()
            await again.wait()
            assert wb.events.match_ids("EPL", 2020) == first
            assert wb.store.get("ws_raw", f"EPL:2020:{first[0]}").fetched_at == stored.fetched_at       # an existing match is left alone
        finally:
            await wb.close()
    asyncio.run(go())


def test_current_seasons_come_before_older_ones(tmp_path):
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=TODAY)
    feed = DemoEventFeed(wb, seasons_back=1)
    order = feed.targets()
    assert [s for _, s in order[:5]] == [2020] * 5 and [s for _, s in order[5:]] == [2019] * 5
    assert order[0][0] == "EPL"
    asyncio.run(wb.close())


def test_with_the_feed_on_scout_and_the_team_page_get_real_event_metrics(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, demo=True, demo_events=True, min_interval=0), today=TODAY)
    with TestClient(app) as c:
        deadline = time.time() + 120
        status = {}
        while time.time() < deadline:
            status = c.get("/api/data/status").json()
            rows = [e for e in status["events"] if e["league"] == "EPL" and e["season"] == 2020]
            if rows and rows[0]["status"] and not rows[0]["status"]["running"] and rows[0]["status"].get("finished"):
                break
            time.sleep(0.5)
        else:
            raise AssertionError(f"the demo event feed did not finish an EPL season in time: {status.get('events')}")
        body = c.get("/api/players", params={"leagues": "EPL", "seasons": "2020", "min_minutes": 1}).json()
        cov = body["coverage"]
        assert cov["event_players"] > 0.85 * cov["players"]                         # every regular is linked to his event record
        stored, played = cov["shots"]["EPL:2020"]
        assert stored == played > 100                                              # and every match page is stored: nothing is "still downloading"
        keys = body["keys"]
        row = max((r for r in body["rows"] if r["group"] == "DEF" and r["ev_minutes"] and r["ev_minutes"] > 500), key=lambda r: r["ev_minutes"])
        assert row["v"][keys.index("tackles90")] is not None and row["v"][keys.index("pass_acc")] is not None
        club = row["teams"][0]
        teams = c.get("/api/teams", params={"leagues": "EPL", "seasons": "2020"}).json()
        t = next(t for t in teams["rows"] if t["team"] == club)
        assert t["v"][teams["keys"].index("poss")] is not None and 0.3 <= t["v"][teams["keys"].index("poss")] <= 0.7
    # stopping the app mid-feed must be clean (the feed is cancelled, the store closes) -- reaching here proves it


def test_a_demo_database_made_by_an_older_world_is_started_afresh_and_keeps_the_shortlist(tmp_path):
    from app.data.demo import WORLD_VERSION

    settings = Settings(data_dir=tmp_path, demo=True, min_interval=0)
    first = Workbench(settings, today=TODAY)
    assert first.store.kv_get("demo:world") == WORLD_VERSION
    first.store.put("match", "1", {"stale": True}, source="demo", complete=True)
    first.store.kv_set("demo:world", WORLD_VERSION - 1)                     # as an older version left it
    first.store.kv_set("events:run:EPL:2019", {"running": False})
    first.shortlist.add({"id": 7, "name": "Kept"})
    asyncio.run(first.close())

    again = Workbench(settings, today=TODAY)
    assert again.store.get("match", "1") is None and again.store.kv_get("events:run:EPL:2019") is None
    assert again.store.kv_get("demo:world") == WORLD_VERSION and [i["id"] for i in again.shortlist.items()] == [7]
    again.store.put("match", "2", {"fresh": True}, source="demo", complete=True)
    asyncio.run(again.close())

    third = Workbench(settings, today=TODAY)                                  # a copy made by this version is left alone
    assert third.store.get("match", "2") is not None
    asyncio.run(third.close())
