"""Event data in the local store: raw -> silver -> gold, rebuilding from the layer below, season roll-ups, and linking sources together."""

from __future__ import annotations

import json
import time
from datetime import date

import pytest

from app.data.models import Fixture, MatchPage, PlayerSeason, RosterEntry
from app.data.store import Store
from app.events import counters as C
from app.events import raw as R
from app.events import silver as SV
from app.events.link import link_by_lineups, link_fixtures, link_season
from app.events.store import DERIVED_MARK, STALE_AFTER, EventStore

from .events_kit import AWAY, end, ev, match, player


def understat(pid, name, *teams):
    return PlayerSeason(id=pid, name=name, teams=list(teams), position="D S", games=10, minutes=900, goals=0, npg=0, assists=0, shots=0,
                        key_passes=0, yellow=0, red=0, xg=0.0, npxg=0.0, xa=0.0, xgchain=0.0, xgbuildup=0.0)


def raw_doc(passes=40, *, home="Reds", away="Blues", score="1 : 0", day="2025-08-16", n_filler=60):
    """A match document big enough to count as a real match, with a known number of passes by player 1."""
    events = [ev("Pass", 1, minute=1 + i % 90) for i in range(passes)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 90) for i in range(n_filler)] + [end(100)]
    doc = match(events, home=home, away=away, score=score, home_players=[player(1)], away_players=[player(2, team_side="away")])
    doc["startTime"] = f"{day}T15:00:00"
    return doc


