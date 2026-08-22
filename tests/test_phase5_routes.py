"""Phase 5R Stage 1 — HTTP exposure of Sofascore/Federated endpoints.

Verifies the previously-dead service methods are reachable over HTTP, honest
gate-off payloads (200 not 500), sqlite write-through of cache/sofa.db, and
the Understat→Sofascore event-ID resolver (cache → manual CSV → search).
No live network: clients are injected fakes.
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app import api as api_module
from app.stat_data.sofascore import SofascoreClient


class FakeSofascore(SofascoreClient):
    """SofascoreClient with canned responses and no network/throttle."""

    def __init__(self, cache_dir, **kwargs):
        super().__init__(
            httpx_client=mock.MagicMock(),  # triggers _should_throttle() -> False
            enabled_override=True,
            cache_dir=cache_dir,
        )

    async def _request(self, path, params=None):
        if "/statistics" in path:
            return {"statistics": []}
        if "/lineups" in path:
            return {"confirmed": True}
        return {}


_svc = None


def _make_service(sofa):
    global _svc
    # Real AnalyticsService without Understat client usage for these methods.
    from app.analytics_service import AnalyticsService

    _svc = AnalyticsService(client=None, sofascore_client=sofa)
    # Force-enabled regardless of ambient env during tests.
    _svc._is_sofascore_enabled = lambda: True
    return _svc


class SofascoreRoutesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name)
        os.environ.pop("SOFASCORE_ENABLED", None)
        self.fake = FakeSofascore(self.cache_dir)
        self.service = _make_service(self.fake)
        self.app = api_module.app
        self.client = TestClient(self.app)

    def tearDown(self):
        self.tmp.cleanup()

    def _override_state(self):
        self.app.state.analytics = self.service
        self.app.state.sofascore = self.fake

    def test_statistics_route_returns_payload_200(self):
        self._override_state()
        resp = self.client.get("/api/v1/sofascore/event/15186861/statistics")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["enabled"])
        self.assertIn("data", body)

    def test_gate_off_returns_honest_200_not_500(self):
        self.service._is_sofascore_enabled = lambda: False
        self._override_state()
        for path in (
            "/api/v1/sofascore/event/15186861/statistics",
            "/api/v1/sofascore/event/15186861/incidents",
            "/api/v1/sofascore/event/15186861/player/868812/rating-breakdown",
            "/api/v1/sofascore/event/15186861/player/868812/heatmap",
        ):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 200, path)
            body = resp.json()
            self.assertFalse(body["enabled"])
            self.assertIn("honest_note", body)
            self.assertEqual(body.get("fallback"), "understat")

    def test_incidents_sorted_chronological(self):
        calls = {"n": 0}

        async def fake_request(path, params=None):
            if "/incidents" in path:
                return {
                    "incidents": [
                        {"incidentType": "goal", "time": 78, "isHome": False},
                        {"incidentType": "card", "time": 34, "isHome": True},
                        {"incidentType": "goal", "time": 4, "addedTime": 2, "isHome": True},
                    ]
                }
            return {}

        self.fake._request = fake_request
        self._override_state()
        resp = self.client.get("/api/v1/sofascore/event/99/incidents")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]["incidents"]
        times = [(i["time"], i.get("addedTime") or 0) for i in data]
        self.assertEqual(times, sorted(times))
        # DROP keys removed
        self.assertTrue(all("reversedPeriodTime" not in i for i in data))

    def test_shotmap_player_query_param_routed(self):
        seen = {}

        async def fake_shotmap(event_id, player_id=None):
            seen["event_id"] = event_id
            seen["player_id"] = player_id
            return {"enabled": True, "data": {"shotmap": []}, "honest_note": "ok"}

        self.service.get_sofascore_shotmap = fake_shotmap
        self._override_state()
        resp = self.client.get("/api/v1/sofascore/event/42/shotmap?player_id=868812")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen, {"event_id": 42, "player_id": 868812})


class SqlitePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name)
        self.client_obj = SofascoreClient(
            httpx_client=mock.MagicMock(),
            enabled_override=True,
            cache_dir=self.cache_dir,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_cache_set_writes_through_to_sofa_db(self):
        payload = {"hello": "world"}
        self.client_obj._cache_set("stats:123", payload)
        db = self.cache_dir / "sofa.db"
        self.assertTrue(db.exists())
        import sqlite3

        with sqlite3.connect(str(db)) as conn:
            row = conn.execute("SELECT data FROM cache WHERE key=?", ("stats:123",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row[0]), payload)

    def test_cache_get_falls_back_to_sqlite_after_memory_loss(self):
        self.client_obj._cache_set("stats:456", {"a": 1})
        # simulate process restart: fresh instance, same cache dir
        fresh = SofascoreClient(
            httpx_client=mock.MagicMock(),
            enabled_override=True,
            cache_dir=self.cache_dir,
        )
        got = fresh._cache_get("stats:456")
        self.assertIsNotNone(got)
        self.assertEqual(got["a"], 1)

    def test_ttl_expiry_on_disk_entry(self):
        import time as _t

        self.client_obj._cache_set("stats:789", {"b": 2})
        # simulate restart: drop the in-memory L1 so the read hits sqlite L2
        self.client_obj._cache.clear()
        # backdate the disk row beyond 6h TTL
        import sqlite3

        with sqlite3.connect(str(self.client_obj.sofa_db)) as conn:
            conn.execute("UPDATE cache SET ts=? WHERE key=?", (_t.time() - 7 * 3600, "stats:789"))
            conn.commit()
        self.assertIsNone(self.client_obj._cache_get("stats:789"))


class EventIdResolverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp.name)
        self.data_dir = self.cache_dir.parent / "data" / "sofascore"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.data_dir / "event_map.csv"
        self.client_obj = SofascoreClient(
            httpx_client=mock.MagicMock(),
            enabled_override=True,
            cache_dir=self.cache_dir,
        )
        # redirect project-root lookup to tmp so we don't touch real data/
        self._orig_root = None

    def tearDown(self):
        import shutil

        shutil.rmtree(self.data_dir, ignore_errors=True)
        self.tmp.cleanup()

    def _patch_manual_path(self):
        return mock.patch.object(
            type(self.client_obj),
            "_manual_event_map_path",
            lambda self_: self.csv_path,
        )

    def test_manual_csv_hit_caches_and_resolves(self):
        self.csv_path.write_text("160000,15186861,seeded\n", encoding="utf-8")
        with self._patch_manual_path():
            out = asyncio.run(self.client_obj.resolve_event_id(160000))
        self.assertTrue(out["resolved"])
        self.assertEqual(out["sofascore_event_id"], 15186861)
        self.assertEqual(out["source"], "manual_csv")
        # second call served from permanent sqlite cache, CSV no longer needed
        self.csv_path.unlink()
        with self._patch_manual_path():
            out2 = asyncio.run(self.client_obj.resolve_event_id(160000))
        self.assertTrue(out2["resolved"])
        self.assertEqual(out2["source"], "cache")

    def test_unresolvable_without_home_team_is_honest(self):
        out = asyncio.run(self.client_obj.resolve_event_id(999001))
        self.assertFalse(out["resolved"])
        self.assertIn("honest_note", out)

    def test_search_match_cached_permanently(self):
        async def fake_request(path, params=None):
            if path == "/search/all":
                return {
                    "results": [
                        {"type": "team", "entity": {"id": 2829, "name": "Arsenal"}},
                    ]
                }
            if "/events/last" in path:
                return {
                    "events": [
                        {
                            "id": 777888,
                            "startTimestamp": 1735689600,  # 2025-01-01
                            "homeTeam": {"name": "Arsenal"},
                            "awayTeam": {"name": "Chelsea"},
                        }
                    ]
                }
            return {}

        self.client_obj._request = fake_request
        out = asyncio.run(
            self.client_obj.resolve_event_id(
                555001, home_team="Arsenal", away_team="Chelsea", kickoff_date="2025-01-01"
            )
        )
        self.assertTrue(out["resolved"])
        self.assertEqual(out["sofascore_event_id"], 777888)
        self.assertEqual(out["source"], "search")


if __name__ == "__main__":
    unittest.main()
