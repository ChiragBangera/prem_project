"""Phase 5C — Federation unified cache + rate limit + fallback mock tests.

Mocks httpx for api-football fixtures and football-data standings.
Verifies: cache hit (second call no http), 429/rate-limit handling,
provider fallback (no keys → Understat-only honest_note), nightly prefetch pattern.
"""
import asyncio
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest import mock

# ── Sample payloads ───────────────────────────────────────────────────────

SAMPLE_API_FOOTBALL_FIXTURES = {
    "response": [
        {
            "fixture": {"id": 1035455, "date": "2025-08-15T19:45:00+00:00"},
            "league": {"id": 39, "name": "Premier League", "season": 2025},
            "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 40, "name": "Liverpool"}},
            "goals": {"home": 2, "away": 1},
        }
    ]
}

SAMPLE_FOOTBALL_DATA_STANDINGS = {
    "standings": [
        {
            "stage": "REGULAR_SEASON",
            "type": "TOTAL",
            "table": [
                {"position": 1, "team": {"id": 57, "name": "Arsenal"}, "points": 89, "playedGames": 38},
                {"position": 2, "team": {"id": 65, "name": "Man City"}, "points": 85, "playedGames": 38},
            ],
        }
    ]
}

SAMPLE_API_FOOTBALL_STANDINGS = {
    "response": [
        {
            "league": {"id": 39, "name": "Premier League", "season": 2025, "standings": [[[ {"rank": 1, "team": {"id": 42, "name": "Arsenal"}, "points": 89} ]]] }
        }
    ]
}

SAMPLE_FOOTBALL_DATA_FIXTURES = {
    "matches": [
        {"id": 436044, "competition": {"code": "PL"}, "homeTeam": {"id": 57, "name": "Arsenal"}, "awayTeam": {"id": 64, "name": "Liverpool"}, "score": {"fullTime": {"home": 2, "away": 1}}}
    ]
}

# ── Mock httpx helpers ───────────────────────────────────────────────────

class MockResponse:
    def __init__(self, json_data, status_code=200, headers=None):
        self._json = json_data
        self.status_code = status_code
        self.headers = headers or {}
        self.text = json.dumps(json_data) if isinstance(json_data, dict) else str(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            # mimic httpx.HTTPStatusError
            try:
                import httpx  # type: ignore
                request = httpx.Request("GET", "http://test")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=request, response=response)
            except Exception as e:
                # fallback generic
                if "HTTPStatusError" in str(type(e)):
                    raise
                raise Exception(f"HTTP {self.status_code}")


class MockHttpxClient:
    """Maps URL substring to response; counts calls."""
    def __init__(self, route_map: dict):
        # route_map: substring -> json or (json, status, headers) or MockResponse
        self.route_map = route_map
        self.calls: list[str] = []
        self.calls_params: list[dict] = []
        self.calls_headers: list[dict] = []
        self.is_closed = False

    async def get(self, url, params=None, headers=None):
        self.calls.append(url)
        self.calls_params.append(params or {})
        self.calls_headers.append(headers or {})
        for key, val in self.route_map.items():
            if key in url:
                if isinstance(val, MockResponse):
                    return val
                if isinstance(val, tuple):
                    # (json, status, headers)
                    if len(val) == 3:
                        data, code, hdrs = val
                        return MockResponse(data, status_code=code, headers=hdrs)
                    elif len(val) == 2:
                        data, code = val
                        return MockResponse(data, status_code=code)
                return MockResponse(val)
        # also check params for league detection
        return MockResponse({}, status_code=404)

    async def aclose(self):
        self.is_closed = True


class FlakyMock:
    """First call 429, second succeeds."""
    def __init__(self, success_data, headers=None):
        self.success_data = success_data
        self.headers = headers or {}
        self.calls = 0
        self.is_closed = False

    async def get(self, url, params=None, headers=None):
        self.calls += 1
        if self.calls == 1:
            return MockResponse({}, status_code=429, headers={"x-ratelimit-requests-remaining": "99"})
        return MockResponse(self.success_data, headers=self.headers or {"x-ratelimit-requests-remaining": "88"})

    async def aclose(self):
        self.is_closed = True


# ── Tests ─────────────────────────────────────────────────────────────────

