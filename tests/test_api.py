"""The HTTP API end to end, on the demo world (no network)."""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import date

import pytest
from starlette.testclient import TestClient

from app.api import _clean, create_app
from app.config import Settings


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(data_dir=tmp_path_factory.mktemp("prem"), demo=True, min_interval=0)
    app = create_app(settings, today=date(2021, 1, 15))  # 2020 season is mid-way; 2019 is complete
    with TestClient(app) as c:
        yield c


def get(client, path, **params):
    return client.get(path, params=params)


# ------------------------------------------------------------------ meta


def test_health_meta_and_catalog(client):
    assert get(client, "/api/health").json()["status"] == "ok"
    meta = get(client, "/api/meta").json()
    assert meta["mode"]["demo"] and meta["mode"]["source"] == "demo" and meta["today"] == "2021-01-15"
    assert [l["code"] for l in meta["leagues"]] == ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
    assert meta["seasons"][0] == {"season": 2020, "label": "2020/21"} and meta["defaults"]["season"] == "auto"
    catalog = get(client, "/api/catalog").json()
    assert catalog["metrics"]["npxg90"]["higher_is_better"] and catalog["profiles"]["ATT"][0] == "npxg90"
    assert any(g["group"] == "Chances" for g in catalog["glossary"]["groups"])


def test_unknown_routes_and_bad_params_use_the_error_format(client):
    missing = get(client, "/api/nope")
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"
    bad = get(client, "/api/league", league="Atlantis")
    assert bad.status_code == 422 and bad.json()["error"] == "invalid_parameters" and "Unknown league" in bad.json()["message"]
    assert get(client, "/api/league", venue="sideways").status_code == 422
    assert get(client, "/api/players", min_minutes="lots").status_code == 422


def test_json_cleaning_handles_numpy_and_nan():
    import numpy as np

    assert _clean({"a": np.float64(1.5), "b": [np.int64(2), float("nan")], "c": (float("inf"),), "d": np.array([1, 2])}) == {"a": 1.5, "b": [2, None], "c": [None], "d": [1, 2]}


# ------------------------------------------------------------------ briefing, league, team


def test_briefing(client):
    body = get(client, "/api/briefing", league="EPL", season="auto").json()
    assert body["scope"]["season"] == 2020 and body["scope"]["label"] == "2020/21" and not body["scope"]["complete"]
    assert len(body["table"]) == 20 and body["table"][0]["rank"] == 1 and body["insights"]
    assert body["recent"] and body["upcoming"] and body["race"] and len(body["race"]) == 20
    assert sum(t["p_title"] for t in body["race"]) == pytest.approx(1.0, abs=0.02)
    assert body["meta"]["source"] == "demo" and not body["meta"]["stale"]
    for insight in body["insights"]:
        assert insight["headline"] and 0 <= insight["score"] <= 100


def test_league_table_and_filters(client):
    overall = get(client, "/api/league", season="2019").json()
    assert overall["scope"]["complete"] and len(overall["table"]) == 20
    assert overall["table"][0]["played"] == 38 and overall["trajectories"]["rounds"] == 38
    home = get(client, "/api/league", season="2019", venue="h").json()["table"]
    assert all(r["played"] == 19 for r in home)
    last5 = get(client, "/api/league", season="2019", last=5).json()["table"]
    assert all(r["played"] == 5 for r in last5)
    assert get(client, "/api/league", season="2019", last=0).status_code == 422


def test_team_history_compares_seasons_and_flags_the_ones_it_cannot_load(client):
    body = get(client, "/api/team/history", team="arsenal", seasons="2019,2020").json()
    assert body["team"] == "Arsenal" and [s["season"] for s in body["seasons"]] == [2020, 2019]
    done, live = body["seasons"][1], body["seasons"][0]
    assert done["available"] and done["complete"] and len(done["points"]) == 38
    assert live["available"] and not live["complete"] and len(live["points"]) < 38
    assert body["rounds_max"] == 38 and body["n_teams_max"] == 20 and body["scope"]["league"] == "EPL"

    partial = get(client, "/api/team/history", team="Arsenal", seasons="2019,2015").json()  # the demo world starts in 2019
    gone = next(s for s in partial["seasons"] if s["season"] == 2015)
    assert not gone["available"] and gone["reason"] and next(s for s in partial["seasons"] if s["season"] == 2019)["available"]


