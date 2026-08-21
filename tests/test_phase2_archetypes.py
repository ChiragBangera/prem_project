"""Phase 2 — tactical archetype classification tests (docs/PHASE2_PLAN.md §3)."""

import unittest
from unittest import mock

from app.analytics.tactical import (
    archetype_report,
    classify,
    league_archetype_map,
    league_feature_stats,
    team_z,
)

HEADER = [
    "Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA", "NPxGA",
    "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS",
]


def make_row(name, m, xg, xga, npxgd, ppda, oppda, dc, pts=50):
    return [name, m, 10, 10, 5, 30, 30, pts, xg, xg * 0.9, xga, xga * 0.9, npxgd, ppda, oppda, dc, dc * 0.9, pts]


def make_table(teams):
    return [HEADER] + teams


# 19 baseline teams: league-average numbers.
BASE = lambda i: make_row(f"Mid{i:02d}", 38, 50.0, 50.0, 0.0, 11.5, 11.5, 380)  # noqa: E731


def base_table():
    return make_table([BASE(i) for i in range(19)])


class TacticalRulesTestCase(unittest.TestCase):
    def _table_with(self, row):
        return make_table([row] + [BASE(i) for i in range(19)])

    def test_control_team_classified(self):
        # City-like: huge DC/g, low xGA, low-ish PPDA.
        table = self._table_with(make_row("CityLike", 38, 85.0, 33.0, 46.0, 10.0, 12.5, 440))
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Control & Territory")

    def test_chaos_team_classified(self):
        table = self._table_with(make_row("ChaosFC", 38, 80.0, 75.0, -3.0, 11.5, 11.5, 370))
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Expansive / Chaos")

    def test_low_block_classified(self):
        # Deep block: high PPDA (little pressing), very low xGA.
        table = self._table_with(make_row("LowBlockUtd", 38, 42.0, 32.0, 8.0, 14.5, 11.0, 300))
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Low Block & Counter")

    def test_balanced_fallback(self):
        table = self._table_with(make_row("AverageFC", 38, 50.0, 50.0, 0.0, 11.5, 11.5, 380))
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Balanced Mid")
        self.assertEqual(report["confidence"], 0.5)

    def test_peers_sorted_by_distance(self):
        near = make_row("NearControl", 38, 84.0, 34.0, 45.0, 10.2, 12.4, 430)
        far = make_row("FarControl", 38, 70.0, 35.5, 28.0, 10.6, 12.6, 400)
        table = make_table(
            [make_row("Target", 38, 85.0, 33.0, 46.0, 10.0, 12.5, 440), near, far]
            + [BASE(i) for i in range(17)]
        )
        report = archetype_report(table[1], table)
        labels = [p["team"] for p in report["peers"]]
        self.assertIn("NearControl", labels)
        distances = [p["distance"] for p in report["peers"]]
        self.assertEqual(distances, sorted(distances))

    def test_confidence_bounds(self):
        z = {k: {"value": 0.0, "z": 0.0} for k in
             ("xg_per_game", "xga_per_game", "npxgd", "ppda", "oppda", "dc_per_game")}
        result = classify(z)
        self.assertGreaterEqual(result["confidence"], 0.0)
        self.assertLessEqual(result["confidence"], 1.0)

    def test_zero_matches_guarded(self):
        empty = make_row("NoMatches", 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
        table = self._table_with(empty)
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Balanced Mid")
        self.assertIn("Insufficient matches played.", report["honest_note"])

    def test_std_zero_guard(self):
        # All teams identical -> std=0 -> all z=0 -> no crash, balanced label.
        table = make_table([make_row(f"Same{i}", 38, 50.0, 50.0, 0.0, 11.5, 11.5, 380) for i in range(20)])
        stats = league_feature_stats(table)
        z = team_z(__import__("app.analytics.team", fromlist=["style_profile"]).style_profile(table[1]), stats)
        self.assertTrue(all(v["z"] == 0.0 for v in z.values()))
        report = archetype_report(table[1], table)
        self.assertEqual(report["label"], "Balanced Mid")


class AnalyticsWiringTestCase(unittest.TestCase):
    """Mock-client wiring tests following tests/test_phase0_understat_maxuse.py pattern."""

    def _mock_client(self, table):
        client = unittest.mock.MagicMock()

        async def _table(league_name="EPL", season=2025, with_headers=True, h_a="overall",
                         start_date=None, end_date=None):
            return table

        async def _history(team_name, season, league_name="EPL"):
            return []

        async def _league_data(league_name, season):
            return {"teams": {}, "dates": []}

        client.get_league_table = unittest.mock.AsyncMock(side_effect=_table)
        client.get_team_history = unittest.mock.AsyncMock(side_effect=_history)
        client.get_league_data = unittest.mock.AsyncMock(side_effect=_league_data)
        client.get_team_player_stats = unittest.mock.AsyncMock(return_value=[])
        client.get_team_results = unittest.mock.AsyncMock(return_value=[])
        return client

    def test_analyze_team_includes_archetype(self):
        import asyncio

        from app.analytics_service import AnalyticsService

        target = make_row("Arsenal", 38, 85.0, 33.0, 46.0, 10.0, 12.5, 440, pts=84)
        table = make_table([target] + [BASE(i) for i in range(19)])
        service = AnalyticsService(client=self._mock_client(table))
        report = asyncio.run(service.analyze_team("Arsenal", "EPL", season=2025))
        self.assertIsNotNone(report.get("archetype"))
        self.assertEqual(report["archetype"]["label"], "Control & Territory")
        self.assertIn("features", report["archetype"])
        self.assertIn("peers", report["archetype"])

    def test_analyze_league_includes_map(self):
        import asyncio

        from app.analytics_service import AnalyticsService

        table = make_table([make_row("CityLike", 38, 85.0, 33.0, 46.0, 10.0, 12.5, 440)]
                           + [BASE(i) for i in range(18)]
                           + [make_row("ChaosFC", 38, 80.0, 75.0, -3.0, 11.5, 11.5, 370)])
        service = AnalyticsService(client=self._mock_client(table))
        report = asyncio.run(service.analyze_league("EPL", 2025))
        arch = report["archetypes"]
        self.assertEqual(arch["by_team"]["CityLike"], "Control & Territory")
        self.assertEqual(arch["by_team"]["ChaosFC"], "Expansive / Chaos")
        self.assertEqual(arch["counts"].get("Control & Territory"), 1)
        self.assertIn("honest_note", arch)


if __name__ == "__main__":
    unittest.main()
