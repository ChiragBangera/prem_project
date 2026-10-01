"""Event data: the store, the rates built from it and linking WhoScored players to Understat players."""

from __future__ import annotations

import time

import pytest

from app.data.models import PlayerSeason
from app.data.store import Store
from app.events.aggregate import COUNTS
from app.events.link import link_season
from app.events.rates import event_rates, merge_totals, with_duels
from app.events.store import STALE_AFTER, EventStore


def row(pid, name, team, minutes=90.0, **counts):
    return {"id": pid, "name": name, "team": team, "min": minutes, "start": 1, **{k: 0 for k in COUNTS}, **counts}


def understat(pid, name, *teams):
    return PlayerSeason(id=pid, name=name, teams=list(teams), position="D S", games=10, minutes=900, goals=0, npg=0, assists=0, shots=0,
                        key_passes=0, yellow=0, red=0, xg=0.0, npxg=0.0, xa=0.0, xgchain=0.0, xgbuildup=0.0)


@pytest.fixture()
def events(tmp_path):
    store = Store(tmp_path / "s.sqlite")
    yield EventStore(store)
    store.close()


def test_matches_are_stored_once_and_add_up(events):
    events.put_match("EPL", 2025, 101, [row(1, "A B", "Reds", 90, passes=40, tackles=2), row(2, "C D", "Blues", 45, passes=10)], home="Reds", away="Blues")
    events.put_match("EPL", 2025, 102, [row(1, "A B", "Reds", 80, passes=30, tackles=1, challenges=1)])
    events.put_match("EPL", 2024, 55, [row(1, "A B", "Reds", 90, passes=99)])
    assert events.has_match("EPL", 2025, 101) and not events.has_match("EPL", 2025, 999)
    assert sorted(events.match_ids("EPL", 2025)) == [101, 102]
    assert events.seasons() == [("EPL", 2024, 1), ("EPL", 2025, 2)]
    totals = events.season_totals("EPL", 2025)
    a = totals[1]
    assert a["passes"] == 70 and a["tackles"] == 3 and a["challenges"] == 1 and a["min"] == 170.0 and a["matches"] == 2 and a["starts"] == 2
    assert a["teams"] == {"Reds": 170.0} and totals[2]["min"] == 45.0
    # the version moves when a match is added, which is how cached results learn they are stale
    before = events.version("EPL", 2025)
    events.put_match("EPL", 2025, 103, [row(1, "A B", "Reds", 90, passes=5)])
    assert events.version("EPL", 2025)[0] == before[0] + 1 and events.season_totals("EPL", 2025)[1]["passes"] == 75


def test_rows_stored_in_an_older_format_are_ignored_and_flagged_for_re_reading(events):
    events.store.put("events", "EPL:2025:7", {"v": 1, "game": 7, "rows": [row(1, "A B", "Reds", 90, passes=99)]}, source="whoscored", complete=True)
    events.put_match("EPL", 2025, 8, [row(1, "A B", "Reds", 90, passes=10)])
    assert events.has_match("EPL", 2025, 7) and not events.has_current_match("EPL", 2025, 7) and events.has_current_match("EPL", 2025, 8)
    assert events.season_totals("EPL", 2025)[1]["passes"] == 10        # the old-format row is not mixed in with definitions that have changed


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
    es.put_match("EPL", 2025, 1, [row(1, "A B", "Reds")])
    store.put("league", "EPL:2025", {"x": 1}, source="understat")
    store.clear(keep=("events",))
    assert es.has_match("EPL", 2025, 1) and store.get("league", "EPL:2025") is None
    store.clear()
    assert not es.has_match("EPL", 2025, 1)
    store.close()


def test_rates_use_exact_definitions():
    t = {"min": 900.0, "passes": 600, "pass_ok": 500, "fwd": 150, "prog": 40, "tackles": 20, "challenges": 10, "aer": 50, "aer_won": 30,
         "aer_def": 30, "aer_def_won": 20, "int": 15, "rec": 60}
    r = event_rates(t)
    assert with_duels(t)["def_duels"] == 60 and with_duels(t)["def_won"] == 40      # tackles + challenges + defending aerials; won = tackles + won aerials
    assert r["def_duels90"] == pytest.approx(6.0) and r["def_duel_win"] == pytest.approx(40 / 60)
    assert r["fwd_pass_ratio"] == pytest.approx(0.25) and r["pass_acc"] == pytest.approx(500 / 600) and r["aerial_win"] == pytest.approx(0.6)
    assert r["prog_passes90"] == pytest.approx(4.0) and r["tackles90"] == pytest.approx(2.0) and r["interceptions90"] == pytest.approx(1.5)
    empty = event_rates({"min": 0.0, **{k: 0 for k in COUNTS}})
    assert all(v is None for v in empty.values())   # nothing played, nothing to report (never a zero that looks like a measurement)
    assert merge_totals([{**t, "id": 1, "name": "A", "teams": {"X": 900.0}}, {**t, "id": 1, "name": "A", "teams": {"X": 100.0, "Y": 5.0}}])["passes"] == 1200


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