def test_team_history_defaults_and_validation(client):
    default = get(client, "/api/team/history", team="Arsenal").json()  # newest 5 seasons: 2020..2016
    assert [s["season"] for s in default["seasons"]] == [2020, 2019, 2018, 2017, 2016]
    assert [s["season"] for s in default["seasons"] if s["available"]] == [2020, 2019]

    missing = get(client, "/api/team/history", team="Nowhere FC", seasons="2019")
    assert missing.status_code == 404 and missing.json()["hint"]
    assert get(client, "/api/team/history", team="Arsenal", seasons="2019,abc").status_code == 422
    too_many = get(client, "/api/team/history", team="Arsenal", seasons=",".join(str(y) for y in range(2010, 2019)))
    assert too_many.status_code == 422 and "at most" in too_many.json()["message"]


def test_team_view_and_chances(client):
    body = get(client, "/api/team", team="Arsenal", season="2019").json()
    profile = body["profile"]
    assert profile["team"]["team"] == "Arsenal" and len(profile["matches"]) == 38 and body["insights"]
    assert len(body["teams"]) == 20 and get(client, "/api/team", team="arsenal", season="2019").status_code == 200
    unknown = get(client, "/api/team", team="Nowhere FC", season="2019")
    assert unknown.status_code == 404 and unknown.json()["hint"]
    chances = get(client, "/api/team/chances", team="Arsenal", season="2019").json()
    keys = [b["key"] for b in chances["breakdowns"]]
    assert {"situation", "timing", "shotZone", "gameState", "attackSpeed", "formation", "result"} <= set(keys)
    assert set(chances["insights"]) == set(keys) and chances["games"] == 38


def test_team_chances_are_named_ordered_and_explained(client):
    body = get(client, "/api/team/chances", team="Arsenal", season="2019").json()
    by = {b["key"]: b for b in body["breakdowns"]}
    assert all(b["guide"]["what"] and b["guide"]["read"] and b["guide"]["good"] and b["guide"]["bad"] and b["blurb"] for b in body["breakdowns"])
    assert {k: b["viz"] for k, b in by.items()} == {"situation": "bars", "shotZone": "pitch", "timing": "columns", "gameState": "columns", "attackSpeed": "columns", "formation": "bars", "result": "outcome"}
    assert [r["label"] for r in by["timing"]["rows"]] == ["1–15 min", "16–30 min", "31–45 min", "46–60 min", "61–75 min", "76+ min"]
    assert [r["label"] for r in by["shotZone"]["rows"]] == ["Outside the box", "Penalty area", "Six-yard box"]  # far to near, and no fake 'own goals' zone
    assert by["gameState"]["rows"][0]["label"] == "Behind by 2+" and by["gameState"]["rows"][-1]["label"] == "Ahead by 2+"
    assert all(r["hint"] for b in body["breakdowns"] if b["key"] != "formation" for r in b["rows"])
    situation = by["situation"]["rows"]
    assert sum(r["share_for"] for r in situation) == pytest.approx(1.0, abs=0.01) and by["situation"]["unit"] == "game"
    assert by["formation"]["unit"] == "90" and by["formation"]["rows"][0]["time"] >= by["formation"]["rows"][-1]["time"]


def test_team_chances_against_the_league_is_optional_context(client):
    body = get(client, "/api/team/chances/league", team="Arsenal", season="2019").json()
    assert body["available"] and body["loaded"] == body["of"] == 20
    stat = body["comparison"]["situation"]["OpenPlay"]["per_for"]
    assert 1 <= stat["rank"] <= stat["of"] == 20 and "avg" in stat and "z" in stat
    assert "formation" not in body["comparison"]  # formation names do not line up across teams
    assert set(body["insights"]) >= {"situation", "shotZone", "timing"}
    assert get(client, "/api/team/chances/league", team="Nowhere FC", season="2019").status_code == 404


