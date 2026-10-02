"""Event data end to end through the API: raw store -> linking -> Scout rows -> player page -> Data page. No network, no browser."""

from __future__ import annotations

import time
from datetime import date

from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings

from .events_kit import AWAY, end, ev, match, player

EVENT_KEYS = ("fwd_pass_ratio", "pass_acc", "def_duel_win", "aerial_win", "passes90", "prog_passes90", "def_duels90", "tackles90", "interceptions90", "recoveries90")


def val(body, row, key):
    return row["v"][body["keys"].index(key)]


def club_match(club: str, players: list[dict], index: int, day: str) -> dict:
    """A raw match at ``club`` in which these Understat players (given a WhoScored id of 5000 + theirs) all play the full match."""
    events = []
    for k, p in enumerate(players):
        pid, scale = 5000 + p["id"], 1 + (k + index) % 5
        events += [ev("Pass", pid, x=30, end_x=45, minute=1 + (i % 90)) for i in range(40 * scale)]
        events += [ev("Pass", pid, x=60, end_x=62, minute=2 + (i % 90), outcome=0) for i in range(10 * scale)]
        events += [ev("Tackle", pid, minute=5 + i) for i in range(scale)] + [ev("Challenge", pid, minute=30, outcome=0)] + [ev("BallRecovery", pid, minute=40 + i) for i in range(3 * scale)]
        events += [ev("Aerial", pid, x=20, minute=50 + i, outcome=i % 2, quals=("Defensive",)) for i in range(3)]
    events += [ev("Pass", 9999, team=AWAY, minute=1 + i % 90) for i in range(60)] + [end(100)]
    doc = match(events, home=club, away="Elsewhere FC", score="1 : 0", home_players=[player(5000 + p["id"], name=p["name"], position="MC") for p in players],
                away_players=[player(9999, team_side="away")])
    doc["startTime"] = f"{day}T15:00:00"
    return doc


def settled(client, **params) -> dict:
    """Scout rows once background role learning has finished (the first request legitimately shifts roles and percentiles once)."""
    for _ in range(40):
        payload = client.get("/api/players", params=params).json()
        if not payload["enrichment"]["roles"]["running"] and not payload["enrichment"]["ages"]["running"]:
            return client.get("/api/players", params=params).json()
        time.sleep(0.25)
    raise AssertionError("enrichment did not finish")