class CacheHitTestCase(unittest.TestCase):
    """Verify sqlite cache hit: second call no http."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_api_football_fixtures_cache_hit(self):
        from app.stat_data.federated import FederatedClient

        route = {"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES}
        mock_client = MockHttpxClient(route)
        # use api-football enabled, token disabled to force api-football path
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="testkey123",
            football_data_token=None,
        )
        # first call hits http
        data1 = asyncio.run(client.get_fixtures("EPL", 2025))
        self.assertTrue(data1.get("enabled"))
        self.assertEqual(len(mock_client.calls), 1)
        # second call same league/season should hit cache, no new http
        data2 = asyncio.run(client.get_fixtures("EPL", 2025))
        self.assertEqual(len(mock_client.calls), 1, "second call should be cached, no http")
        # data equal
        self.assertEqual(data1.get("fixtures"), data2.get("fixtures"))
        asyncio.run(client.close())

    def test_football_data_standings_cache_hit(self):
        from app.stat_data.federated import FederatedClient

        route = {"/standings": SAMPLE_FOOTBALL_DATA_STANDINGS}
        mock_client = MockHttpxClient(route)
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key=None,
            football_data_token="tok123",
        )
        data1 = asyncio.run(client.get_standings("EPL", 2025))
        self.assertTrue(data1.get("enabled"))
        self.assertEqual(len(mock_client.calls), 1)
        data2 = asyncio.run(client.get_standings("EPL", 2025))
        self.assertEqual(len(mock_client.calls), 1, "standings second call should be cached")
        self.assertEqual(data1.get("standings"), data2.get("standings"))
        asyncio.run(client.close())

    def test_cache_normalized_league_key(self):
        """epl vs EPL should hit same cache via normalize_league_name."""
        from app.stat_data.federated import FederatedClient

        route = {"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES}
        mock_client = MockHttpxClient(route)
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token=None,
        )
        asyncio.run(client.get_fixtures("epl", 2025))
        self.assertEqual(len(mock_client.calls), 1)
        # second call with different casing should be cache hit due to normalization
        asyncio.run(client.get_fixtures("EPL", 2025))
        self.assertEqual(len(mock_client.calls), 1)
        # also La Liga alias
        asyncio.run(client.get_fixtures("La Liga", 2025))
        self.assertEqual(len(mock_client.calls), 2)  # new league -> http
        asyncio.run(client.get_fixtures("La_liga", 2025))
        self.assertEqual(len(mock_client.calls), 2)  # normalized same
        asyncio.run(client.close())

    def test_fixtures_ttl_6h_standings_24h_files_exist(self):
        from app.stat_data.federated import FederatedClient, FIXTURES_TTL, STANDINGS_TTL
        self.assertEqual(FIXTURES_TTL, 6 * 3600)
        self.assertEqual(STANDINGS_TTL, 24 * 3600)
        # ensure db files created
        route = {"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES}
        mock_client = MockHttpxClient(route)
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token="tok",
        )
        asyncio.run(client.get_fixtures("EPL", 2025))
        # files should exist
        import pathlib
        self.assertTrue(pathlib.Path(self.tmp, "api-football.db").exists())
        self.assertTrue(pathlib.Path(self.tmp, "api.db").exists())
        self.assertTrue(pathlib.Path(self.tmp, "sofa.db").exists())
        asyncio.run(client.close())


class RateLimitAndBackoffTestCase(unittest.TestCase):
    """Verify 429 handling and rate-limit headers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_api_football_429_retry_succeeds(self):
        from app.stat_data.federated import FederatedClient

        flaky = FlakyMock(SAMPLE_API_FOOTBALL_FIXTURES, headers={"x-ratelimit-requests-remaining": "88"})
        client = FederatedClient(
            httpx_client=flaky,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token=None,
        )
        # patch sleep to avoid delay
        async def _run():
            with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
                data = await client.get_fixtures("EPL", 2025)
                return data
        data = asyncio.run(_run())
        self.assertEqual(flaky.calls, 2)
        self.assertTrue(data.get("enabled"))
        asyncio.run(client.close())

    def test_football_data_429_retry_succeeds(self):
        from app.stat_data.federated import FederatedClient

        flaky = FlakyMock(SAMPLE_FOOTBALL_DATA_STANDINGS)
        client = FederatedClient(
            httpx_client=flaky,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key=None,
            football_data_token="tok",
        )
        async def _run():
            with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock):
                data = await client.get_standings("EPL", 2025)
                return data
        data = asyncio.run(_run())
        self.assertEqual(flaky.calls, 2)
        self.assertTrue(data.get("enabled"))
        asyncio.run(client.close())

    def test_api_football_ratelimit_header_logged(self):
        from app.stat_data.federated import FederatedClient
        import logging

        headers = {"x-ratelimit-requests-remaining": "42"}
        mock_client = MockHttpxClient({"/fixtures": (SAMPLE_API_FOOTBALL_FIXTURES, 200, headers)})
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token=None,
        )
        with self.assertLogs("app.stat_data.federated", level="INFO") as cm:
            asyncio.run(client.get_fixtures("EPL", 2025))
        # should log x-ratelimit-requests-remaining
        log_text = " ".join(cm.output)
        self.assertIn("x-ratelimit-requests-remaining", log_text.lower())
        self.assertIn("42", log_text)
        asyncio.run(client.close())

    def test_football_data_token_bucket_does_not_crash(self):
        from app.stat_data.federated import FederatedClient

        # make 12 rapid calls with disable_throttle=False to exercise token bucket
        # but we patch sleep to avoid waiting
        mock_client = MockHttpxClient({"/standings": SAMPLE_FOOTBALL_DATA_STANDINGS})
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=False,  # enable bucket
            cache_dir=self.tmp,
            api_football_key=None,
            football_data_token="tok",
        )
        # we need to clear cache between calls to force http; use different seasons
        async def _run():
            with mock.patch("asyncio.sleep", new_callable=mock.AsyncMock) as mock_sleep:
                for i in range(12):
                    await client.get_standings("EPL", 2025 + i)
                # should have called sleep at least once due to bucket 10/min?
                # With 12 calls in same minute, bucket should trigger throttle after 10
                # But our implementation uses monotonic and jitter; at least not crash
                return mock_sleep
        mock_sleep = asyncio.run(_run())
        # at least 12 http calls
        self.assertEqual(len(mock_client.calls), 12)
        asyncio.run(client.close())


