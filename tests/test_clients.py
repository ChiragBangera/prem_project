"""The Understat client and the Wikidata resolver, against local aiohttp servers."""

from __future__ import annotations

import asyncio
import json

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.config import Settings
from app.data.store import Store
from app.data.understat import UnderstatClient, team_slug
from app.data.wikidata import CACHE_VERSION, BirthdateResolver, age_on, pick_birthdate, resolve_birthdate
from app.errors import UpstreamError, UpstreamTimeout


async def serve(app: web.Application) -> TestServer:
    server = TestServer(app)
    await server.start_server()
    return server


def client_for(server: TestServer, **kwargs) -> UnderstatClient:
    defaults = dict(min_interval=0, retries=2, backoff_base=0.001, timeout=2)
    return UnderstatClient(base_url=str(server.make_url("")), **{**defaults, **kwargs})


# ------------------------------------------------------------------ Understat


async def test_league_request_shape_and_json():
    seen = {}

    async def handler(request):
        seen["path"], seen["xrw"], seen["referer"], seen["ua"] = (
            request.path,
            request.headers.get("X-Requested-With"),
            request.headers.get("Referer"),
            request.headers.get("User-Agent"),
        )
        return web.json_response({"teams": {}, "players": [], "dates": []})

    app = web.Application()
    app.router.add_get("/getLeagueData/{league}/{season}", handler)
    server = await serve(app)
    client = client_for(server)
    try:
        assert await client.league("La_liga", 2024) == {"teams": {}, "players": [], "dates": []}
    finally:
        await client.close()
        await server.close()
    assert seen["path"] == "/getLeagueData/La_liga/2024"
    assert seen["xrw"] == "XMLHttpRequest" and seen["referer"].endswith("/league/La_liga/2024")
    assert "prem-lab" in seen["ua"]


async def test_retries_transient_errors_then_succeeds():
    hits = {"n": 0}

    async def handler(request):
        hits["n"] += 1
        if hits["n"] < 3:
            return web.Response(status=503)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/getPlayerData/{pid}", handler)
    server = await serve(app)
    client = client_for(server, retries=3)
    try:
        assert await client.player(8260) == {"ok": True}
    finally:
        await client.close()
        await server.close()
    assert hits["n"] == 3


async def test_gives_up_after_retries_with_status():
    async def handler(request):
        return web.Response(status=429, headers={"Retry-After": "0"})

    app = web.Application()
    app.router.add_get("/getMatchData/{mid}", handler)
    server = await serve(app)
    client = client_for(server, retries=1)
    try:
        with pytest.raises(UpstreamError) as caught:
            await client.match(1)
    finally:
        await client.close()
        await server.close()
    assert caught.value.upstream_status == 429


async def test_404_is_not_retried_and_carries_status():
    hits = {"n": 0}

    async def handler(request):
        hits["n"] += 1
        return web.Response(status=404)

    app = web.Application()
    app.router.add_get("/getTeamData/{team}/{season}", handler)
    server = await serve(app)
    client = client_for(server)
    try:
        with pytest.raises(UpstreamError) as caught:
            await client.team("Nowhere FC", 2025)
    finally:
        await client.close()
        await server.close()
    assert hits["n"] == 1 and caught.value.upstream_status == 404


async def test_html_body_gives_a_helpful_error():
    async def handler(request):
        return web.Response(text="<html>Just a moment...</html>", content_type="text/html")

    app = web.Application()
    app.router.add_get("/getLeagueData/{league}/{season}", handler)
    server = await serve(app)
    client = client_for(server)
    try:
        with pytest.raises(UpstreamError) as caught:
            await client.league("EPL", 2025)
    finally:
        await client.close()
        await server.close()
    assert "HTML" in str(caught.value) and caught.value.hint


async def test_timeout_maps_to_upstream_timeout():
    async def handler(request):
        await asyncio.sleep(1.0)
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/getLeagueData/{league}/{season}", handler)
    server = await serve(app)
    client = client_for(server, timeout=0.05, retries=0)
    try:
        with pytest.raises(UpstreamTimeout):
            await client.league("EPL", 2025)
    finally:
        await client.close()
        await server.close()


async def test_connection_refused_is_reported_not_raised_raw():
    client = UnderstatClient(base_url="http://127.0.0.1:9", min_interval=0, retries=0, timeout=1)
    try:
        with pytest.raises(UpstreamError) as caught:
            await client.league("EPL", 2025)
    finally:
        await client.close()
    assert "connect" in str(caught.value).lower()


