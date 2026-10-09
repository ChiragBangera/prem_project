"""The HTTP API end to end, on the demo world (no network)."""

from __future__ import annotations

import asyncio
import json
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


def val(body, row, key):
    """A metric's value in a scouting row (rows carry two arrays aligned with the dataset's ``keys``)."""
    return row["v"][body["keys"].index(key)]


def pct(body, row, key):
    return row["p"][body["keys"].index(key)]


# ------------------------------------------------------------------ meta


def test_health_meta_and_catalog(client):
    assert get(client, "/api/health").json()["status"] == "ok"
    meta = get(client, "/api/meta").json()
    assert meta["mode"]["demo"] and meta["mode"]["source"] == "demo" and meta["today"] == "2021-01-15"
    assert [lg["code"] for lg in meta["leagues"]] == ["EPL", "La_liga", "Bundesliga", "Serie_A", "Ligue_1"]
    assert meta["seasons"][0] == {"season": 2020, "label": "2020/21"} and meta["defaults"]["season"] == "auto"
    catalog = get(client, "/api/catalog").json()
    metric = catalog["player"]["metrics"]["npxg90"]
    assert metric["hib"] is True and metric["formula"] and metric["what"] and metric["needs"] == "base" and catalog["player"]["profile"]["role"]["ATT"][0] == "npxg90"
    assert len(catalog["player"]["metrics"]) > 100 and len(catalog["team"]["metrics"]) > 90
    assert {"enabled", "running", "next_at", "next_reason", "finished", "errors", "backlog", "events_running"} == set(meta["auto"]) and meta["auto"]["enabled"] is False   # the top-bar pill reads this; demo never updates itself
    tags = catalog["player"]["tags"]                                           # the Profile filter and the dictionary are built from this list
    assert {t["group"] for t in tags} == {"ATT", "MID", "DEF", "GK"} and all(t["explain"] and t["rules"] for t in tags)
    assert all(r["metrics"][0] in catalog["player"]["metrics"] for t in tags for r in t["rules"])
    assert {g["key"] for g in catalog["player"]["groups"]} >= {"shooting", "passing", "defending", "goalkeeping"}
    assert [v["key"] for v in catalog["player"]["views"]][:2] == ["overview", "attacking"] and catalog["team"]["views"] and catalog["roles"]["order"] == ["ATT", "MID", "DEF", "GK"]
    # every lens, view and score recipe names metrics that exist: nothing in the catalogue points at a missing number
    for level in ("player", "team"):
        known = set(catalog[level]["metrics"])
        assert all(m in known for v in catalog[level]["views"] for m in v["metrics"])
        assert all(r["metric"] in known for lens in catalog[level]["lenses"] for r in lens["rules"])
        assert all(lens["explain"] and lens["rules"] for lens in catalog[level]["lenses"])


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
    assert body["recent"] and body["upcoming"] and "race" not in body and body["gaps"]["title"] >= 0
    assert all("p_home" not in f and f["home_rank"] and f["utc"].endswith("Z") for f in body["upcoming"])
    assert body["meta"]["source"] == "demo" and not body["meta"]["stale"]
    for insight in body["insights"]:
        assert insight["headline"] and 0 <= insight["score"] <= 100


