"""The `prem events` command and the cache-clearing safeguard."""

from __future__ import annotations


from app.cli import main
from app.data.store import Store
from app.events.store import EventStore

from .events_kit import AWAY, end, ev, match, player


def seeded(tmp_path):
    store = Store(tmp_path / "prem.sqlite")
    events = EventStore(store)
    events.ingest("EPL", 2025, 1, match([ev("Pass", 1, minute=1 + i % 90) for i in range(60)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 90) for i in range(10)] + [end()],
                                        home_players=[player(1)], away_players=[player(2, team_side="away")]))
    events.set_status("EPL", 2025, running=False, finished_matches=380, done=1, failed=0)
    store.put("league", "EPL:2025", {"x": 1}, source="understat")
    return store, events


def test_status_lists_what_is_stored(tmp_path, capsys):
    store, _ = seeded(tmp_path)
    store.close()
    assert main(["events", "status", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "EPL 2025: 1 of 380 matches stored" in out and "idle" in out


def test_status_with_nothing_stored_says_how_to_start(tmp_path, capsys):
    Store(tmp_path / "prem.sqlite").close()
    assert main(["events", "status", "--data-dir", str(tmp_path)]) == 0
    assert "prem events sync" in capsys.readouterr().out


def test_bare_events_command_explains_itself(capsys):
    assert main(["events"]) == 1
    assert "prem events sync" in capsys.readouterr().out


def test_clear_keeps_event_data_unless_asked(tmp_path, capsys):
    store, _ = seeded(tmp_path)
    store.close()
    assert main(["clear", "--data-dir", str(tmp_path)]) == 1                       # asks for confirmation and says what it keeps
    assert "Event data is kept" in capsys.readouterr().out

    assert main(["clear", "--yes", "--data-dir", str(tmp_path)]) == 0
    store = Store(tmp_path / "prem.sqlite")
    assert EventStore(store).has_match("EPL", 2025, 1) and store.get("league", "EPL:2025") is None
    store.close()

    assert main(["clear", "--yes", "--events", "--data-dir", str(tmp_path)]) == 0
    store = Store(tmp_path / "prem.sqlite")
    assert not EventStore(store).has_match("EPL", 2025, 1)
    store.close()


def test_sync_reports_a_missing_optional_dependency_cleanly(tmp_path, capsys, monkeypatch):
    from app.events import fetch

    monkeypatch.setattr(fetch, "find_browser", lambda: "/usr/bin/true")
    monkeypatch.setitem(__import__("sys").modules, "soccerdata", None)               # importing it now raises ImportError
    monkeypatch.chdir(tmp_path)
    assert main(["events", "sync", "--league", "EPL", "--seasons", "2025", "--data-dir", str(tmp_path)]) == 2
    out = capsys.readouterr().out
    assert "soccerdata" in out and "--extra events" in out
    store = Store(tmp_path / "prem.sqlite")
    assert EventStore(store).status("EPL", 2025)["running"] is False                  # never left marked as running
    store.close()


def test_import_adopts_pages_the_download_cache_holds_and_reclaim_deletes_the_duplicates(tmp_path, capsys):
    import json

    folder = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "ENG-Premier League_2526"
    folder.mkdir(parents=True)
    doc = match([ev("Pass", 1, minute=1 + i % 90) for i in range(60)] + [ev("Pass", 2, team=AWAY, minute=1 + i % 90) for i in range(10)] + [end()],
                home_players=[player(1)], away_players=[player(2, team_side="away")])
    (folder / "1903117.json").write_text(json.dumps(doc))
    Store(tmp_path / "prem.sqlite").close()
    assert main(["events", "import", "--data-dir", str(tmp_path)]) == 0
    assert "1 matches imported" in capsys.readouterr().out
    assert main(["events", "reclaim", "--data-dir", str(tmp_path)]) == 1                 # asks first
    assert (folder / "1903117.json").exists()
    assert main(["events", "reclaim", "--yes", "--data-dir", str(tmp_path)]) == 0
    assert not (folder / "1903117.json").exists()
    store = Store(tmp_path / "prem.sqlite")
    assert EventStore(store).has_match("EPL", 2025, 1903117)                             # the store still has it
    store.close()


def test_rebuild_says_what_it_did(tmp_path, capsys):
    store, _ = seeded(tmp_path)
    store.kv_delete("events:derived")
    store.delete("ws_gold")
    store.close()
    assert main(["rebuild", "--data-dir", str(tmp_path)]) == 0
    assert "1 matches need rebuilding" in capsys.readouterr().out
    assert main(["rebuild", "--data-dir", str(tmp_path)]) == 0
    assert "up to date" in capsys.readouterr().out