def test_event_data_flows_from_the_store_to_scout_the_player_page_and_the_data_page(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2021, 1, 15))
    with TestClient(app) as c:
        wb = c.app.state.wb
        before = settled(c, leagues="EPL", seasons="2019")
        assert before["coverage"]["event_players"] == 0 and c.get("/api/data/status").json()["events"] == []
        regulars = [r for r in before["rows"] if val(before, r, "minutes") >= 900 and r["group"] != "GK"]
        club_a = regulars[0]["teams"][0]
        club_b = next(r["teams"][0] for r in regulars if r["teams"][0] != club_a)
        chosen = [r for r in regulars if r["teams"] == [club_a]][:7] + [r for r in regulars if r["teams"] == [club_b]][:7]
        assert len(chosen) == 14

        for game, day in enumerate(("2019-08-10", "2019-08-17", "2019-08-24"), start=1):   # three matches per club stored: the dataset must notice without a restart
            for club, group in ((club_a, chosen[:7]), (club_b, chosen[7:])):
                assert wb.events.ingest("EPL", 2019, game * 10 + (club == club_b), club_match(club, group, game, day))

        after = settled(c, leagues="EPL", seasons="2019")
        assert after["coverage"]["event_players"] == 14 and after["coverage"]["event_matches"] == 6
        by_id, old = {r["id"]: r for r in after["rows"]}, {r["id"]: r for r in before["rows"]}
        base_keys = [k for k in after["keys"] if k in ("npxg90", "xa90", "shots90", "xgchain90", "output")]
        assert all(val(after, by_id[i], k) == val(before, old[i], k) for i in old for k in base_keys)          # nothing that already existed moves
        assert all(after["rows"][0]["p"][after["keys"].index(k)] == before["rows"][0]["p"][before["keys"].index(k)] for k in base_keys)

        have = [by_id[r["id"]] for r in chosen]
        assert all(r["ev_minutes"] == 270 and r["ev_matches"] == 3 and all(val(after, r, k) is not None for k in EVENT_KEYS) for r in have)
        others = [r for r in after["rows"] if r["id"] not in {x["id"] for x in chosen}]
        assert others and all(r["ev_minutes"] == 0 and val(after, r, "tackles90") is None for r in others)   # no event data is blank, never zero

        # the player page
        target = have[0]
        body = c.get(f"/api/player/{target['id']}", params={"league": "EPL", "season": "2019"}).json()
        card = body["detail"]["events"]
        assert card["available"] and card["matches"] == 3 and card["minutes"] == 270 and card["pool_n"] > 0
        assert any(i["needs"] == "events" and i["pct"] is not None for b in body["detail"]["blocks"] for i in b["items"])
        blank = c.get(f"/api/player/{others[0]['id']}", params={"league": "EPL", "season": "2019"}).json()["detail"]["events"]
        assert blank == {"available": False, "stored": True}

        # Compare: event metrics appear only when two or more of the players have event data
        outfield_without = next(r for r in others if r["group"] != "GK" and val(after, r, "minutes") >= 270)   # Compare refuses goalkeepers
        two, one = have[:2], [have[0], outfield_without]
        cmp2 = c.get("/api/compare/players", params={"ids": ",".join(str(r["id"]) for r in two), "league": "EPL", "season": "2019"}).json()
        assert cmp2["event_metrics"] and all(len(m["values"]) == 2 and len(m["pct"]) == 2 for m in cmp2["event_metrics"])
        assert all(p["ev_minutes"] == 270 for p in cmp2["players"])
        cmp1 = c.get("/api/compare/players", params={"ids": ",".join(str(r["id"]) for r in one), "league": "EPL", "season": "2019"}).json()
        assert cmp1["event_metrics"] == []                    # only one of them has event data: nothing to compare

        # the Data page: raw matches stored, how well they line up, and the coverage matrix
        status = c.get("/api/data/status").json()
        (entry,) = status["events"]
        assert (entry["league"], entry["season"], entry["matches"]) == ("EPL", 2019, 6) and entry["total"] == 380 and entry["linked"] == 14
        assert [u["id"] for u in entry["unlinked"]] == [9999]       # the one player nobody could place (the filler on the other side) is listed, not guessed at
        row = next(r for r in status["matrix"] if (r["league"], r["season"]) == ("EPL", 2019))
        assert row["events"] == 6 and row["silver"] == 6 and row["played"] == 380
        assert status["store"]["kinds"]["ws_raw"]["count"] == 6 and status["store"]["kinds"]["ws_gold"]["count"] == 6


def test_events_are_picked_up_after_a_restart_from_pages_only_the_download_cache_holds(tmp_path):
    """The app starts, finds event pages in the download cache that the store lacks, stores them, and serves them: no command needed."""
    import json

    folder = tmp_path / "soccerdata" / "data" / "WhoScored" / "events" / "ENG-Premier League_1920"
    folder.mkdir(parents=True)
    (folder / "777.json").write_text(json.dumps(club_match("Arsenal", [{"id": 1, "name": "Some Player"}], 1, "2019-08-10")))
    with TestClient(create_app(Settings(data_dir=tmp_path, demo=True, min_interval=0), today=date(2021, 1, 15))) as c:
        for _ in range(40):
            if (c.get("/api/data/status").json()["boot"] or {}).get("stage") == "done":
                break
            time.sleep(0.25)
        status = c.get("/api/data/status").json()
        assert status["boot"]["stage"] == "done" and status["boot"]["adopted"] == 1
        assert status["store"]["kinds"]["ws_raw"]["count"] == 1 and status["reclaimable_bytes"] > 0
        assert c.post("/api/data/reclaim").json()["deleted"] == 1 and not (folder / "777.json").exists()