def test_auto_season_falls_back_when_the_new_season_is_barely_started(tmp_path):
    early = create_app(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2020, 8, 25))  # one round played
    with TestClient(early) as c:
        body = c.get("/api/league", params={"season": "auto"}).json()
        assert body["scope"]["season"] == 2019 and "only" in body["scope"]["note"] and body["scope"]["complete"]
        assert c.get("/api/league", params={"season": "2020"}).json()["scope"]["note"] is None  # explicit choice is respected


# ------------------------------------------------------------------ players


def test_scouting_dataset(client):
    body = get(client, "/api/players", leagues="EPL", seasons="2019").json()
    rows = body["rows"]
    assert 400 < len(rows) < 700 and body["scope"]["pool_minutes"] == 840 and body["scope"]["labels"] == ["2019/20"]
    assert {"id", "name", "team", "group", "age", "pct", "tags", "minutes", "npxg90", "output", "in_pool"} <= set(rows[0])
    assert body["coverage"]["ages_known"] > 400 and body["highlights"]
    assert body["enrichment"]["ages"]["kind"] == "ages"
    few = get(client, "/api/players", leagues="EPL", seasons="2019", min_minutes=1800).json()["rows"]
    assert 0 < len(few) < len(rows) and all(r["minutes"] >= 1800 for r in few)


def test_multi_season_and_multi_league_dataset(client):
    two = get(client, "/api/players", leagues="EPL", seasons="2019,2020").json()
    assert two["scope"]["seasons"] == [2019, 2020]
    both = get(client, "/api/players", leagues="EPL,La_liga", seasons="2019").json()
    assert set(r["league"] for r in both["rows"]) == {"EPL", "La_liga"} and len(both["rows"]) > 900