@pytest.fixture()
def events(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    yield EventStore(store)
    store.close()


# ------------------------------------------------------------------ bronze


def test_only_real_matches_are_stored_as_raw_and_the_same_one_twice_changes_nothing(events):
    assert not events.ingest("EPL", 2025, 1, {"events": [], "home": {}, "away": {}})          # not a match: nothing is stored, nothing half-stored
    assert not events.has_match("EPL", 2025, 1) and events.store.keys(R.RAW_KIND) == []
    assert events.ingest("EPL", 2025, 1, raw_doc(passes=40))
    first = events.store.meta(R.RAW_KIND, "EPL:2025:1")
    assert events.ingest("EPL", 2025, 1, raw_doc(passes=40))
    assert events.match_ids("EPL", 2025) == [1] and events.store.meta(R.RAW_KIND, "EPL:2025:1")[2] is True and first[1] == "whoscored"
    assert events.raw.get("EPL", 2025, 1)["home"]["name"] == "Reds"          # the document comes back exactly as it went in


def test_pages_soccerdata_left_in_its_download_cache_are_adopted_without_the_network(tmp_path):
    folder = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "ENG-Premier League_2526"
    folder.mkdir(parents=True)
    (folder / "1903117.json").write_text(json.dumps(raw_doc(passes=30)))
    (folder / "1903118.json").write_text("null")                       # soccerdata writes null for a page it could not read
    (folder / "notes.txt").write_text("ignored")
    other = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "XXX-Unknown League_2526"
    other.mkdir()
    (other / "5.json").write_text(json.dumps(raw_doc()))
    store = Store(tmp_path / "s.sqlite")
    try:
        result = R.import_soccerdata_cache(store, tmp_path)
        assert result == {"imported": 1, "already": 0, "rejected": 1, "files": 2}
        assert R.RawStore(store).ids("EPL", 2025) == [1903117]
        assert R.import_soccerdata_cache(store, tmp_path)["imported"] == 0   # idempotent
        assert R.reclaimable_bytes(store, tmp_path) > 0
        freed = R.reclaim(store, tmp_path)                                    # the duplicate is safe to delete: the store has it
        assert freed["deleted"] == 1 and not (folder / "1903117.json").exists() and (folder / "1903118.json").exists()
        assert R.RawStore(store).get("EPL", 2025, 1903117) is not None
    finally:
        store.close()


def test_season_codes_round_trip():
    assert R.season_code(2025) == "2526" and R.season_from_code("2526") == 2025 and R.season_from_code("xx") is None


# ------------------------------------------------------------------ silver and gold: derived, versioned, rebuilt offline


def test_ingesting_a_match_derives_silver_and_gold_at_once(events):
    events.ingest("EPL", 2025, 7, raw_doc(passes=40))
    assert events.silver("EPL", 2025, 7).info["venue"] == "Ground" and events.gold("EPL", 2025, 7)["teams"][0]["c"]["passes"] == 40
    assert events.store.get(SV.SILVER_KIND, "EPL:2025:7").body["v"] == SV.SILVER_VERSION and events.store.get(C.GOLD_KIND, "EPL:2025:7").body["v"] == C.GOLD_VERSION


def test_matches_added_to_an_empty_store_are_current_and_are_not_rebuilt_at_the_next_start(events):
    events.ingest("EPL", 2025, 7, raw_doc(passes=40))
    events.ingest("EPL", 2025, 8, raw_doc(passes=41))
    assert events.store.kv_get(DERIVED_MARK) == [SV.SILVER_VERSION, C.GOLD_VERSION] and events.pending_rebuild() == 0
    events.store.kv_delete(DERIVED_MARK)
    assert events.pending_rebuild() == 2                                  # a store from before the marker existed cannot be vouched for: it is rebuilt once
    events.ingest("EPL", 2025, 9, raw_doc(passes=42))
    assert events.store.kv_get(DERIVED_MARK) is None                      # ...and a match added to it does not pretend otherwise
    events.ensure_current()
    assert events.pending_rebuild() == 0


def test_a_changed_definition_rebuilds_from_the_stored_raw_page_with_no_network(events, monkeypatch):
    events.ingest("EPL", 2025, 7, raw_doc(passes=40))
    events.ensure_current()
    assert events.pending_rebuild() == 0 and events.store.kv_get(DERIVED_MARK) == [SV.SILVER_VERSION, C.GOLD_VERSION]
    monkeypatch.setattr(C, "GOLD_VERSION", C.GOLD_VERSION + 1)           # a definition changed: the gold version moves
    assert events.pending_rebuild() == 1                                  # ...and the stored match is out of date
    rebuilt = events.ensure_current()
    assert rebuilt["rebuilt"] == 1 and rebuilt["failed"] == 0 and events.pending_rebuild() == 0
    assert events.store.get(C.GOLD_KIND, "EPL:2025:7").body["v"] == C.GOLD_VERSION


def test_silver_and_gold_that_are_missing_or_stale_are_rebuilt_on_demand(events):
    events.ingest("EPL", 2025, 7, raw_doc(passes=40))
    events.store.delete(C.GOLD_KIND)
    events.store.put(SV.SILVER_KIND, "EPL:2025:7", {"v": 0}, source="derived", complete=True)        # silver from an older parser
    assert events.gold("EPL", 2025, 7)["teams"][0]["c"]["passes"] == 40 and events.silver("EPL", 2025, 7).n > 0
    assert events.silver("EPL", 2025, 999) is None and events.gold("EPL", 2025, 999) is None


def test_a_season_adds_up_and_the_version_moves_when_a_match_is_added(events):
    events.ingest("EPL", 2025, 1, raw_doc(passes=40, home="Reds", away="Blues"))
    events.ingest("EPL", 2025, 2, raw_doc(passes=30, home="Blues", away="Reds", day="2025-08-23"))
    events.ingest("EPL", 2024, 3, raw_doc(passes=99))
    assert events.seasons() == [("EPL", 2024, 1), ("EPL", 2025, 2)]
    season = events.season("EPL", 2025)
    assert season["games"] == 2 and season["teams"]["Reds"]["matches"] == 2
    assert season["teams"]["Reds"]["c"]["passes"] == 40 + 60 and season["teams"]["Reds"]["a"]["passes"] == 60 + 30   # for and against, by side per match
    one = season["players"][1]
    assert one["c"]["passes"] == 70 and one["matches"] == 2 and one["starts"] == 2
    assert one["teams"] == {"Reds": 90.0, "Blues": 90.0}              # he is always the home side's man, and the home side's name changes between these two matches
    assert [(r["date"], r["home"]) for r in season["teams"]["Reds"]["log"]] == [("2025-08-16", True), ("2025-08-23", False)]
    assert events.season("EPL", 2025) is season                       # remembered until something changes
    before = events.version("EPL", 2025)
    events.ingest("EPL", 2025, 4, raw_doc(passes=5, day="2025-08-30"))
    assert events.version("EPL", 2025)[0] == before[0] + 1 and events.season("EPL", 2025)["players"][1]["c"]["passes"] == 75


def test_run_status_goes_stale_when_the_fetching_process_dies(events):
    events.set_status("EPL", 2025, running=True, done=3, total=380)
    assert events.status("EPL", 2025)["running"] is True
    events.store.kv_set("events:run:EPL:2025", {"running": True, "done": 3, "updated": time.time() - STALE_AFTER - 5})
    status = events.status("EPL", 2025)
    assert status["running"] is False and status["stalled"] is True and status["done"] == 3
    assert events.status("EPL", 1999) is None


def test_clearing_the_cache_can_keep_event_data(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    es = EventStore(store)
    es.ingest("EPL", 2025, 1, raw_doc())
    store.put("league", "EPL:2025", {"x": 1}, source="understat")
    store.clear(keep=("ws_raw", "ws_silver", "ws_gold"))
    assert es.has_match("EPL", 2025, 1) and store.get("league", "EPL:2025") is None and es.gold("EPL", 2025, 1) is not None
    store.clear()
    assert not es.has_match("EPL", 2025, 1)
    store.close()


# ------------------------------------------------------------------ linking WhoScored to Understat: matches, clubs, players


def fixture(fid, day, home, away, hg, ag):
    return Fixture(id=fid, dt=f"{day} 14:00:00", home=home, away=away, home_short=home[:3], away_short=away[:3], played=True, hg=hg, ag=ag, hxg=1.0, axg=1.0)


def test_matches_clubs_are_lined_up_by_date_and_score_and_odd_spellings_are_learned(events):
    events.ingest("EPL", 2025, 1, raw_doc(home="Man Utd", away="Wolves", score="2 : 1", day="2025-08-16"))
    events.ingest("EPL", 2025, 2, raw_doc(home="Wolves", away="Man Utd", score="0 : 0", day="2025-08-23"))
    events.ingest("EPL", 2025, 3, raw_doc(home="Everton", away="Arsenal", score="1 : 1", day="2025-09-01"))      # nothing on Understat's side matches this one
    fixtures = [fixture(10, "2025-08-15", "Manchester United", "Wolverhampton Wanderers", 2, 1),     # a day earlier: the two sources keep time differently
                fixture(11, "2025-08-23", "Wolverhampton Wanderers", "Manchester United", 0, 0),
                fixture(12, "2025-09-01", "Everton", "Arsenal", 3, 3)]                                 # same teams and date, different score: not the same match
    links, teams, unlinked = link_fixtures(events.season("EPL", 2025), fixtures)
    assert {g: f.id for g, f in links.items()} == {1: 10, 2: 11}
    assert teams == {"Man Utd": "Manchester United", "Wolves": "Wolverhampton Wanderers"}
    assert [m["game"] for m in unlinked] == [3]


def test_a_match_names_cannot_place_is_placed_by_date_and_score_only_when_exactly_one_fits(events):
    events.ingest("EPL", 2025, 1, raw_doc(home="Zorb FC", away="Quux Town", score="3 : 2", day="2025-08-16"))
    events.ingest("EPL", 2025, 2, raw_doc(home="Zorb FC", away="Quux Town", score="1 : 0", day="2025-08-16"))
    fixtures = [fixture(10, "2025-08-16", "Alpha", "Beta", 3, 2), fixture(11, "2025-08-16", "Gamma", "Delta", 1, 0), fixture(12, "2025-08-16", "Epsilon", "Zeta", 1, 0)]
    links, teams, unlinked = link_fixtures(events.season("EPL", 2025), fixtures)
    assert links[1].id == 10 and 2 not in links and [m["game"] for m in unlinked] == [2]         # two fixtures share 1-0 that day: refuse to guess


def test_players_the_names_miss_are_found_in_the_matches_both_sources_saw(events):
    def doc(day, minutes_on):
        ev_ = [ev("Pass", 1, minute=m) for m in range(1, 40)] + [ev("SubstitutionOn", 2, minute=minutes_on), *[ev("Pass", 2, minute=minutes_on + i) for i in range(1, 15)], end(100)]
        d = match(ev_, home_players=[player(1), player(2, start=False, name="Rayan Cherki")], away_players=[player(9, team_side="away")])
        d["startTime"] = f"{day}T15:00:00"
        return d

    for i, day in enumerate(("2025-08-16", "2025-08-23", "2025-08-30", "2025-09-06"), start=1):
        events.ingest("EPL", 2025, i, {**doc(day, 60), "events": doc(day, 60)["events"] + [ev("Pass", 9, team=AWAY, minute=m) for m in range(1, 60)]})
    season = events.season("EPL", 2025)
    fixtures = [fixture(100 + i, day, "Reds", "Blues", 1, 0) for i, day in enumerate(("2025-08-16", "2025-08-23", "2025-08-30", "2025-09-06"), start=1)]
    links, teams, _ = link_fixtures(season, fixtures)
    def page(started):
        roster = RosterEntry(player_id=77, player="Mathis Cherki", position="Sub" if not started else "MC", minutes=30, goals=0, own_goals=0, shots=0, xg=0.0, key_passes=0, assists=0,
                             xa=0.0, xgchain=0.0, xgbuildup=0.0, yellow=0, red=0, venue="h")
        other = RosterEntry(player_id=78, player="Mathis Other", position="Sub", minutes=30, goals=0, own_goals=0, shots=0, xg=0.0, key_passes=0, assists=0, xa=0.0, xgchain=0.0, xgbuildup=0.0, yellow=0, red=0, venue="h")
        return MatchPage(id=0, shots={"h": [], "a": []}, rosters={"h": [roster, other], "a": []})
    pages = {f.id: page(False) for f in fixtures}
    us = [understat(77, "Mathis Cherki", "Reds"), understat(78, "Mathis Other", "Reds")]
    found = link_by_lineups([season["players"][2]], us, pages, links, teams)
    assert found == {77: 2}                       # shares "Cherki", came off the bench in every match; "Other" shares no word of his name
    two = link_by_lineups([season["players"][2], {**season["players"][2], "id": 3}], us, pages, links, teams)
    assert two == {}                              # two people claiming the same candidate: leave both alone


def test_players_link_on_name_words_and_club():
    ws = {
        1: {"id": 1, "name": "Heung-Min Son", "teams": {"Tottenham": 900.0}, "min": 900.0},
        2: {"id": 2, "name": "Joao Pedro", "teams": {"Brighton": 600.0}, "min": 600.0},
        3: {"id": 3, "name": "Rodri", "teams": {"Manchester City": 800.0}, "min": 800.0},
        4: {"id": 4, "name": "Jan Smith", "teams": {"Reds": 500.0}, "min": 500.0},
        5: {"id": 5, "name": "Wolves Player", "teams": {"Wolves": 300.0}, "min": 300.0},
    }
    us = [
        understat(10, "Son Heung-Min", "Tottenham"),              # word order differs
        understat(11, "João Pedro", "Brighton"),                   # accents differ
        understat(12, "Rodrigo Hernandez", "Manchester City"),     # a single word must never link by partial overlap
        understat(13, "Jan Smith", "Blues"), understat(14, "Jan Smith", "Reds"),   # same name, told apart by club
        understat(15, "Wolves Player", "Wolverhampton Wanderers"),  # short club name via alias
    ]
    linked, unlinked = link_season(ws, us)
    assert linked[10]["id"] == 1 and linked[11]["id"] == 2 and linked[14]["id"] == 4 and linked[15]["id"] == 5
    assert 12 not in linked and 13 not in linked
    assert [u["name"] for u in unlinked] == ["Rodri"]


def test_single_word_understat_names_link_only_when_unambiguous_on_both_sides():
    ws = {
        1: {"id": 1, "name": "Alisson Becker", "teams": {"Liverpool": 900.0}, "min": 900.0},
        2: {"id": 2, "name": "Gabriel Magalhaes", "teams": {"Arsenal": 900.0}, "min": 900.0},
        3: {"id": 3, "name": "Gabriel Jesus", "teams": {"Arsenal": 800.0}, "min": 800.0},
        4: {"id": 4, "name": "Rodrigo Hernandez", "teams": {"Manchester City": 700.0}, "min": 700.0},
        5: {"id": 5, "name": "Rodrigo Munoz", "teams": {"Manchester City": 600.0}, "min": 600.0},
    }
    us = [
        understat(10, "Alisson", "Liverpool"),
        understat(11, "Gabriel", "Arsenal"), understat(12, "Gabriel Jesus", "Arsenal"),
        understat(13, "Rodrigo", "Manchester City"),                # two Rodrigos at the club: which one? refuse
    ]
    linked, unlinked = link_season(ws, us)
    assert linked[10]["id"] == 1                                    # the only unmatched Alisson on both sides
    assert linked[11]["id"] == 2 and linked[12]["id"] == 3          # Gabriel Jesus matches exactly, which leaves "Gabriel" for Magalhaes
    assert 13 not in linked and {u["name"] for u in unlinked} == {"Rodrigo Hernandez", "Rodrigo Munoz"}


def test_common_nicknames_match_on_the_same_club():
    ws = {1: {"id": 1, "name": "Andy Robertson", "teams": {"Liverpool": 900.0}, "min": 900.0}, 2: {"id": 2, "name": "Matty Cash", "teams": {"Aston Villa": 800.0}, "min": 800.0}}
    us = [understat(10, "Andrew Robertson", "Liverpool"), understat(11, "Matthew Cash", "Aston Villa"), understat(12, "Andrew Robertson", "Elsewhere")]
    linked, unlinked = link_season(ws, us)
    assert linked[10]["id"] == 1 and linked[11]["id"] == 2 and 12 not in linked and unlinked == []


def test_ambiguity_and_wrong_club_are_left_unlinked():
    ws = {1: {"id": 1, "name": "Jan Smith", "teams": {"Reds": 500.0}, "min": 500.0}, 2: {"id": 2, "name": "Ann Lee", "teams": {"Elsewhere": 400.0}, "min": 400.0}}
    us = [understat(1, "Jan Smith", "Reds"), understat(2, "Jan Smith", "Reds"), understat(3, "Ann Lee", "Home FC")]
    linked, unlinked = link_season(ws, us)
    assert linked == {}                                              # two Jan Smiths at the same club: refuse to guess; Ann Lee is at another club
    assert {u["name"] for u in unlinked} == {"Jan Smith", "Ann Lee"}