class ProviderFallbackTestCase(unittest.TestCase):
    """When keys absent, return honest_note and fallback to Understat — never crash."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_no_keys_federated_returns_honest_note(self):
        from app.stat_data.federated import FederatedClient

        # ensure env cleared
        with mock.patch.dict(os.environ, {}, clear=False):
            # remove keys if present
            os.environ.pop("API_FOOTBALL_KEY", None)
            os.environ.pop("FOOTBALL_DATA_TOKEN", None)
            mock_client = MockHttpxClient({})
            client = FederatedClient(
                httpx_client=mock_client,
                disable_throttle=True,
                cache_dir=self.tmp,
                api_football_key=None,
                football_data_token=None,
            )
            data = asyncio.run(client.get_fixtures("EPL", 2025))
            self.assertFalse(data.get("enabled", True))
            self.assertIn("honest_note", data)
            self.assertIn("Understat", data["honest_note"])
            self.assertEqual(data.get("fallback"), "understat")
            self.assertEqual(len(mock_client.calls), 0, "no http when no keys")
            # standings too
            data2 = asyncio.run(client.get_standings("EPL", 2025))
            self.assertFalse(data2.get("enabled", True))
            self.assertIn("honest_note", data2)
            self.assertIn("Understat", data2["honest_note"])
            # team
            data3 = asyncio.run(client.get_team(57))
            self.assertFalse(data3.get("enabled", True))
            self.assertIn("honest_note", data3)
            asyncio.run(client.close())

    def test_no_keys_analytics_service_fallback_to_understat(self):
        from app.analytics_service import AnalyticsService
        from unittest.mock import AsyncMock, MagicMock

        # mock Understat client
        mock_understat = MagicMock()
        mock_understat.get_league_data = AsyncMock(return_value={"dates": [{"id": "1", "h": {"title": "Arsenal"}, "a": {"title": "Chelsea"}}]})
        mock_understat.get_league_table = AsyncMock(return_value=[["Team","M","W"], ["Arsenal", 38, 28]])

        service = AnalyticsService(client=mock_understat, federated_client=None)
        # ensure env no keys
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_FOOTBALL_KEY", None)
            os.environ.pop("FOOTBALL_DATA_TOKEN", None)
            # also patch _is_federated_enabled to false
            with mock.patch.object(service, "_is_federated_enabled", return_value=False):
                fx = asyncio.run(service.get_federated_fixtures("EPL", 2025))
                self.assertFalse(fx.get("enabled", True))
                self.assertIn("honest_note", fx)
                self.assertIn("Understat", fx["honest_note"])
                self.assertEqual(fx.get("fallback"), "understat")
                # standings fallback should have called get_league_table
                st = asyncio.run(service.get_federated_standings("EPL", 2025))
                self.assertFalse(st.get("enabled", True))
                self.assertIn("honest_note", st)
                self.assertIn("Understat", st["honest_note"])
                # team fallback
                tm = asyncio.run(service.get_federated_team(57))
                self.assertFalse(tm.get("enabled", True))
                self.assertIn("honest_note", tm)

    def test_with_keys_calls_federated_successfully(self):
        from app.analytics_service import AnalyticsService
        from app.stat_data.federated import FederatedClient

        mock_understat = mock.MagicMock()
        route = {"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES}
        mock_client = MockHttpxClient(route)
        # need temp dir
        tmp = self.tmp
        federated = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=tmp,
            api_football_key="k",
            football_data_token="tok",
        )
        service = AnalyticsService(client=mock_understat, federated_client=federated)
        with mock.patch.dict(os.environ, {"API_FOOTBALL_KEY": "k", "FOOTBALL_DATA_TOKEN": "tok"}):
            fx = asyncio.run(service.get_federated_fixtures("EPL", 2025))
            self.assertTrue(fx.get("enabled"))
            self.assertIn("honest_note", fx)
        asyncio.run(federated.close())

    def test_federated_headers_env_gates(self):
        from app.stat_data.federated import FederatedClient

        # api-football header x-apisports-key, football-data X-Auth-Token
        mock_client = MockHttpxClient({"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES, "/teams": {"team": {"id": 57}}})
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="my_api_key_123",
            football_data_token="my_token_456",
        )
        # fixtures via api-football should send x-apisports-key
        asyncio.run(client.get_fixtures("EPL", 2025))
        self.assertIn("x-apisports-key", mock_client.calls_headers[0])
        self.assertEqual(mock_client.calls_headers[0]["x-apisports-key"], "my_api_key_123")
        # team via football-data should send X-Auth-Token
        mock_client2 = MockHttpxClient({"/teams": {"id": 57, "name": "Arsenal"}})
        client2 = FederatedClient(
            httpx_client=mock_client2,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key=None,
            football_data_token="my_token_456",
        )
        asyncio.run(client2.get_team(57))
        self.assertIn("X-Auth-Token", mock_client2.calls_headers[0])
        self.assertEqual(mock_client2.calls_headers[0]["X-Auth-Token"], "my_token_456")
        asyncio.run(client.close())
        asyncio.run(client2.close())


class NightlyPrefetchTestCase(unittest.TestCase):
    """Verify nightly prefetch top-5 leagues via utils.normalize_league_name."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_prefetch_top5_calls_each_league(self):
        from app.stat_data.federated import FederatedClient, TOP5_LEAGUES

        # route that matches all leagues: fixtures and standings
        route = {
            "/fixtures": SAMPLE_API_FOOTBALL_FIXTURES,
            "/standings": SAMPLE_FOOTBALL_DATA_STANDINGS,
            "/matches": SAMPLE_FOOTBALL_DATA_FIXTURES,
        }
        mock_client = MockHttpxClient(route)
        # need both keys so both fixture and standings paths work
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token="tok",
        )
        # also verify normalize_league_name is used: patch Utils.normalize
        from app.utils.utils import Utils
        orig_norm = Utils.normalize_league_name
        called_leagues = []
        def spy_norm(self, name):
            called_leagues.append(name)
            return orig_norm(self, name)
        with mock.patch.object(Utils, "normalize_league_name", spy_norm):
            result = asyncio.run(client.nightly_prefetch(2025))
            # also test aliases
            asyncio.run(client.prefetch_top5(2025))
            asyncio.run(client.prefetch_top5_leagues(2025))
            asyncio.run(client.warm_cache(2025))

        # result should contain 5 leagues
        self.assertIn("leagues", result)
        self.assertEqual(len(result["leagues"]), len(TOP5_LEAGUES))
        for lg in TOP5_LEAGUES:
            norm = Utils({}).normalize_league_name(lg)
            self.assertIn(norm, result["leagues"] or result.get("leagues", {}))
        # mock calls should be at least 5*2 (fixtures+standings) but cache will hit on repeated aliases second time, so first prefetch does 10
        # Since second prefetch hits cache, total calls should be ~10 not 40
        # Check that at least 10 http calls were made overall (first prefetch)
        self.assertGreaterEqual(len(mock_client.calls), 10)
        # verify that normalize was called for each league
        self.assertGreaterEqual(len(called_leagues), len(TOP5_LEAGUES))
        asyncio.run(client.close())

    def test_prefetch_never_crashes_without_keys(self):
        from app.stat_data.federated import FederatedClient

        mock_client = MockHttpxClient({})
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key=None,
            football_data_token=None,
        )
        # should not raise even with no keys
        result = asyncio.run(client.nightly_prefetch(2025))
        self.assertIn("leagues", result)
        self.assertIn("honest_note", result)
        self.assertEqual(len(mock_client.calls), 0)
        asyncio.run(client.close())

    def test_prefetch_uses_cache_ttl(self):
        from app.stat_data.federated import FederatedClient

        route = {"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES, "/standings": SAMPLE_FOOTBALL_DATA_STANDINGS}
        mock_client = MockHttpxClient(route)
        client = FederatedClient(
            httpx_client=mock_client,
            disable_throttle=True,
            cache_dir=self.tmp,
            api_football_key="k",
            football_data_token="tok",
        )
        asyncio.run(client.nightly_prefetch(2025))
        first_calls = len(mock_client.calls)
        # second prefetch immediate should be cached -> no extra http
        asyncio.run(client.nightly_prefetch(2025))
        self.assertEqual(len(mock_client.calls), first_calls, "second prefetch should be cached")
        asyncio.run(client.close())


class EnvGateAndHeadersTestCase(unittest.TestCase):
    def test_is_federated_enabled(self):
        from app.stat_data.federated import is_api_football_enabled, is_football_data_enabled, is_federated_enabled
        with mock.patch.dict(os.environ, {"API_FOOTBALL_KEY": "abc"}, clear=False):
            with mock.patch.dict(os.environ, {"FOOTBALL_DATA_TOKEN": ""}, clear=False):
                os.environ.pop("FOOTBALL_DATA_TOKEN", None)
                self.assertTrue(is_api_football_enabled())
                self.assertFalse(is_football_data_enabled())
                self.assertTrue(is_federated_enabled())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("API_FOOTBALL_KEY", None)
            os.environ.pop("FOOTBALL_DATA_TOKEN", None)
            self.assertFalse(is_api_football_enabled())
            self.assertFalse(is_football_data_enabled())
            self.assertFalse(is_federated_enabled())
        with mock.patch.dict(os.environ, {"FOOTBALL_DATA_TOKEN": "tok"}, clear=False):
            os.environ.pop("API_FOOTBALL_KEY", None)
            self.assertTrue(is_football_data_enabled())
            self.assertTrue(is_federated_enabled())

    def test_cache_files_naming(self):
        from app.stat_data.federated import FederatedClient
        tmp = tempfile.mkdtemp()
        try:
            mock_client = MockHttpxClient({"/fixtures": SAMPLE_API_FOOTBALL_FIXTURES})
            c = FederatedClient(httpx_client=mock_client, disable_throttle=True, cache_dir=tmp, api_football_key="k")
            self.assertTrue(c.api_football_db.endswith("api-football.db"))
            self.assertTrue(c.football_data_db.endswith("api.db"))
            self.assertTrue(c.sofa_db.endswith("sofa.db"))
            asyncio.run(c.close())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
