"""Event data end to end through the API: store -> linking -> Scout rows -> player page -> Data page."""

from __future__ import annotations

import time
from datetime import date

from starlette.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.events.aggregate import COUNTS
from app.events.rates import EVENT_KEYS


def ws_row(player: dict, index: int, minutes: float = 90.0) -> dict:
    scale = 1 + index % 5
    counts = {k: 0 for k in COUNTS}
    counts.update(passes=40 * scale, pass_ok=30 * scale, fwd=10 * scale, prog=2 * scale, tackles=scale, challenges=1, aer=3, aer_won=2, aer_def=2, aer_def_won=1, rec=3 * scale, **{"int": scale})
    return {"id": 5000 + player["id"], "name": player["name"], "team": player["teams"][0], "min": minutes, "start": 1, **counts}


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
        catalog = c.get("/api/catalog").json()
        assert {"def_duels90", "fwd_pass_ratio", "prog_passes90"} <= set(catalog["metrics"]) and "DEF" in catalog["event_profiles"] and "MIXED" in catalog["event_profiles"]

        before = settled(c, leagues="EPL", seasons="2019")
        assert before["coverage"]["event_players"] == 0 and c.get("/api/data/status").json()["events"] == []
        chosen = [r for r in before["rows"] if r["minutes"] >= 900 and r["group"] != "GK"][:14]
        assert len(chosen) == 14

        for game in (1, 2, 3):                       # three matches stored: the dataset must notice without a restart
            wb.events.put_match("EPL", 2019, game, [ws_row(r, i) for i, r in enumerate(chosen)], home="A", away="B")

        after = settled(c, leagues="EPL", seasons="2019")
        assert after["coverage"]["event_players"] == 14 and after["coverage"]["event_matches"] == 3
        by_id = {r["id"]: r for r in after["rows"]}
        old = {r["id"]: r for r in before["rows"]}
        assert all((by_id[i]["output"], by_id[i]["pct"], by_id[i]["rank"]) == (old[i]["output"], old[i]["pct"], old[i]["rank"]) for i in old)  # nothing existing moved

        have = [by_id[r["id"]] for r in chosen]
        assert all(r["ev_minutes"] == 270 and r["ev_matches"] == 3 and all(r[k] is not None for k in EVENT_KEYS) for r in have)
        others = [r for r in after["rows"] if r["id"] not in {x["id"] for x in chosen}]
        assert others and all(r["ev_minutes"] == 0 and r["evpct"] == {} for r in others)

        # the player page
        target = have[0]
        detail = c.get(f"/api/player/{target['id']}", params={"league": "EPL", "season": "2019"}).json()["detail"]
        card = detail["events"]
        assert card["available"] and card["matches"] == 3 and card["minutes"] == 270 and card["items"] and card["pool_n"] > 0
        blank = c.get(f"/api/player/{others[0]['id']}", params={"league": "EPL", "season": "2019"}).json()["detail"]["events"]
        assert blank == {"available": False, "stored": True}

        # Compare: event metrics appear only when two or more of the players have event data
        outfield_without = next(r for r in others if r["group"] != "GK" and r["minutes"] >= 270)   # Compare refuses goalkeepers
        two, one = have[:2], [have[0], outfield_without]
        cmp2 = c.get("/api/compare/players", params={"ids": ",".join(str(r["id"]) for r in two), "league": "EPL", "season": "2019"}).json()
        assert cmp2["event_metrics"] and all(len(m["values"]) == 2 and len(m["pct"]) == 2 for m in cmp2["event_metrics"])
        assert all(p["ev_minutes"] == 270 for p in cmp2["players"])
        cmp1 = c.get("/api/compare/players", params={"ids": ",".join(str(r["id"]) for r in one), "league": "EPL", "season": "2019"}).json()
        assert cmp1["event_metrics"] == []                    # only one of them has event data: nothing to compare

        # the Data page
        (entry,) = c.get("/api/data/status").json()["events"]
        assert (entry["league"], entry["season"], entry["matches"]) == ("EPL", 2019, 3) and entry["total"] == 380
        assert entry["linked"] == 14 and entry["unlinked"] == []
