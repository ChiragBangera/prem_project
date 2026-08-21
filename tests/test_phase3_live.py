"""Phase 3 — live gameweek board tests (docs/PHASE3_PLAN.md)."""

import unittest
from unittest import mock

from app.analytics_service import AnalyticsService


def _match_row(mid, date, home, away, is_result, hg=None, ag=None, hxg=1.0, axg=0.8):
    return {
        "match_id": mid,
        "date": date,
        "home": home,
        "away": away,
        "is_result": is_result,
        "home_goals": hg,
        "away_goals": ag,
        "home_xg": hxg,
        "away_xg": axg,
    }


def _mock_client(dates):
    client = mock.MagicMock()

    async def _league_data(league_name, season):
        return {"dates": dates}

    client.get_league_data = mock.AsyncMock(side_effect=_league_data)
    return client


class MatchLiveTestCase(unittest.TestCase):
    def test_matches_live_shape_mixed_rounds(self):
        # Round 1 played (both matches), round 2 half-played, round 3 upcoming.
        dates = [
            {"id": 1, "h": {"title": "A"}, "a": {"title": "B"}, "datetime": "2025-08-10", "isResult": True,
             "goals": {"h": 2, "a": 0}, "xG": {"h": 1.5, "a": 0.7}},
            {"id": 2, "h": {"title": "C"}, "a": {"title": "D"}, "datetime": "2025-08-10", "isResult": True,
             "goals": {"h": 1, "a": 1}, "xG": {"h": 1.1, "a": 1.2}},
            {"id": 3, "h": {"title": "A"}, "a": {"title": "C"}, "datetime": "2025-08-17", "isResult": True,
             "goals": {"h": 0, "a": 3}, "xG": {"h": 0.5, "a": 2.0}},
            {"id": 4, "h": {"title": "B"}, "a": {"title": "D"}, "datetime": "2025-08-18", "isResult": False,
             "forecast": {"w": 0.4, "d": 0.3, "l": 0.3}},
            {"id": 5, "h": {"title": "A"}, "a": {"title": "D"}, "datetime": "2025-08-25", "isResult": False},
        ]
        service = AnalyticsService(client=_mock_client(dates))
        import asyncio

        live = asyncio.run(service.match_live("TestLeague", 2025))
        self.assertEqual(live["season_status"], "in-progress")
        self.assertEqual(live["n_played"], 3)
        self.assertEqual(live["n_upcoming"], 2)
        self.assertEqual(live["round_current"], 2)
        rounds = {r["round"]: r for r in live["rounds"]}
        self.assertTrue(all(r["complete"] for r in [rounds[1]]))
        self.assertFalse(rounds[2]["complete"] or rounds[3]["complete"])
        r1 = rounds[1]["matches"]
        self.assertTrue(all(m["isResult"] for m in r1))
        upcoming = [m for r in live["rounds"] for m in r["matches"] if not m["isResult"]]
        self.assertEqual(len(upcoming), 2)
        forecast = next((m["forecast"] for m in upcoming if m.get("forecast")), None)
        self.assertEqual(forecast, {"w": 0.4, "d": 0.3, "l": 0.3, "source": "understat"})
        # note honesty present
        self.assertIn("Understat updates post-match", live["note"])

    def test_matches_live_pre_season(self):
        dates = [
            {"id": 9, "h": {"title": "A"}, "a": {"title": "B"}, "datetime": "2026-08-15",
             "isResult": False, "forecast": {"w": 0.5, "d": 0.25, "l": 0.25}},
        ]
        service = AnalyticsService(client=_mock_client(dates))
        import asyncio

        live = asyncio.run(service.match_live("TestLeague", 2026))
        self.assertEqual(live["season_status"], "pre-season")
        self.assertEqual(live["round_current"], 1)
        self.assertEqual(live["rounds"][0]["matches"][0]["forecast"]["source"], "understat")

    def test_matches_live_complete_season(self):
        dates = [
            {"id": 1, "h": {"title": "A"}, "a": {"title": "B"}, "datetime": "2025-05-19", "isResult": True,
             "goals": {"h": 2, "a": 1}, "xG": {"h": 1.9, "a": 1.1}},
        ]
        service = AnalyticsService(client=_mock_client(dates))
        import asyncio

        live = asyncio.run(service.match_live("TestLeague", 2025))
        self.assertEqual(live["season_status"], "complete")
        self.assertEqual(live["n_upcoming"], 0)
        self.assertEqual(live["round_current"], 1)
        self.assertTrue(live["rounds"][0]["complete"])


if __name__ == "__main__":
    unittest.main()
