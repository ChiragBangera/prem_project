"""ESPN squad lists: parsing, storing, resuming and linking, against a local fake of the feed."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.config import Settings
from app.data.rosters import COOLDOWN, RETRY_AFTER, SPARSE_RETRY, RosterClient, link_roster, parse_athletes
from app.data.store import Store

TODAY = date(2026, 10, 1)   # so season 2025 is finished and 2026 is live


def athlete(aid, name, dob, pos="M", display=None):
    return {"id": aid, "fullName": name, "displayName": display or name, "dateOfBirth": dob, "position": {"abbreviation": pos}}


ROSTERS = {
    "1": [athlete("11", "Bukayo Saka", "2001-09-05T07:00Z", "F"), athlete("12", "Gabriel dos Santos Magalhães", "1997-12-19T08:00Z", "D", display="Gabriel Magalhães"),
          athlete("13", "No Birthdate", None), athlete("14", "Impossible Child", "2020-01-01T00:00Z")],
    "2": [{"position": "Goalkeepers", "items": [athlete("21", "Jordan Pickford", "1994-03-07T08:00Z", "G")]}, athlete("22", "Dominic Calvert-Lewin", "1997-03-16T08:00Z", "F")],
}


class Feed:
    """A fake ESPN: counts requests and can be told to fail."""

    def __init__(self):
        self.calls: list[str] = []
        self.fail_standings = False
        self.fail_rosters: set[str] = set()

    def app(self):
        async def standings(request):
            self.calls.append("standings")
            if self.fail_standings:
                return web.Response(status=500)
            entries = [{"team": {"id": "1", "displayName": "Arsenal"}}, {"team": {"id": "2", "displayName": "Everton"}}]
            return web.json_response({"children": [{"standings": {"entries": entries}}]})

        async def roster(request):
            tid = request.match_info["tid"]
            self.calls.append(f"roster:{tid}")
            if tid in self.fail_rosters:
                return web.Response(status=500)
            return web.json_response({"athletes": ROSTERS[tid]})

        app = web.Application()
        app.router.add_get("/v2/sports/soccer/eng.1/standings", standings)
        app.router.add_get("/site/v2/sports/soccer/eng.1/teams/{tid}/roster", roster)
        return app


@pytest.fixture()
async def env(tmp_path, monkeypatch):
    monkeypatch.setattr("app.data.rosters.MIN_SQUAD", 1)   # the fake squads have two players each; the sparse rule has its own test
    feed = Feed()
    server = TestServer(feed.app())
    await server.start_server()
    store = Store(tmp_path / "s.sqlite")
    clock = NS(now=1_000_000.0)
    client = RosterClient(store, Settings(data_dir=tmp_path), base_url=str(server.make_url("")), today=lambda: TODAY, clock=lambda: clock.now,
                          concurrency=3, interval=0, retries=0, backoff=0.001)
    yield NS(feed=feed, client=client, store=store, clock=clock)
    await client.close()
    await server.close()
    store.close()


def test_parse_keeps_players_with_a_plausible_birthdate_and_flattens_groups():
    got = parse_athletes({"athletes": ROSTERS["1"] + ROSTERS["2"]}, 2026)
    assert [p["name"] for p in got] == ["Bukayo Saka", "Gabriel dos Santos Magalhães", "Jordan Pickford", "Dominic Calvert-Lewin"]
    assert got[0]["dob"] == "2001-09-05" and got[1]["alt"] == ["Gabriel Magalhães"] and got[2]["pos"] == "G"
    assert parse_athletes({}, 2026) == [] and parse_athletes({"athletes": [{"id": "1", "fullName": "X", "dateOfBirth": "garbage"}]}, 2026) == []


async def test_a_finished_season_is_fetched_once_and_stored_for_good(env):
    body = await env.client.ensure("EPL", 2025)
    assert [t["name"] for t in body["teams"]] == ["Arsenal", "Everton"] and body["pending"] == []
    assert sum(len(t["players"]) for t in body["teams"]) == 4
    assert env.feed.calls.count("standings") == 1 and sorted(c for c in env.feed.calls if c.startswith("roster")) == ["roster:1", "roster:2"]
    assert env.store.meta("roster", "EPL:2025")[2] is True                       # complete: never refreshed
    env.clock.now += 400 * 86400
    assert await env.client.ensure("EPL", 2025) == body and len(env.feed.calls) == 3   # a year later: still no new requests
    assert env.client.cached("EPL", 2025)["teams"][0]["players"][0]["dob"] == "2001-09-05"
    assert env.client.version("EPL", 2025) == (4, body["fetched"])


async def test_the_live_season_refreshes_daily_and_keeps_old_squads_if_a_refresh_fails(env):
    first = await env.client.ensure("EPL", 2026)
    assert env.store.meta("roster", "EPL:2026")[2] is False                       # live: not final
    env.clock.now += 3600
    assert await env.client.ensure("EPL", 2026) == first and len(env.feed.calls) == 3   # an hour later: still fresh
    env.clock.now += 25 * 3600
    env.feed.fail_rosters = {"2"}
    second = await env.client.ensure("EPL", 2026)
    assert second["fetched"] > first["fetched"] and sum(len(t["players"]) for t in second["teams"]) == 4   # Everton's squad is kept, not lost
    assert second["pending"] == []


async def test_clubs_that_fail_are_retried_alone_and_not_straight_away(env):
    env.feed.fail_rosters = {"2"}
    body = await env.client.ensure("EPL", 2025)
    assert [t["name"] for t in body["teams"]] == ["Arsenal"] and [t["name"] for t in body["pending"]] == ["Everton"]
    assert env.store.meta("roster", "EPL:2025")[2] is False and not env.client.fresh(body, 2025)
    calls = len(env.feed.calls)
    assert await env.client.ensure("EPL", 2025) == body and len(env.feed.calls) == calls        # too soon: nothing is requested
    env.feed.fail_rosters = set()
    env.clock.now += RETRY_AFTER + 1
    done = await env.client.ensure("EPL", 2025)
    assert [t["name"] for t in done["teams"]] == ["Arsenal", "Everton"] and done["pending"] == []
    assert env.feed.calls[calls:] == ["roster:2"]                                              # only the missing club was asked for


async def test_a_refusal_means_a_cooldown_not_a_hammering(env):
    env.feed.fail_standings = True
    assert await env.client.ensure("EPL", 2025) is None
    assert env.client.cooling_down() and env.feed.calls == ["standings"]
    assert await env.client.ensure("EPL", 2024) is None and env.feed.calls == ["standings"]    # any league-season waits
    env.feed.fail_standings = False
    env.clock.now += COOLDOWN + 1
    assert (await env.client.ensure("EPL", 2025))["teams"]


async def test_offline_demo_and_unknown_leagues_never_touch_the_network(env, tmp_path):
    for settings in (Settings(data_dir=tmp_path, offline=True), Settings(data_dir=tmp_path, demo=True)):
        client = RosterClient(env.store, settings, base_url="http://127.0.0.1:1", today=lambda: TODAY)
        assert await client.ensure("EPL", 2025) is None
    assert await env.client.ensure("Eredivisie", 2025) is None and env.feed.calls == []


async def test_roster_players_link_to_understat_players_by_name_and_club(env):
    body = await env.client.ensure("EPL", 2025)
    players = [NS(id=7, name="Bukayo Saka", teams=["Arsenal"]), NS(id=8, name="Gabriel Magalhaes", teams=["Arsenal"]), NS(id=9, name="Jordan Pickford", teams=["Everton"]),
               NS(id=10, name="Someone Else", teams=["Everton"])]
    linked, left = link_roster(body, players)
    assert {uid: p["dob"] for uid, p in linked.items()} == {7: "2001-09-05", 8: "1997-12-19", 9: "1994-03-07"}
    assert [p["name"] for p in left] == ["Dominic Calvert-Lewin"] and linked[9]["pos"] == "G"


async def test_needs_fetch_is_the_one_rule_for_going_to_the_network(env, tmp_path):
    assert env.client.needs_fetch("EPL", 2025) and env.client.needs_fetch("EPL", 2026)
    assert not env.client.needs_fetch("Eredivisie", 2025)                                         # a league the feed is not asked about
    await env.client.ensure("EPL", 2025)
    assert not env.client.needs_fetch("EPL", 2025)                                                # final and stored: never again
    await env.client.ensure("EPL", 2026)
    assert not env.client.needs_fetch("EPL", 2026)
    env.clock.now += 25 * 3600
    assert env.client.needs_fetch("EPL", 2026)                                                    # the live season goes stale after a day
    env.feed.fail_rosters = {"2"}
    await env.client.ensure("EPL", 2024)
    assert not env.client.needs_fetch("EPL", 2024)                                                # a club that just failed waits for its retry
    env.clock.now += RETRY_AFTER + 1
    assert env.client.needs_fetch("EPL", 2024)
    env.client.cool_down()
    assert not env.client.needs_fetch("EPL", 2024) and env.client.cooling_down()
    for settings in (Settings(data_dir=tmp_path, offline=True), Settings(data_dir=tmp_path, demo=True)):
        assert not RosterClient(env.store, settings, today=lambda: TODAY).needs_fetch("EPL", 2023)


async def test_what_went_wrong_is_remembered_for_the_data_page(env):
    env.feed.fail_rosters = {"2"}
    await env.client.ensure("EPL", 2025)
    assert "Everton" in env.client.last_error
    env.clock.now += RETRY_AFTER + 1
    env.feed.fail_rosters = set()
    await env.client.ensure("EPL", 2025)
    assert env.client.last_error is None


async def test_the_enricher_fetches_squad_lists_in_the_background_and_says_when_new_birthdates_landed(env):
    from app.enrich import Enricher, FavoriteIndex

    enricher = Enricher(NS(), env.store, NS(), FavoriteIndex(env.store), roster_client=env.client)
    targets = [("EPL", 2025), ("EPL", 2026)]
    assert enricher.squads_pending(targets) is True
    assert enricher.schedule_rosters(targets) == 2 and enricher.rosters.running and enricher.squads_pending(targets) is True
    epoch = enricher.epoch
    await enricher._tasks["rosters"]
    assert not enricher.rosters.running and (enricher.rosters.done, enricher.rosters.total, enricher.rosters.failed) == (2, 2, 0)
    assert enricher.epoch == epoch + 2                                                             # each league-season changed what ages are known
    assert enricher.squads_pending(targets) is False and enricher.schedule_rosters(targets) == 0   # nothing left: no task, no rescheduling loop
    assert enricher.status()["rosters"]["kind"] == "rosters" and enricher.busy is False


async def test_a_failing_feed_does_not_make_the_enricher_retry_on_every_page_load(env):
    from app.enrich import Enricher, FavoriteIndex

    enricher = Enricher(NS(), env.store, NS(), FavoriteIndex(env.store), roster_client=env.client)
    env.feed.fail_standings = True
    assert enricher.schedule_rosters([("EPL", 2025)]) == 1
    await enricher._tasks["rosters"]
    epoch, calls = enricher.epoch, len(env.feed.calls)
    assert enricher.rosters.last_error and enricher.epoch == epoch                                  # nothing new landed, so nothing is rebuilt
    assert enricher.schedule_rosters([("EPL", 2025)]) == 0 and enricher.squads_pending([("EPL", 2025)]) is False   # cooling down: Wikidata may go ahead
    assert len(env.feed.calls) == calls


async def test_an_enricher_without_a_roster_client_does_nothing(env):
    from app.enrich import Enricher, FavoriteIndex

    enricher = Enricher(NS(), env.store, NS(), FavoriteIndex(env.store))
    assert enricher.schedule_rosters([("EPL", 2025)]) == 0 and enricher.squads_pending([("EPL", 2025)]) is False


async def test_the_probe_makes_one_real_round_trip_and_stores_nothing(env):
    assert await env.client.probe("EPL", 2026) == "ESPN answered: Arsenal has 2 players with exact birthdates"
    assert env.feed.calls == ["standings", "roster:1"] and env.store.keys("roster") == []


async def test_the_probe_says_what_is_wrong_when_the_feed_changes_shape_or_goes_quiet(env):
    from app.errors import UpstreamError

    env.feed.fail_standings = True
    with pytest.raises(UpstreamError):
        await env.client.probe("EPL", 2026)
    env.feed.fail_standings = False
    env.feed.fail_rosters = {"1"}
    with pytest.raises(UpstreamError):
        await env.client.probe("EPL", 2026)


async def test_a_season_the_feed_has_little_for_is_kept_but_flagged_and_looked_at_again_after_a_week(env, monkeypatch):
    monkeypatch.setattr("app.data.rosters.MIN_SQUAD", 8)                      # real squads have 20 or more listed; here every club has two
    body = await env.client.ensure("EPL", 2025)
    assert body["sparse"] is True and sum(len(t["players"]) for t in body["teams"]) == 4   # what it does list is still real, so it is kept
    assert env.store.meta("roster", "EPL:2025")[2] is False                  # a finished season, but not final: the feed may fill in
    calls = len(env.feed.calls)
    assert not env.client.needs_fetch("EPL", 2025) and await env.client.ensure("EPL", 2025) == body and len(env.feed.calls) == calls
    env.clock.now += SPARSE_RETRY + 1
    assert env.client.needs_fetch("EPL", 2025)
    monkeypatch.setattr("app.data.rosters.MIN_SQUAD", 1)                      # the feed has filled in (or the rule is met)
    again = await env.client.ensure("EPL", 2025)
    assert again["sparse"] is False and env.store.meta("roster", "EPL:2025")[2] is True and not env.client.needs_fetch("EPL", 2025)


async def test_a_sync_job_fetches_the_squad_lists_with_the_league_data_and_logs_it(env, repo):
    import asyncio

    from app.jobs import JobManager

    jobs = JobManager(repo, rosters=env.client)
    job = jobs.start_sync(["EPL"], [2025])
    await jobs._tasks[job.id]
    assert job.state == "finished" and job.failed == 0
    assert any("squad lists for 2 clubs, 4 players" in line for line in job.log)
    assert env.client.cached("EPL", 2025) is not None
    again = jobs.start_sync(["EPL"], [2025])                                    # a second sync does not ask the feed again
    await jobs._tasks[again.id]
    assert env.feed.calls.count("standings") == 1 and not any("squad lists" in line for line in again.log)

    env.feed.fail_standings = True
    failing = jobs.start_sync(["EPL"], [2024])                                  # an unreachable feed must not fail the sync of league data
    await jobs._tasks[failing.id]
    assert failing.state == "finished" and failing.failed == 0 and any("squad lists unavailable" in line for line in failing.log)