async def test_concurrency_limit_and_pacing_are_respected():
    state = {"now": 0, "peak": 0, "starts": []}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        state["starts"].append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.03)
        state["now"] -= 1
        return web.json_response({})

    app = web.Application()
    app.router.add_get("/getPlayerData/{pid}", handler)
    server = await serve(app)
    client = client_for(server, max_concurrency=2, min_interval=0.02)
    try:
        await asyncio.gather(*(client.player(i) for i in range(1, 9)))
    finally:
        await client.close()
        await server.close()
    assert state["peak"] <= 2
    gaps = [b - a for a, b in zip(state["starts"], state["starts"][1:])]
    assert min(gaps) >= 0.015  # request starts are spaced out


async def test_post_player_stats_and_search():
    got = {}

    async def stats(request):
        got["form"] = dict(await request.post())
        got["origin"] = request.headers.get("Origin")
        return web.json_response({"success": True, "players": [{"id": "1", "player_name": "X"}]})

    async def search(request):
        return web.json_response({"response": {"success": True, "players": [{"id": "7", "player": "Erling Haaland", "team": "Manchester City"}]}})

    app = web.Application()
    app.router.add_post("/main/getPlayersStats/", stats)
    app.router.add_get("/main/getPlayersName/{q}", search)
    server = await serve(app)
    client = client_for(server)
    try:
        players = await client.league_players("EPL", 2025, "2025-09-01", None)
        found = await client.search_players("haaland")
    finally:
        await client.close()
        await server.close()
    assert players[0]["player_name"] == "X" and found[0]["id"] == "7"
    assert got["form"]["league"] == "EPL" and got["form"]["date_start"] == "2025-09-01 00:00:00"
    assert got["form"]["date_end"] == "" and got["origin"]


def test_team_slug_quotes_safely():
    assert team_slug("Manchester United") == "Manchester_United"
    assert team_slug("Borussia M.Gladbach") == "Borussia_M.Gladbach"
    assert team_slug("Atlético Madrid") == "Atl%C3%A9tico_Madrid"


# ------------------------------------------------------------------ Wikidata


def sparql(*rows):
    return {"results": {"bindings": [
        {"name": {"value": name}, "dob": {"value": dob + "T00:00:00Z"}, **({"teamLabel": {"value": team}} if team else {})}
        for name, dob, team in rows
    ]}}


def test_age_on():
    from datetime import date

    assert age_on("2000-07-21", date(2026, 7, 20)) == 25
    assert age_on("2000-07-21", date(2026, 7, 21)) == 26
    assert age_on(None) is None and age_on("garbage") is None


def test_pick_birthdate_disambiguation():
    one = [{"dob": "1999-07-21", "teams": ["Manchester City F.C."]}]
    assert pick_birthdate(one, None) == "1999-07-21"
    namesakes = [
        {"dob": "1990-01-01", "teams": ["Chelsea F.C."]},
        {"dob": "2001-05-05", "teams": ["Manchester United F.C."]},
    ]
    assert pick_birthdate(namesakes, "Manchester United") == "2001-05-05"
    assert pick_birthdate(namesakes, "Everton") is None  # ambiguous: refuse to guess
    assert pick_birthdate(namesakes, None) is None
    assert pick_birthdate([{"dob": "1901-01-01", "teams": []}], None) is None  # implausible
    assert pick_birthdate([{"dob": "1999-07-21", "teams": []}, {"dob": "1999-07-21", "teams": ["X"]}], None) == "1999-07-21"


NOW = __import__("datetime").date(2026, 10, 1)


def cand(dob, *stints):
    """A Wikidata candidate; each stint is (club, start, end)."""
    return {"dob": dob, "teams": [t for t, _s, _e in stints], "stints": [{"team": t, "start": st, "end": en} for t, st, en in stints]}


def test_retired_namesakes_are_ruled_out_by_age():
    old = [cand("1974-01-09", ("Avaí Futebol Clube", "2010-01-01", "2010-01-01"))]
    assert resolve_birthdate(old, ["Manchester City"], name="Sávio", reference=NOW) == (None, None)  # 52 years old
    veteran = [cand("1982-08-20", ("CA Osasuna", None, None))]
    assert resolve_birthdate(veteran, ["Osasuna"], name="Rubén García", reference=NOW) == (None, None)  # 44
    # the same man is a perfectly plausible player when the question is about a season long ago
    assert resolve_birthdate(veteran, ["Osasuna"], name="Rubén García", reference=__import__("datetime").date(2012, 6, 30))[0] == "1982-08-20"


