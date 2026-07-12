import unittest

from app.utils import Utils


class UtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.utils = Utils({"X-Requested-With": "XMLHttpRequest"})

    def test_normalize_league_name_maps_common_aliases(self):
        self.assertEqual(self.utils.normalize_league_name("epl"), "EPL")
        self.assertEqual(self.utils.normalize_league_name("la liga"), "La_liga")
        self.assertEqual(self.utils.normalize_league_name("Serie A"), "Serie_A")

    def test_filter_data_filters_lists(self):
        data = [
            {"player_name": "Bruno Fernandes", "team_title": "Manchester United"},
            {"player_name": "Bukayo Saka", "team_title": "Arsenal"},
        ]

        filtered = self.utils.filter_data(data, {"team_title": "Arsenal"})

        self.assertEqual(filtered, [data[1]])

    def test_filter_by_date_uses_full_day_boundaries(self):
        data = [
            {"date": "2025-08-10 15:00:00"},
            {"date": "2025-09-02 20:00:00"},
            {"date": "2025-10-01 18:00:00"},
        ]

        filtered = self.utils.filter_by_date(
            data,
            season=2025,
            start="2025-09-01",
            end="2025-09-30",
        )

        self.assertEqual(filtered, [data[1]])

    def test_build_datetime_range_validates_input(self):
        date_range = self.utils.build_datetime_range(
            start_date="2025-01-01",
            end_date="2025-01-31",
        )

        self.assertEqual(
            date_range,
            {
                "date_start": "2025-01-01 00:00:00",
                "date_end": "2025-01-31 23:59:59",
            },
        )

    def test_filter_by_positions_matches_original_package_shape(self):
        stats = {
            "FW": {"goals": {"avg": 0.6}},
            "AM": {"goals": {"avg": 0.2}},
        }

        filtered = self.utils.filter_by_positions(stats, ["FW"])

        self.assertEqual(
            filtered,
            [{"goals": {"avg": 0.6}, "position": "FW"}],
        )


if __name__ == "__main__":
    unittest.main()
