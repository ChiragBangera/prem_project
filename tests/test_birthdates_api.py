"""Exact birthdates from squad lists, end to end: store -> linking -> Scout rows -> Data page, and who Wikidata is asked about."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from itertools import count

from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.data.wikidata import CACHE_VERSION
from app.leagues import fold
from app.workbench import Workbench

from .conftest import FakeProvider


_fetched = count(1_780_000_000)   # every stored list is a new fetch, as in life, so what was built from the old one notices


def squad(season: int, clubs: dict[str, list[tuple[str, str]]], *, pending: list[str] | None = None, sparse: bool = False) -> dict:
    """A stored squad list body: ``clubs`` maps a club to its (name, date of birth) players."""
    teams = [{"id": str(i), "name": club, "players": [{"id": f"{i}{n}", "name": name, "alt": [], "dob": dob, "pos": "M"} for n, (name, dob) in enumerate(players)]}
             for i, (club, players) in enumerate(clubs.items(), start=1)]
    return {"v": 2, "league": "EPL", "season": season, "fetched": float(next(_fetched)), "teams": teams, "pending": [{"id": "9", "name": c} for c in pending or []], "sparse": sparse}


def put(wb, body: dict) -> None:
    wb.store.put("roster", f"{body['league']}:{body['season']}", body, source="espn", complete=True)


def wikidata(wb, name: str, dob: str, club: str) -> None:
    """What an earlier Wikidata lookup would have stored: one person of that name, at that club since 2015."""
    entry = {"candidates": [{"dob": dob, "teams": [club], "stints": [{"team": club, "start": "2015-07-01", "end": None}]}], "name": name, "v": CACHE_VERSION}
    wb.store.put("dob", fold(name), entry, source="wikidata")


def demo_app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2021, 1, 15))


def rows_of(c, **params) -> dict[int, dict]:
    return {r["id"]: r for r in c.get("/api/players", params={"leagues": "EPL", **params}).json()["rows"]}


def test_a_squad_list_gives_the_exact_birthdate_and_is_marked_as_such(tmp_path):
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        before = rows_of(c, seasons="2019")
        a, b, other_club = [r for r in before.values() if r["minutes"] >= 900 and len(r["teams"]) == 1][:3]
        stranger_club = next(t for t in {t for r in before.values() for t in r["teams"]} if t not in a["teams"] + b["teams"])
        put(wb, squad(2019, {a["teams"][0]: [(a["name"], "2001-02-03")],
                             stranger_club: [(b["name"], "1990-01-01")]}))      # b's name, but at a club he did not play for: not him

        after = rows_of(c, seasons="2019")
        assert (after[a["id"]]["dob"], after[a["id"]]["dob_basis"]) == ("2001-02-03", "roster")
        assert after[a["id"]]["age"] == 19 and after[a["id"]]["dob"] != before[a["id"]]["dob"]   # 3 Feb 2001, on the season's reference date (30 Jun 2020)
        assert after[b["id"]]["dob_basis"] != "roster" and after[b["id"]]["dob"] == before[b["id"]]["dob"]
        assert after[other_club["id"]]["dob"] == before[other_club["id"]]["dob"]       # nobody else was touched


def test_two_seasons_that_disagree_about_one_player_leave_him_out(tmp_path):
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        y19, y20 = rows_of(c, seasons="2019"), rows_of(c, seasons="2020")
        both = next(r for r in y19.values() if r["id"] in y20 and r["minutes"] >= 900 and len(r["teams"]) == 1 and y20[r["id"]]["teams"] == r["teams"])
        put(wb, squad(2019, {both["teams"][0]: [(both["name"], "2000-05-05")]}))
        put(wb, squad(2020, {both["teams"][0]: [(both["name"], "2000-05-05")]}))
        agreed = rows_of(c, seasons="2019,2020")
        assert (agreed[both["id"]]["dob"], agreed[both["id"]]["dob_basis"]) == ("2000-05-05", "roster")

        put(wb, squad(2020, {both["teams"][0]: [(both["name"], "1994-11-11")]}))       # a different man under the same name and club
        split = rows_of(c, seasons="2019,2020")
        assert split[both["id"]]["dob_basis"] != "roster"                               # a blank (or the old source) beats a coin toss


def test_your_own_correction_still_beats_the_squad_list_and_the_squad_list_beats_wikidata(tmp_path):
    (tmp_path / "birthdates.json").write_text(json.dumps({"Corrected Man|Alpha FC": "1990-01-01"}))
    wb = Workbench(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2026, 10, 1))
    try:
        roster = {1: "2000-02-02", 2: "2001-03-03"}
        assert wb.dob_info("Corrected Man", ["Alpha FC"], None, 1, roster) == ("1990-01-01", "manual")
        assert wb.dob_info("Someone", ["Alpha FC"], None, 1, roster) == ("2000-02-02", "roster")
        assert wb.dob_info("Someone", ["Alpha FC"], None, 99, roster)[1] != "roster"     # not on a squad list: falls through to the old sources
        assert wb.dob_info("Someone", ["Alpha FC"], None, 1, None)[1] != "roster" and wb.dob_info("Someone", ["Alpha FC"])[1] != "roster"
    finally:
        asyncio.run(wb.close())


def test_the_data_page_reports_how_well_each_squad_list_matched_and_where_wikidata_disagrees(tmp_path):
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        assert c.get("/api/data/status").json()["birthdates"] == []
        base = rows_of(c, seasons="2019")
        regulars = sorted((r for r in base.values() if r["minutes"] >= 450 and len(r["teams"]) == 1), key=lambda r: -r["minutes"])
        a, b = regulars[0], regulars[1]
        put(wb, squad(2019, {a["teams"][0]: [(a["name"], "1999-09-09")], b["teams"][0]: [("Nobody Atall", "1988-08-08")]}, pending=["Somewhere FC"]))

        (entry,) = c.get("/api/data/status").json()["birthdates"]
        assert (entry["league"], entry["season"], entry["clubs"], entry["players"]) == ("EPL", 2019, 2, 2)
        assert entry["pending"] == ["Somewhere FC"] and entry["final"] is True
        assert entry["linked"] == 1 and entry["players_total"] >= len(base)       # every player of the league, not only those with 90 minutes
        assert entry["regulars"] >= 2 and entry["regulars_linked"] == 1
        assert entry["missing"] and entry["missing"][0]["minutes"] >= entry["missing"][-1]["minutes"]    # the regulars it missed, busiest first
        assert entry["disagree"] == 0


def test_wikidata_is_only_asked_about_players_the_squad_lists_leave_out_and_only_after_they_are_in(tmp_path):
    """Everyone with an unknown age is asked about (goalkeepers and fringe players too), most minutes first, but only once the squad lists have settled."""
    wb = Workbench(Settings(data_dir=tmp_path, min_interval=0), provider=FakeProvider(), today=date(2025, 12, 1))
    asked, state = [], {"pending": True, "scheduled": []}
    wb.enricher.schedule_rosters = lambda targets: state["scheduled"].append(list(targets)) or 0
    wb.enricher.squads_pending = lambda targets: state["pending"]
    wb.enricher.schedule_ages = lambda people: asked.append(list(people)) or 0
    wb.enricher.schedule_roles = lambda ids, limit=0: 0

    async def go():
        try:
            await wb.players_view(["EPL"], [2025])
            assert state["scheduled"] == [[("EPL", 2025)]] and asked == []              # squad lists first: Wikidata waits
            state["pending"] = False
            await wb.players_view(["EPL"], [2025])
            assert [name for name, _team in asked[0]] == ["Di Keeper", "Bo Playmaker", "Ann Striker", "Cy Traveller"]   # by minutes, the keeper included
        finally:
            await wb.close()

    asyncio.run(go())


def test_a_squad_list_and_a_club_confirmed_wikidata_entry_that_are_far_apart_leave_the_age_blank(tmp_path):
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        base = rows_of(c, seasons="2019")
        a, b, d = [r for r in base.values() if r["minutes"] >= 900 and len(r["teams"]) == 1 and r["name"].count(" ") >= 1][:3]
        wikidata(wb, a["name"], "2001-02-06", a["teams"][0])       # three days apart: a different record of the same birthday, harmless
        wikidata(wb, b["name"], "1996-02-03", b["teams"][0])       # five years apart, and sure of the club: one source is wrong, nobody knows which
        wikidata(wb, d["name"], "1996-02-03", "Some Other Club")   # not sure of the club: no reason to doubt the squad list
        clubs: dict[str, list[tuple[str, str]]] = {}
        for x in (a, b, d):
            clubs.setdefault(x["teams"][0], []).append((x["name"], "2001-02-03"))
        put(wb, squad(2019, clubs))

        rows = rows_of(c, seasons="2019")
        assert (rows[a["id"]]["dob"], rows[a["id"]]["dob_basis"]) == ("2001-02-03", "roster")
        assert (rows[b["id"]]["dob"], rows[b["id"]]["dob_basis"], rows[b["id"]]["age"]) == (None, None, None)
        assert (rows[d["id"]]["dob"], rows[d["id"]]["dob_basis"]) == ("2001-02-03", "roster")

        (entry,) = c.get("/api/data/status").json()["birthdates"]
        assert (entry["compared"], entry["disagree"], entry["blank"]) == (2, 2, 1)
        assert [(x["name"], x["blank"]) for x in entry["disagree_examples"]] == [(b["name"], True), (a["name"], False)]   # the biggest gap first


def test_a_player_found_on_any_stored_squad_list_has_that_birthdate_in_every_view(tmp_path):
    """Someone who left his club since the season on show is missing from that club's list, but he is on the list of the club he went to."""
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        y19, y20 = rows_of(c, seasons="2019"), rows_of(c, seasons="2020")
        mover = next(r for r in y19.values() if r["id"] in y20 and r["minutes"] >= 900 and len(r["teams"]) == 1 and len(y20[r["id"]]["teams"]) == 1)
        later_club = y20[mover["id"]]["teams"][0]
        put(wb, squad(2020, {later_club: [(mover["name"], "2000-08-08")]}))          # only the 2020 list is stored
        assert (rows_of(c, seasons="2020")[mover["id"]]["dob"], rows_of(c, seasons="2020")[mover["id"]]["dob_basis"]) == ("2000-08-08", "roster")
        old = rows_of(c, seasons="2019")[mover["id"]]                                  # ...and it also settles his age in the earlier season
        assert (old["dob"], old["dob_basis"]) == ("2000-08-08", "roster")


def test_a_sparse_season_is_flagged_on_the_data_page(tmp_path):
    with TestClient(demo_app(tmp_path)) as c:
        wb = c.app.state.wb
        a = next(r for r in rows_of(c, seasons="2019").values() if r["minutes"] >= 900 and len(r["teams"]) == 1)
        put(wb, squad(2019, {a["teams"][0]: [(a["name"], "1999-09-09")]}, sparse=True))
        (entry,) = c.get("/api/data/status").json()["birthdates"]
        assert entry["sparse"] is True and entry["median_squad"] == 1 and entry["linked"] == 1