def test_a_club_he_left_long_ago_does_not_confirm_a_namesake():
    # Wikidata lists every club ever: the 1985 man played for Celta in the 2000s, the 2003 one has no clubs listed
    namesakes = [cand("1985-06-21", ("RC Celta de Vigo", "2004-01-01", "2006-01-01")), cand("2003-07-02")]
    assert resolve_birthdate(namesakes, ["Celta Vigo"], name="Hugo Álvarez", reference=NOW) == ("2003-07-02", "name")
    # both young enough to play: the old Celta stint must not decide it, and nothing else can
    both = [cand("1996-06-21", ("RC Celta de Vigo", "2014-01-01", "2016-01-01")), cand("2003-07-02")]
    assert resolve_birthdate(both, ["Celta Vigo"], name="Hugo Álvarez", reference=NOW) == (None, None)
    # a recent stint (or one with no end) does confirm
    current = [cand("1996-06-21", ("RC Celta de Vigo", "2014-01-01", "2016-01-01")), cand("2003-07-02", ("RC Celta de Vigo", "2022-01-01", None))]
    assert resolve_birthdate(current, ["Celta Vigo"], name="Hugo Álvarez", reference=NOW) == ("2003-07-02", "club")


def test_clubs_match_on_meaningful_words_not_exact_strings():
    one = [cand("1987-08-01", ("RC Celta de Vigo", "2008-01-01", None))]
    assert resolve_birthdate(one, ["Celta Vigo"], name="Iago Aspas", reference=NOW) == ("1987-08-01", "club")
    assert resolve_birthdate(one, ["Real Madrid", "Celta Vigo"], name="Iago Aspas", reference=NOW)[1] == "club"  # any of his clubs
    city = [cand("1999-07-21", ("Manchester City F.C.", "2022-01-01", None)), cand("1990-01-01", ("Manchester United F.C.", "2015-01-01", None))]
    assert resolve_birthdate(city, ["Manchester City"], name="Some Player", reference=NOW) == ("1999-07-21", "club")


def test_without_club_evidence_only_full_names_and_not_veterans_are_trusted():
    lone = [cand("2000-05-24", ("FC Basel", None, None))]
    assert resolve_birthdate(lone, ["Leeds"], name="Noah Okafor", reference=NOW) == ("2000-05-24", "name")  # Wikidata lags transfers
    assert resolve_birthdate(lone, ["Leeds"], name="Okafor", reference=NOW) == (None, None)  # one word: far too likely to be someone else
    assert resolve_birthdate([cand("1987-03-03")], ["Leeds"], name="Some Veteran", reference=NOW) == (None, None)  # 39: a retired namesake is likelier
    assert resolve_birthdate(lone, None, reference=NOW)[0] == "2000-05-24"  # name not given: no single-word rule


def test_parse_keeps_the_dates_of_each_stint():
    payload = {"results": {"bindings": [
        {"name": {"value": "A B"}, "dob": {"value": "2000-01-01T00:00:00Z"}, "teamLabel": {"value": "X FC"}, "start": {"value": "2020-01-01T00:00:00Z"}},
        {"name": {"value": "A B"}, "dob": {"value": "2000-01-01T00:00:00Z"}, "teamLabel": {"value": "Y FC"}, "start": {"value": "2018-01-01T00:00:00Z"}, "end": {"value": "2020-01-01T00:00:00Z"}},
    ]}}
    (c,) = BirthdateResolver._parse(payload)["a b"]
    assert c["teams"] == ["X FC", "Y FC"]
    assert c["stints"] == [{"team": "X FC", "start": "2020-01-01", "end": None}, {"team": "Y FC", "start": "2018-01-01", "end": "2020-01-01"}]


