"""Phase 4 — Transfermarkt manual-import enrichment tests (docs/PHASE4_PLAN.md)."""

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.analytics.enrichment import (
    CsvEnrichmentProvider,
    NoopEnrichmentProvider,
    provider_from_env,
    upsert_player_rows,
)


def _write_db(path: Path) -> None:
    upsert_player_rows(
        path,
        [
            {
                "player_name": "Mohamed Salah",
                "team_hint": "Liverpool",
                "market_value_eur": 55000000,
                "contract_end": "2027-06-30",
                "foot": "Left",
                "height_cm": 175,
                "fetched_at": "2026-08-21",
            },
            {
                "player_name": "João Pedro",
                "team_hint": "Chelsea",
                "market_value_eur": 40000000,
                "contract_end": "2030-06-30",
                "foot": "Right",
                "height_cm": 185,
                "fetched_at": "2026-08-20",
            },
        ],
    )


class ImportAndProviderTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "enrichment.db"
        _write_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_parses_and_upserts(self):
        # Re-upsert same key updates value rather than duplicating.
        upsert_player_rows(
            self.db,
            [{"player_name": "Mohamed Salah", "team_hint": "Liverpool", "market_value_eur": 60000000,
              "fetched_at": "2026-09-01"}],
        )
        with sqlite3.connect(self.db) as conn:
            n, val = conn.execute(
                "SELECT COUNT(*), market_value_eur FROM players WHERE player_key LIKE 'mohamed salah::%'"
            ).fetchone()
        self.assertEqual(n, 1)
        self.assertEqual(val, 60000000)

    def test_provider_match_and_namesake_disambiguation(self):
        # Add a namesake at a different club.
        upsert_player_rows(
            self.db,
            [{"player_name": "João Pedro", "team_hint": "Brighton", "market_value_eur": 30000000,
              "fetched_at": "2026-08-21"}],
        )
        provider = CsvEnrichmentProvider(self.db)

        hit = asyncio.run(provider.enrich_player("mohamed  salah", "Liverpool"))
        self.assertEqual(hit.source, "transfermarkt-manual")
        self.assertEqual(hit.market_value_eur, 55000000)
        self.assertIn("manual Transfermarkt import dated 2026-08-21", hit.honest_note)

        chelsea = asyncio.run(provider.enrich_player("João Pedro", "Chelsea"))
        brighton = asyncio.run(provider.enrich_player("João Pedro", "Brighton"))
        self.assertEqual(chelsea.market_value_eur, 40000000)
        self.assertEqual(brighton.market_value_eur, 30000000)

        # Accent-folded + no team hint still resolves (most recent first).
        nohint = asyncio.run(provider.enrich_player("joao pedro"))
        self.assertIsNotNone(nohint.market_value_eur)

    def test_provider_miss_returns_none_fields(self):
        provider = CsvEnrichmentProvider(self.db)
        miss = asyncio.run(provider.enrich_player("Unknown Player"))
        self.assertEqual(miss.source, "none")
        self.assertIsNone(miss.market_value_eur)
        self.assertIsNone(miss.contract_end)


class WiringTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "enrichment.db"
        _write_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _mock_client(self):
        client = mock.MagicMock()

        async def _stats(league_name, season, start_date=None, end_date=None):
            return [
                {
                    "id": 1, "player_name": "Mohamed Salah", "team_title": "Liverpool",
                    "position": "FW", "games": "38", "time": "2700", "goals": "7", "xG": "8.8",
                    "npxG": "8.0", "npg": "6.5", "assists": "7", "xA": "6.4", "shots": "67",
                    "key_passes": "49", "xGChain": "17.4", "xGBuildup": "9.3",
                    "yellow_cards": "2", "red_cards": "0",
                }
            ]

        async def _shots(player_id):
            return []

        async def _player_data(player_id):
            return {"groups": {}, "player": {"favorite_position": "FW"}}

        client.get_league_player_stats = mock.AsyncMock(side_effect=_stats)
        client.get_player_shots = mock.AsyncMock(side_effect=_shots)
        client.get_player_data = mock.AsyncMock(side_effect=_player_data)
        client.search_players = mock.AsyncMock(return_value=[])
        return client

    def test_analyze_player_uses_provider(self):
        from app.analytics_service import AnalyticsService

        service = AnalyticsService(client=self._mock_client(), enrichment=CsvEnrichmentProvider(self.db))
        report = asyncio.run(service.analyze_player(player_name="Mohamed Salah", league_name="EPL", season=2025))
        enr = report.get("enrichment") or {}
        self.assertEqual(enr.get("source"), "transfermarkt-manual")
        self.assertEqual(enr.get("market_value_eur"), 55000000)
        self.assertEqual(enr.get("contract_end"), "2027-06-30")

    def test_lifespan_factory_noop_when_db_missing(self):
        import os

        old = os.environ.get("FOOTBALL_ENRICHMENT_DB")
        try:
            os.environ["FOOTBALL_ENRICHMENT_DB"] = str(Path(self.tmp.name) / "missing" / "nope.db")
            provider = provider_from_env()
            self.assertIsInstance(provider, NoopEnrichmentProvider)
        finally:
            if old is None:
                os.environ.pop("FOOTBALL_ENRICHMENT_DB", None)
            else:
                os.environ["FOOTBALL_ENRICHMENT_DB"] = old

    def test_lifespan_factory_csv_when_env_set(self):
        import os

        old = os.environ.get("FOOTBALL_ENRICHMENT_DB")
        try:
            os.environ["FOOTBALL_ENRICHMENT_DB"] = str(self.db)
            provider = provider_from_env()
            self.assertIsInstance(provider, CsvEnrichmentProvider)
        finally:
            if old is None:
                os.environ.pop("FOOTBALL_ENRICHMENT_DB", None)
            else:
                os.environ["FOOTBALL_ENRICHMENT_DB"] = old


if __name__ == "__main__":
    unittest.main()
