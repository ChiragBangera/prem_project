import unittest
from unittest.mock import patch

from app.cli import (
    parse_key_value_pairs,
    parse_param_value,
    render_endpoint_details,
    render_templates,
    render_manchester_united_presets,
)
from app.endpoint_manifest import get_endpoint_manifest
from app.errors import UnderstatRequestError


class CliTestCase(unittest.TestCase):
    def test_parse_param_value_understands_primitives(self):
        self.assertEqual(parse_param_value("2025"), 2025)
        self.assertEqual(parse_param_value("true"), True)
        self.assertEqual(parse_param_value('["FW", "AM"]'), ["FW", "AM"])

    def test_parse_param_value_splits_simple_csv_lists(self):
        self.assertEqual(parse_param_value("FW,AM"), ["FW", "AM"])

    def test_parse_key_value_pairs_builds_param_dict(self):
        params = parse_key_value_pairs(
            [
                'league_name="EPL"',
                "season=2025",
                "positions=FW,AM",
            ]
        )

        self.assertEqual(
            params,
            {
                "league_name": "EPL",
                "season": 2025,
                "positions": ["FW", "AM"],
            },
        )

    def test_manifest_contains_terminal_entrypoints(self):
        manifest = get_endpoint_manifest()
        self.assertIn("league_data", manifest)
        self.assertIn("team_player_stats", manifest)
        self.assertIn("match_shots", manifest)
        self.assertIn("search_players", manifest)

    def test_render_endpoint_details_includes_example(self):
        details = render_endpoint_details("league_data")
        self.assertIn("Endpoint: league_data", details)
        self.assertIn("Example:", details)

    def test_render_templates_and_presets(self):
        self.assertIn("Analytics templates:", render_templates())
        self.assertIn("Manchester United presets:", render_manchester_united_presets())

    @patch("app.cli._main", side_effect=UnderstatRequestError("Upstream unavailable"))
    @patch("app.cli.sys.stderr")
    def test_main_formats_expected_errors_without_traceback(self, stderr, _):
        from app.cli import main

        with self.assertRaises(SystemExit) as raised:
            main()

        self.assertEqual(raised.exception.code, 1)
        self.assertTrue(stderr.write.called)

if __name__ == "__main__":
    unittest.main()