def test_briefing_cards_carry_scorers_and_shots_once_their_match_pages_are_stored(client):
    recent = get(client, "/api/briefing", league="EPL", season="2020").json()["recent"]
    first = recent[0]
    assert get(client, f"/api/match/{first['id']}", league="EPL", season="2020").status_code == 200
    card = get(client, "/api/briefing", league="EPL", season="2020").json()["recent"][0]
    assert card["id"] == first["id"] and set(card["scorers"]) == {"h", "a"}
    assert len(card["scorers"]["h"]) + len(card["scorers"]["a"]) == card["hg"] + card["ag"]
    assert card["shots"]["h"] >= card["sot"]["h"] and card["shots"]["a"] >= card["sot"]["a"]


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
    assert {"id", "name", "team", "group", "age", "tags", "v", "p", "in_pool", "pos2", "sample"} <= set(rows[0])
    assert len(body["keys"]) > 100 and all(len(r["v"]) == len(r["p"]) == len(body["keys"]) for r in rows)
    assert {"npxg90", "tklint90", "save_pct", "output", "score_full", "age", "minutes"} <= set(body["keys"])
    assert body["coverage"]["ages_known"] > 400 and body["highlights"]
    assert body["enrichment"]["ages"]["kind"] == "ages"
    # nothing is filtered on the server except a one-minute floor: every role, goalkeepers included, is in the payload
    assert {r["group"] for r in rows} == {"ATT", "MID", "DEF", "GK"}
    few = get(client, "/api/players", leagues="EPL", seasons="2019", min_minutes=1800).json()
    assert 0 < len(few["rows"]) < len(rows) and all(val(few, r, "minutes") >= 1800 for r in few["rows"])
    # unknown is blank, not zero: the demo world has no event data, so no event metric has a value for anyone
    assert all(val(body, r, "tackles90") is None and val(body, r, "pass_acc") is None for r in rows)
    star = max((r for r in rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: val(body, r, "output"))
    assert pct(body, star, "npxg90") is not None and val(body, star, "score_full") is None


def test_multi_season_and_multi_league_dataset(client):
    two = get(client, "/api/players", leagues="EPL", seasons="2019,2020").json()
    assert two["scope"]["seasons"] == [2019, 2020]
    both = get(client, "/api/players", leagues="EPL,La_liga", seasons="2019").json()
    assert {r["league"] for r in both["rows"]} == {"EPL", "La_liga"} and len(both["rows"]) > 900


def test_player_detail_similar_and_shortlist_flag(client):
    ds = get(client, "/api/players", leagues="EPL", seasons="2019").json()
    star = max((r for r in ds["rows"] if r["in_pool"] and r["group"] == "ATT"), key=lambda r: val(ds, r, "output"))
    body = get(client, f"/api/player/{star['id']}", league="EPL", season="2019").json()
    shots = val(ds, star, "shots")
    assert body["detail"]["player"]["name"] == star["name"] and body["detail"]["finishing"]["shots"] == shots
    assert len(body["detail"]["shots"]) == shots and body["detail"]["career"] and body["insights"] and len(body["similar"]) == 8
    assert [b["group"] for b in body["detail"]["blocks"]][:2] == ["availability", "shooting"] and body["shortlisted"] is False
    shooting = next(b for b in body["detail"]["blocks"] if b["group"] == "shooting")
    assert all(i["formula"] and i["what"] and i["pool_n"] for i in shooting["items"] if i["pct"] is not None)
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
    ds = get(client, "/api/players", leagues="EPL", seasons="2019").json()
    rows = ds["rows"]
    atts = sorted((r for r in rows if r["in_pool"] and r["group"] == "ATT"), key=lambda r: -val(ds, r, "output"))[:3]
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


def test_match_players_carry_every_metric_for_that_match_alone(client):
    body = get(client, "/api/matches", league="EPL", season="2020").json()
    played = next(m for r in body["rounds"] for m in r["matches"] if m["played"])
    mid = played["id"]
    d = get(client, f"/api/match/{mid}/players", league="EPL", season="2020").json()
    assert d["rows"] and {r["side"] for r in d["rows"]} == {"h", "a"}
    assert all(r["minutes"] > 0 and len(r["v"]) == len(d["keys"]) == len(r["p"]) for r in d["rows"])
    keys = d["keys"]
    assert "age" not in keys and "games" not in keys                 # season-long figures mean nothing for one match
    i = {k: n for n, k in enumerate(keys)}
    report = get(client, f"/api/match/{mid}", league="EPL", season="2020").json()["report"]
    # goals and xG of the match, added up over the players, are the match's
    for side, key in (("h", "home"), ("a", "away")):
        rows = [r for r in d["rows"] if r["side"] == side]
        assert sum(r["v"][i["goals"]] or 0 for r in rows) == sum(p["goals"] for p in report["players"][key])
    # a count has no percentile; a percentile is 0-100 and absent for a cameo
    assert all(r["p"][i["goals"]] is None for r in d["rows"])
    assert all(0 <= p <= 100 for r in d["rows"] for p in r["p"] if p is not None)
    assert all(not r["in_pool"] and all(p is None for p in r["p"]) for r in d["rows"] if r["minutes"] < 30)
    assert get(client, "/api/match/1/players", league="EPL", season="2020").status_code == 404


def test_match_players_are_the_trend_arithmetic(client):
    """A player's number for a match is the number his match trend shows for that match: one set of formulas."""
    body = get(client, "/api/matches", league="EPL", season="2020").json()
    mid = next(m for r in body["rounds"] for m in r["matches"] if m["played"])["id"]
    d = get(client, f"/api/match/{mid}/players", league="EPL", season="2020").json()
    keys = d["keys"]
    starter = max((r for r in d["rows"] if r["minutes"] >= 90 and r["group"] != "GK"), key=lambda r: r["v"][keys.index("shots")] or 0)
    trend = get(client, f"/api/player/{starter['id']}/trend", league="EPL", season="2020").json()
    at = next(i for i, m in enumerate(trend["matches"]) if m["match_id"] == mid)
    checked = 0
    for k in keys:
        if k in trend["series"]:
            assert trend["series"][k]["m"][at] == pytest.approx(starter["v"][keys.index(k)], abs=1e-9), k
            checked += 1
    assert checked > 20


def test_forecasting_has_been_retired(client):
    for path in ("/api/forecast/fixtures", "/api/forecast/match", "/api/forecast/season", "/api/forecast/calibration"):
        assert get(client, path).status_code == 404


def test_matches_carry_scorers_and_kickoffs_in_utc_once_match_pages_are_stored(client):
    league = get(client, "/api/matches", league="EPL", season="2019").json()
    assert league["coverage"]["played"] == 380
    ids = [m["id"] for r in league["rounds"][:2] for m in r["matches"]]
    for mid in ids:  # opening a match report stores its page; the list then carries scorers for it
        assert get(client, f"/api/match/{mid}", league="EPL", season="2019").status_code == 200
    again = get(client, "/api/matches", league="EPL", season="2019").json()
    card = next(m for r in again["rounds"] for m in r["matches"] if m["id"] == ids[0])
    assert card["utc"].endswith("Z") and "scorers" in card and set(card["scorers"]) == {"h", "a"}
    assert len(card["scorers"]["h"]) + len(card["scorers"]["a"]) == card["hg"] + card["ag"]
    assert all(g["kind"] in ("goal", "pen", "og") and g["player"] for side in card["scorers"].values() for g in side)
    assert card["shots"]["h"] >= card["sot"]["h"]


# ------------------------------------------------------------------ teams, the dictionary, caching


def test_teams_dataset_ranks_each_team_within_its_own_league_and_season(client):
    body = get(client, "/api/teams", leagues="EPL,La_liga", seasons="2019").json()
    assert body["scope"]["n"] == 40 and set(body["scope"]["pools"]) == {"EPL:2019", "La_liga:2019"} and all(n == 20 for n in body["scope"]["pools"].values())
    keys = body["keys"]
    assert {"xg_pg", "xga_pg", "ppda", "poss", "pts_xpts"} <= set(keys)
    row = next(r for r in body["rows"] if r["team"] == "Arsenal")
    assert len(row["v"]) == len(row["p"]) == len(keys) and row["rank"] and row["league"] == "EPL"
    # percentiles compare a team with its own league: the best xG in each league is near the top of its own
    best = max((r for r in body["rows"] if r["league"] == "La_liga"), key=lambda r: r["v"][keys.index("xg_pg")])
    assert best["p"][keys.index("xg_pg")] >= 90
    # event metrics are blank, not zero, where no event data exists
    assert row["v"][keys.index("poss")] is None and row["v"][keys.index("tackles_pg")] is None


def test_dictionary_explains_every_metric_and_the_raw_data_behind_it(client):
    d = get(client, "/api/dictionary").json()
    keys = {(m["level"], m["key"]) for m in d["metrics"]}
    assert ("player", "npxg90") in keys and ("team", "ppda") in keys and len(d["metrics"]) > 200
    for m in d["metrics"]:
        assert m["formula"] and m["what"] and m["kind"] in ("raw", "derived") and m["source"] and m["group_label"], m["key"]
    assert {s["key"] for s in d["sources"]} >= {"understat", "whoscored", "espn"} and all(s["parts"] or s["key"] == "wikidata" for s in d["sources"])
    assert len(d["counters"]) > 100 and len(d["events"]) > 30 and d["concepts"]
    stats = get(client, "/api/dictionary/stats", league="EPL", season="2019").json()
    q = stats["players"]["npxg90"]["ATT"]
    assert q[0] > 8 and q[1:] == sorted(q[1:]) and stats["teams"]["xg_pg"][0] == 20


def test_maps_say_so_when_there_is_no_event_data_instead_of_drawing_nothing(client):
    team = get(client, "/api/maps/team", team="Arsenal", league="EPL", season="2019").json()
    assert team["available"] is False and team["reason"]
    ds = get(client, "/api/players", leagues="EPL", seasons="2019").json()
    player = get(client, f"/api/maps/player/{ds['rows'][0]['id']}", league="EPL", season="2019").json()
    assert player["available"] is False
    shots = get(client, "/api/team/shots", team="Arsenal", league="EPL", season="2019").json()
    assert (shots["coverage"][1] == 380 and shots["for"] == []) or shots["matches"] >= 0


def test_unchanged_answers_are_revalidated_with_a_304(client):
    first = client.get("/api/teams", params={"leagues": "EPL", "seasons": "2019"})
    etag = first.headers["etag"]
    assert etag and first.headers["cache-control"] == "no-cache"
    again = client.get("/api/teams", params={"leagues": "EPL", "seasons": "2019"}, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""
    assert client.get("/api/teams", params={"leagues": "EPL", "seasons": "2019"}, headers={"If-None-Match": 'W/"stale"'}).status_code == 200
    assert "etag" not in client.get("/api/data/status").headers  # live status is never cached


# ------------------------------------------------------------------ search, shortlist, data


def test_search_players_and_teams(client):
    get(client, "/api/briefing", league="EPL", season="2020")  # ensures a league is cached
    assert get(client, "/api/search", q="a").json() == {"players": [], "teams": []}  # too short
    teams = get(client, "/api/search", q="arse").json()["teams"]
    assert teams and teams[0]["name"] == "Arsenal"
    rows = get(client, "/api/players", leagues="EPL", seasons="2020").json()["rows"]
    accented = next(r for r in rows if any(ord(c) > 127 for c in r["name"]))
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


def test_favourite_teams_roundtrip(client):
    assert get(client, "/api/favourites").json() == {"teams": []}
    put = client.put("/api/favourites/teams", json={"league": "EPL", "team": "Arsenal"})
    assert put.status_code == 200 and [(t["league"], t["team"]) for t in put.json()["teams"]] == [("EPL", "Arsenal")]
    assert client.put("/api/favourites/teams", json={"league": "Nowhere", "team": "Arsenal"}).status_code == 422
    assert get(client, "/api/favourites").headers.get("etag") is None            # always live, never answered from a cache
    assert client.put("/api/favourites/teams", json={"league": "EPL", "team": "Arsenal", "favourite": False}).json() == {"teams": []}


def test_the_live_view_of_a_match_answers_for_played_and_unplayed_fixtures(client):
    rounds = get(client, "/api/matches", league="EPL", season="2020").json()["rounds"]
    played = next(m for r in rounds for m in r["matches"] if m["played"])
    upcoming = next(m for r in rounds for m in r["matches"] if not m["played"])
    a = get(client, f"/api/match/{played['id']}/live", league="EPL", season="2020").json()
    assert a["fixture"]["played"] is True and a["phase"] == "played"
    b = get(client, f"/api/match/{upcoming['id']}/live", league="EPL", season="2020", follow=1).json()
    assert b["fixture"]["played"] is False and b["read"] is None and b["events_on"] is False and b["followed"] is None   # the demo reads nothing live
    assert client.get("/api/match/999999/live", params={"league": "EPL", "season": "2020"}).status_code == 404


def test_data_status_and_sync_job(client):
    status = get(client, "/api/data/status").json()
    assert status["mode"]["demo"] and status["store"]["total_items"] > 0 and any(lg["league"] == "EPL" for lg in status["leagues"])
    assert status["matrix"] and {"league", "season", "pages", "events", "played"} <= set(status["matrix"][0]) and status["auto"]["prefs"]["enabled"] is True
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
    assert [s["name"] for s in result["steps"]] == ["Load the league", "Read the league page", "Read a match", "Read a player", "Read a squad list", "Look up birthdates"]
    assert all(s["ok"] and isinstance(s["ms"], int) for s in result["steps"])
    assert "20 teams" in result["steps"][1]["detail"]


def test_your_own_birthdate_corrections_win(tmp_path):
    from app.workbench import Workbench

    (tmp_path / "birthdates.json").write_text(json.dumps({"Sávio": "2004-04-10", "Pablo Ibáñez|Alaves": "1998-08-03", "Broken": "not a date"}))
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2026, 10, 1))
    try:
        assert wb.ages.dob_info("Sávio", ["Manchester City"]) == ("2004-04-10", "manual")
        assert wb.ages.dob_info("Pablo Ibáñez", ["Alaves"]) == ("1998-08-03", "manual")  # name and club together
        assert wb.ages.dob_info("Pablo Ibáñez", ["Elche"])[1] != "manual"  # a different club is a different man
        assert wb.ages.dob_info("Broken", [])[1] != "manual"
    finally:
        asyncio.run(wb.close())