async def test_answers_cached_before_dates_were_stored_are_asked_again(tmp_path):
    calls = []

    async def endpoint(request):
        calls.append(1)
        return web.json_response(sparql(("Erling Haaland", "2000-07-21", "Manchester City F.C.")), content_type="application/sparql-results+json")

    app = web.Application()
    app.router.add_post("/sparql", endpoint)
    server = await serve(app)
    store = Store(tmp_path / "s.sqlite")
    resolver = BirthdateResolver(store, Settings(data_dir=tmp_path), endpoints=(str(server.make_url("/sparql")),))
    try:
        store.put("dob", "erling haaland", {"candidates": [{"dob": "2000-07-21", "teams": ["Manchester City F.C."]}], "name": "Erling Haaland"}, source="wikidata")
        assert resolver.cached("Erling Haaland", "Manchester City", NOW) == "2000-07-21"  # an old answer is still usable...
        assert not resolver.known("Erling Haaland")  # ...but is asked for again
        await resolver.resolve([("Erling Haaland", "Manchester City")])
        assert len(calls) == 1 and resolver.known("Erling Haaland") and store.get("dob", "erling haaland").body["v"] == CACHE_VERSION
    finally:
        await server.close()
        store.close()


async def test_resolver_batches_caches_and_disambiguates(tmp_path):
    calls = []

    async def endpoint(request):
        form = await request.post()
        calls.append(form["query"])
        return web.json_response(
            sparql(
                ("Erling Haaland", "2000-07-21", "Manchester City F.C."),
                ("Erling Haaland", "2000-07-21", "Borussia Dortmund"),
                ("Pedro Neto", "1990-03-03", "Some Old Club"),
                ("Pedro Neto", "2000-03-09", "Chelsea F.C."),
            ),
            content_type="application/sparql-results+json",
        )

    app = web.Application()
    app.router.add_post("/sparql", endpoint)
    server = await serve(app)
    store = Store(tmp_path / "s.sqlite")
    resolver = BirthdateResolver(store, Settings(data_dir=tmp_path), endpoints=(str(server.make_url("/sparql")),))
    try:
        result = await resolver.resolve([("Erling Haaland", "Manchester City"), ("Pedro Neto", "Chelsea"), ("Nobody Known", None)])
        assert result["erling haaland"] == "2000-07-21"
        assert result["pedro neto"] == "2000-03-09"  # namesake resolved by club
        assert result["nobody known"] is None
        assert '"Erling Haaland"@en' in calls[0] and "rdfs:label" in calls[0]
        n_after_first = len(calls)

        again = await resolver.resolve([("Erling Haaland", "Manchester City"), ("Nobody Known", None)])
        assert again["erling haaland"] == "2000-07-21"
        assert len(calls) == n_after_first  # served entirely from the store (hit and miss cached)
        assert resolver.cached("Pedro Neto", "Chelsea") == "2000-03-09" and resolver.known("Nobody Known")
    finally:
        await server.close()
        store.close()


async def test_resolver_falls_back_to_second_endpoint_and_alt_labels(tmp_path):
    seen = []

    async def broken(request):
        return web.Response(status=500)

    async def good(request):
        form = await request.post()
        seen.append("altLabel" if "skos:altLabel" in form["query"] else "label")
        if "skos:altLabel" in form["query"]:
            return web.json_response(sparql(("Vinicius Junior", "2000-07-12", "Real Madrid CF")))
        return web.json_response(sparql())

    app = web.Application()
    app.router.add_post("/broken", broken)
    app.router.add_post("/good", good)
    server = await serve(app)
    store = Store(tmp_path / "s.sqlite")
    resolver = BirthdateResolver(
        store, Settings(data_dir=tmp_path), endpoints=(str(server.make_url("/broken")), str(server.make_url("/good")))
    )
    try:
        result = await resolver.resolve([("Vinicius Junior", "Real Madrid")])
        assert result["vinicius junior"] == "2000-07-12"
        assert seen == ["label", "altLabel"]
    finally:
        await server.close()
        store.close()


async def test_resolver_cools_down_when_unreachable_and_never_raises(tmp_path):
    async def broken(request):
        return web.Response(status=500)

    app = web.Application()
    app.router.add_post("/x", broken)
    server = await serve(app)
    store = Store(tmp_path / "s.sqlite")
    resolver = BirthdateResolver(store, Settings(data_dir=tmp_path), endpoints=(str(server.make_url("/x")),))
    try:
        assert await resolver.resolve([("Someone", None)]) == {"someone": None}
        assert store.get("dob", "someone") is None  # failure is not cached as a miss
        assert resolver._cooldown_until > 0
    finally:
        await server.close()
        store.close()


async def test_resolver_skips_network_in_demo_and_offline(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    for settings in (Settings(data_dir=tmp_path, demo=True), Settings(data_dir=tmp_path, offline=True)):
        resolver = BirthdateResolver(store, settings, endpoints=("http://127.0.0.1:9/never",))
        assert await resolver.resolve([("Anyone", None)]) == {"anyone": None}
    store.close()
