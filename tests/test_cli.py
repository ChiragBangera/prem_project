import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.cli import (
    parse_key_value_pairs,
    parse_param_value,
    render_ask_command,
    render_endpoint_details,
    render_templates,
    render_manchester_united_presets,
    render_visual_templates,
)
from app.endpoint_manifest import get_endpoint_manifest


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

    def test_render_visual_templates_splits_polished_from_rework(self):
        output = render_visual_templates()

        self.assertIn("Visual templates:", output)
        self.assertIn("Polished:", output)
        self.assertIn("coach_trend_insight_v1", output)
        self.assertIn("Rework:", output)
        self.assertIn("goalkeeper_variance_v1", output)

    @patch("app.cli.render_visualization_asset")
    @patch("app.cli.FootballQuestionAnswerer")
    def test_render_ask_command_writes_svg(self, mock_answerer_cls, mock_render):
        answerer = AsyncMock()
        answerer.__aenter__.return_value = answerer
        answerer.answer.return_value = {
            "answer": {
                "social_ready": {
                    "visualizations": {
                        "framework": "echarts",
                        "echarts_option": {"title": {"text": "Test"}},
                    }
                }
            }
        }
        mock_answerer_cls.return_value = answerer

        output = asyncio.run(render_ask_command("Show Arsenal chance creation by zone and type in 2025"))

        self.assertTrue(output.endswith(".svg"))
        self.assertTrue(mock_render.called)

    @patch("app.cli.render_visualization_asset_with_png")
    @patch("app.cli.FootballQuestionAnswerer")
    def test_render_ask_command_can_export_png(self, mock_answerer_cls, mock_render):
        answerer = AsyncMock()
        answerer.__aenter__.return_value = answerer
        answerer.answer.return_value = {
            "answer": {
                "social_ready": {
                    "visualizations": {
                        "framework": "echarts",
                        "echarts_option": {"title": {"text": "Test"}},
                    }
                }
            }
        }
        mock_answerer_cls.return_value = answerer
        mock_render.return_value = {"svg": "outputs/test.svg", "png": "outputs/test.png"}

        output = asyncio.run(render_ask_command("Test visual", export_png=True))

        self.assertEqual(output["png"], "outputs/test.png")
        self.assertTrue(mock_render.called)


if __name__ == "__main__":
    unittest.main()