def test_player_detail_similar_and_shortlist_flag(client):
    rows = get(client, "/api/players", leagues="EPL", seasons="2019").json()["rows"]
    star = max((r for r in rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: r["output"])
    body = get(client, f"/api/player/{star['id']}", league="EPL", season="2019").json()
    assert body["detail"]["player"]["name"] == star["name"] and body["detail"]["finishing"]["shots"] == star["shots"]
    assert len(body["detail"]["shots"]) == star["shots"] and body["detail"]["career"] and body["insights"] and len(body["similar"]) == 8
    assert body["detail"]["blocks"][0]["category"] == "Shooting" and body["shortlisted"] is False
    assert body["detail"]["player"]["favorite"]  # position confirmed from his player page on first open

    young = get(client, f"/api/player/{star['id']}/similar", league="EPL", seasons="2019", max_age=23, limit=5).json()
    assert young["target"] == star["name"] and all(s["age"] is not None and s["age"] <= 23 for s in young["similar"])
    assert get(client, "/api/player/999999999", league="EPL", season="2019").status_code in (404, 502)


def test_player_falls_back_to_a_season_he_played(client):
    rows = get(client, "/api/players", leagues="EPL", seasons="2019").json()["rows"]
    now = {r["id"] for r in get(client, "/api/players", leagues="EPL", seasons="2020").json()["rows"]}
    gone = next((r for r in rows if r["in_pool"] and r["id"] not in now), None)
    if gone is None:
        pytest.skip("every 2019 regular also played in 2020")
    body = get(client, f"/api/player/{gone['id']}", league="EPL", season="2020").json()
    assert body["scope"]["seasons"] == [2019] and "no 2020/21 minutes" in body["scope"]["note"]


def test_compare(client):
    rows = get(client, "/api/players", leagues="EPL", seasons="2019").json()["rows"]
    atts = sorted((r for r in rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: -r["output"])[:3]
    body = get(client, "/api/compare/players", ids=",".join(str(r["id"]) for r in atts), league="EPL", season="2019").json()
    assert [p["name"] for p in body["players"]] == [r["name"] for r in atts]
    assert body["metrics"][0]["key"] == "npxg90" and all(len(m["values"]) == 3 for m in body["metrics"]) and not body["mixed_groups"]
    assert get(client, "/api/compare/players", ids=str(atts[0]["id"]), league="EPL", season="2019").status_code == 422
    keeper = next(r for r in rows if r["group"] == "GK")
    assert get(client, "/api/compare/players", ids=f"{atts[0]['id']},{keeper['id']}", league="EPL", season="2019").status_code == 422
    teams = get(client, "/api/compare/teams", a="Arsenal", b="Chelsea", league="EPL", season="2019").json()
    assert len(teams["meetings"]) == 2 and teams["a"]["team"] == "Arsenal" and len(teams["metrics"]) == 11
    assert get(client, "/api/compare/teams", a="Arsenal", b="Arsenal", league="EPL", season="2019").status_code == 422


# ------------------------------------------------------------------ matches & forecasts


def test_matches_and_match_report(client):
    body = get(client, "/api/matches", league="EPL", season="2020").json()
    assert body["latest_round"] and len(body["rounds"]) == 38
    played = next(m for r in body["rounds"] for m in r["matches"] if m["played"])
    unplayed = next(m for r in body["rounds"] for m in r["matches"] if not m["played"])
    report = get(client, f"/api/match/{played['id']}", league="EPL", season="2020").json()
    assert report["report"]["fixture"]["home"] == played["home"] and report["insights"]
    assert report["report"]["deserved"]["home"] + report["report"]["deserved"]["away"] + report["report"]["deserved"]["draw"] == pytest.approx(1.0, abs=1e-3)
    assert get(client, f"/api/match/{unplayed['id']}", league="EPL", season="2020").status_code == 422
    assert get(client, "/api/match/1", league="EPL", season="2020").status_code == 404


def test_forecasts(client):
    fixtures = get(client, "/api/forecast/fixtures", league="EPL", season="2020").json()
    assert fixtures["fixtures"] and fixtures["model"]["weights"] == {"ratings": 0.7, "elo": 0.3}
    first = fixtures["fixtures"][0]
    assert first["p_home"] + first["p_draw"] + first["p_away"] == pytest.approx(1.0, abs=2e-3)
    single = get(client, "/api/forecast/match", home="Arsenal", away="Chelsea", league="EPL", season="2020").json()
    assert len(single["forecast"]["matrix"]) == 9 and len(single["teams"]) == 20
    assert get(client, "/api/forecast/match", home="Arsenal", away="Arsenal", league="EPL", season="2020").status_code == 422
    season = get(client, "/api/forecast/season", league="EPL", season="2020", sims=1000).json()["simulation"]
    assert season["n_sims"] == 1000 and sum(t["p_title"] for t in season["teams"]) == pytest.approx(1.0, abs=0.03)
    cal = get(client, "/api/forecast/calibration", league="EPL", season="2019").json()["calibration"]
    assert cal["skill_vs_baseline"] > 0 and cal["models"]["ensemble"]["brier"] < cal["models"]["baseline"]["brier"]


# ------------------------------------------------------------------ search, shortlist, data


def test_search_players_and_teams(client):
    get(client, "/api/briefing", league="EPL", season="2020")  # ensures a league is cached
    assert get(client, "/api/search", q="a").json() == {"players": [], "teams": []}  # too short
    teams = get(client, "/api/search", q="arse").json()["teams"]
    assert teams and teams[0]["name"] == "Arsenal"
    rows = get(client, "/api/players", leagues="EPL", seasons="2020").json()["rows"]
    accented = next(r for r in rows if any(ord(c) > 127 for c in r["name"]))
    plain = "".join(c for c in accented["name"].split()[-1].lower() if ord(c) < 128)
    found = get(client, "/api/search", q=accented["name"].split()[-1][:5]).json()["players"]
    assert any(p["id"] == accented["id"] for p in found)
    exact = get(client, "/api/search", q=accented["name"].lower()).json()["players"]
    assert exact[0]["id"] == accented["id"]


def test_shortlist_roundtrip_and_flag(client):
    assert get(client, "/api/shortlist").json() == {"items": []}
    rows = get(client, "/api/players", leagues="EPL", seasons="2019").json()["rows"]
    r = next(x for x in rows if x["in_pool"] and x["group"] == "MID")
    put = client.put(f"/api/shortlist/{r['id']}", json={"name": r["name"], "team": r["team"], "league": "EPL", "note": "Watch his progressive passing"})
    assert put.status_code == 200 and put.json()["items"][0]["note"] == "Watch his progressive passing"
    assert get(client, f"/api/player/{r['id']}", league="EPL", season="2019").json()["shortlisted"] is True
    client.put(f"/api/shortlist/{r['id']}", json={"note": "Updated note"})
    items = get(client, "/api/shortlist").json()["items"]
    assert len(items) == 1 and items[0]["note"] == "Updated note" and items[0]["name"] == r["name"]  # merge keeps identity
    assert client.delete(f"/api/shortlist/{r['id']}").json() == {"items": []}


def test_data_status_and_sync_job(client):
    status = get(client, "/api/data/status").json()
    assert status["mode"]["demo"] and status["store"]["total_items"] > 0 and any(l["league"] == "EPL" for l in status["leagues"])
    job = client.post("/api/data/sync", json={"leagues": ["EPL", "Ligue_1"], "seasons": [2019, 2020]}).json()
    assert job["total"] == 4 and job["state"] in ("running", "finished")
    for _ in range(60):
        polled = get(client, f"/api/data/jobs/{job['id']}").json()
        if polled["state"] != "running":
            break
        time.sleep(0.5)
    assert polled["state"] == "finished" and polled["done"] == 4 and polled["failed"] == 0 and len(polled["log"]) == 4
    assert client.post("/api/data/sync", json={"leagues": ["Nope"]}).status_code == 422
    assert get(client, "/api/data/jobs/deadbeef").status_code == 500 or get(client, "/api/data/jobs/deadbeef").json()["error"]


def test_offline_mode_refuses_to_sync_and_serves_the_cache(tmp_path):
    from app.data.repository import Repository

    settings = Settings(data_dir=tmp_path, demo=True, min_interval=0)
    with TestClient(create_app(settings, today=date(2021, 1, 15))) as warm:
        assert warm.get("/api/league", params={"season": "2019"}).status_code == 200
    cold = Settings(data_dir=tmp_path, demo=True, offline=True, min_interval=0)
    with TestClient(create_app(cold, today=date(2021, 1, 15))) as c:
        assert c.get("/api/league", params={"season": "2019"}).status_code == 200  # cached
        missing = c.get("/api/league", params={"season": "2019", "league": "La_liga"})
        assert missing.status_code == 503 and missing.json()["error"] == "data_unavailable" and missing.json()["hint"]
        assert c.post("/api/data/sync", json={"leagues": ["EPL"]}).status_code == 503


# ------------------------------------------------------------------ connection check


def test_connection_check_walks_the_data_path_on_the_demo_world(client):
    result = client.post("/api/data/check").json()
    assert result["ok"] and result["mode"]["demo"]
    assert [s["name"] for s in result["steps"]] == ["Load the league", "Read the league page", "Read a match", "Read a player", "Look up birthdates"]
    assert all(s["ok"] and isinstance(s["ms"], int) for s in result["steps"])
    assert "20 teams" in result["steps"][1]["detail"]


def test_your_own_birthdate_corrections_win(tmp_path):
    from app.workbench import Workbench

    (tmp_path / "birthdates.json").write_text(json.dumps({"Sávio": "2004-04-10", "Pablo Ibáñez|Alaves": "1998-08-03", "Broken": "not a date"}))
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2026, 10, 1))
    try:
        assert wb.dob_info("Sávio", ["Manchester City"]) == ("2004-04-10", "manual")
        assert wb.dob_info("Pablo Ibáñez", ["Alaves"]) == ("1998-08-03", "manual")  # name and club together
        assert wb.dob_info("Pablo Ibáñez", ["Elche"])[1] != "manual"  # a different club is a different man
        assert wb.dob_info("Broken", [])[1] != "manual"
    finally:
        asyncio.run(wb.close())
