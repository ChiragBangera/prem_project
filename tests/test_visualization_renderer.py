import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.visualization_renderer import render_echarts_svg, render_svg_to_png, render_visualization_asset, slugify_filename


class VisualizationRendererTestCase(unittest.TestCase):
    def test_slugify_filename(self):
        self.assertEqual(slugify_filename("Arsenal chance profile 2025"), "arsenal-chance-profile-2025")

    @patch("app.visualization_renderer.subprocess.run")
    def test_render_echarts_svg_invokes_node_renderer(self, mock_run):
        payload = {
            "framework": "echarts",
            "echarts_option": {"title": {"text": "Test"}},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "chart.svg"
            returned = render_echarts_svg(payload, output)

        self.assertEqual(returned, output)
        self.assertTrue(mock_run.called)

    @patch("app.visualization_renderer.subprocess.run")
    def test_render_svg_to_png_invokes_node_converter(self, mock_run):
        with tempfile.TemporaryDirectory() as temp_dir:
            svg_path = Path(temp_dir) / "chart.svg"
            svg_path.write_text("<svg />", encoding="utf-8")
            returned = render_svg_to_png(svg_path)

        self.assertEqual(returned, svg_path.with_suffix(".png"))
        self.assertTrue(mock_run.called)

    def test_render_visualization_asset_supports_custom_svg_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "premium_team_compare_v1",
            "title": "Manchester United vs Arsenal",
            "headline": "Arsenal have the stronger recent league form",
            "subtitle": "Last 5 league matches | points, W-D-L, goals, xG, xGA",
            "footer": "Data source: Understat",
            "stat_lines": [
                "Arsenal have taken 13 points from the last five league matches.",
                "United have taken 10 points from the same five-match window.",
            ],
            "teams": [
                {
                    "name": "Manchester United",
                    "short_name": "MUN",
                    "accent": "#C8102E",
                    "accent_soft": "#F59E0B",
                    "points": "10",
                    "record": "3-1-1",
                    "results": ["W", "D", "W", "W", "L"],
                    "summary": "3-1-1 | 10 pts",
                    "metrics": [
                        {"label": "Goals Scored", "value": "9", "ratio": 0.82},
                        {"label": "Goals Conceded", "value": "6", "ratio": 1.0},
                    ],
                },
                {
                    "name": "Arsenal",
                    "short_name": "ARS",
                    "accent": "#EF4444",
                    "accent_soft": "#3B82F6",
                    "points": "13",
                    "record": "4-1-0",
                    "results": ["W", "W", "D", "W", "W"],
                    "summary": "4-1-0 | 13 pts",
                    "metrics": [
                        {"label": "Goals Scored", "value": "11", "ratio": 1.0},
                        {"label": "Goals Conceded", "value": "4", "ratio": 0.67},
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "custom.svg"
            returned = render_visualization_asset(payload, output)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("FORM CHECK", svg_text)
        self.assertIn("Manchester United", svg_text)
        self.assertIn("Arsenal", svg_text)
        self.assertIn("Goals Scored", svg_text)

    def test_render_visualization_asset_supports_player_distribution_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "player_distribution_compare_v1",
            "title": "Chance creation distribution",
            "headline": "Amorim spread the burden. Carrick centralised it around Bruno.",
            "subtitle": "Manchester United attacking distribution by coach window",
            "kicker": "PLAYER LOAD MAP",
            "footer": "Data source: Understat",
            "highlight_names": ["Bruno Fernandes", "Casemiro", "Kobbie Mainoo"],
            "stat_lines": [
                "Bruno's xA share jumped from 20.8% to 54.3%.",
                "Top three creators jumped from 44.8% to 75.9% of team xA.",
            ],
            "left_window": {
                "label": "Ruben Amorim",
                "sublabel": "20 league matches",
                "palette": {"accent": "#C8102E", "accent_soft": "#F59E0B"},
                "totals": {"xA": 25.36, "xG": 40.73, "shots": 321},
                "summary_lines": ["Bruno xA share: 20.8%", "Top 3 xA share: 44.8%"],
                "rows": [
                    {"player_name": "Bruno Fernandes", "xA_share": 0.208, "xGxA_share": 0.197, "xA": 5.28, "xGxA": 13.02, "shots": 46, "minutes": 1489, "goals": 5},
                    {"player_name": "Amad Diallo Traore", "xA_share": 0.122, "xGxA_share": 0.101, "xA": 3.1, "xGxA": 6.65, "shots": 29, "minutes": 1212, "goals": 2},
                ],
            },
            "right_window": {
                "label": "Michael Carrick",
                "sublabel": "10 league matches",
                "palette": {"accent": "#F59E0B", "accent_soft": "#38BDF8"},
                "totals": {"xA": 12.68, "xG": 17.57, "shots": 141},
                "summary_lines": ["Bruno xA share: 54.3%", "Top 3 xA share: 75.9%"],
                "rows": [
                    {"player_name": "Bruno Fernandes", "xA_share": 0.543, "xGxA_share": 0.330, "xA": 6.88, "xGxA": 9.99, "shots": 26, "minutes": 900, "goals": 3},
                    {"player_name": "Casemiro", "xA_share": 0.052, "xGxA_share": 0.102, "xA": 0.66, "xGxA": 3.08, "shots": 13, "minutes": 854, "goals": 3},
                ],
            },
            "focus_rows": [
                {
                    "player_name": "Kobbie Mainoo",
                    "left": {"xA": 0.27, "xGxA": 0.33, "shots": 2, "minutes": 174},
                    "right": {"xA": 0.33, "xGxA": 0.44, "shots": 5, "minutes": 895},
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "distribution.svg"
            returned = render_visualization_asset(payload, output, width=1900, height=2860)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("PLAYER LOAD MAP", svg_text)
        self.assertIn("Bruno Fernandes", svg_text)
        self.assertIn("Kobbie Mainoo", svg_text)
        self.assertIn("Michael Carrick", svg_text)

    def test_render_visualization_asset_supports_prematch_matchup_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "prematch_matchup_v1",
            "title": "Manchester United vs Leeds United",
            "kicker": "MATCHUP",
            "headline": "Old Trafford edge favors United",
            "subtitle": "Manchester United vs Leeds United | Monday, April 13, 2026",
            "footer": "Data source: Understat",
            "stat_lines": [
                "United have 33 home points from 15 matches.",
                "Leeds have taken only 10 away points from 15 matches.",
            ],
            "focus_players": [
                {"name": "Bruno Fernandes", "note": "13.04 xA | 11.16 xG"},
                {"name": "Dominic Calvert-Lewin", "note": "Leeds leader on 13.04 xG"},
            ],
            "teams": [
                {
                    "name": "Manchester United",
                    "short_name": "MUN",
                    "accent": "#C8102E",
                    "accent_soft": "#F59E0B",
                    "context_label": "HOME SPLIT",
                    "points": "33",
                    "venue_record": "10-3-2",
                    "recent_record": "3-1-1",
                    "recent_sequence": ["W", "W", "L", "W", "D"],
                    "player_note": "Bruno: 13.04 xA | 11.16 xG",
                    "metrics": [
                        {"label": "xG", "value": "31.58", "ratio": 1.0},
                        {"label": "xGA", "value": "15.40", "ratio": 0.61},
                        {"label": "NPxGD", "value": "15.42", "ratio": 1.0},
                        {"label": "xPTS", "value": "31.16", "ratio": 1.0},
                    ],
                },
                {
                    "name": "Leeds United",
                    "short_name": "LEE",
                    "accent": "#1D4ED8",
                    "accent_soft": "#FACC15",
                    "context_label": "AWAY SPLIT",
                    "points": "10",
                    "venue_record": "1-7-7",
                    "recent_record": "0-3-2",
                    "recent_sequence": ["D", "L", "L", "D", "D"],
                    "player_note": "DCL: 13.04 xG | Stach: 5.74 xA",
                    "metrics": [
                        {"label": "xG", "value": "18.44", "ratio": 0.58},
                        {"label": "xGA", "value": "25.44", "ratio": 1.0},
                        {"label": "NPxGD", "value": "-7.15", "ratio": 0.1},
                        {"label": "xPTS", "value": "16.92", "ratio": 0.54},
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "prematch.svg"
            returned = render_visualization_asset(payload, output)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("Old Trafford edge favors", svg_text)
        self.assertIn("United", svg_text)
        self.assertIn("Manchester United", svg_text)
        self.assertIn("Leeds United", svg_text)
        self.assertIn("WHY UNITED ARE FAVORED", svg_text)

    def test_render_visualization_asset_supports_coach_trend_insight_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "coach_trend_insight_v1",
            "title": "Manchester United open-play xG by coach",
            "kicker": "TACTICAL TREND",
            "headline": "Carrick's open-play attack is sliding",
            "subtitle": "Manchester United | EPL 2025/26",
            "verdict": "Amorim held a higher open-play level. Carrick starts lower and trends down.",
            "footer": "Data source: Understat",
            "min_value": 0,
            "max_value": 3.2,
            "latest_match": {
                "label": "Latest: Leeds H",
                "value": "0.66 open-play xG",
                "note": "below Carrick average",
            },
            "annotations": [
                {"match_index": 1, "value": 1.2, "label": "Arsenal H", "sublabel": "1.20 xG"},
                {"match_index": 6, "value": 0.7, "label": "Leeds H", "sublabel": "latest"},
            ],
            "windows": [
                {
                    "label": "Amorim",
                    "matches": "20",
                    "average": "1.54",
                    "slope_label": "-0.000/match",
                    "note": "Higher, stable level",
                    "points": [
                        {"match_index": 1, "value": 1.2},
                        {"match_index": 2, "value": 1.5},
                        {"match_index": 3, "value": 1.4},
                    ],
                    "slope_points": [
                        {"match_index": 1, "value": 1.36},
                        {"match_index": 3, "value": 1.36},
                    ],
                },
                {
                    "label": "Carrick",
                    "matches": "11",
                    "average": "1.23",
                    "slope_label": "-0.085/match",
                    "note": "Lower and falling",
                    "points": [
                        {"match_index": 4, "value": 2.6},
                        {"match_index": 5, "value": 1.3},
                        {"match_index": 6, "value": 0.7},
                    ],
                    "slope_points": [
                        {"match_index": 4, "value": 2.2},
                        {"match_index": 6, "value": 1.0},
                    ],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "coach-trend.svg"
            returned = render_visualization_asset(payload, output)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("TACTICAL TREND", svg_text)
        self.assertIn("Carrick", svg_text)
        self.assertIn("Latest: Leeds H", svg_text)
        self.assertIn("Arsenal H", svg_text)
        self.assertIn("OPEN-PLAY xG PER MATCH", svg_text)

    def test_render_visualization_asset_supports_process_vs_results_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "process_vs_results_lens_v1",
            "title": "EPL: process vs results",
            "kicker": "PROCESS VS RESULTS",
            "headline": "Results are not always process",
            "subtitle": "EPL 2025: points vs xPTS, finishing, defensive variance",
            "footer": "Data source: Understat",
            "categories": ["Aston Villa", "Arsenal", "Wolves"],
            "metric_series": {
                "points_minus_xpts": [13.38, 3.2, -12.24],
                "goals_minus_xg": [1.4, -2.1, -6.8],
                "xga_minus_goals_against": [4.1, 8.2, -1.3],
            },
            "rankings": {
                "points_overperformer": {"team": "Aston Villa", "points_gap": 13.38},
                "points_underperformer": {"team": "Wolves", "points_gap": -12.24},
                "finishing_overperformer": {"team": "Tottenham", "finishing_gap": 2.37},
                "finishing_underperformer": {"team": "Crystal Palace", "finishing_gap": -19.23},
                "defensive_overperformer": {"team": "Everton", "defensive_prevention_gap": 11.6},
                "defensive_underperformer": {"team": "Leeds", "defensive_prevention_gap": -1.56},
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "process.svg"
            returned = render_visualization_asset(payload, output)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("PROCESS VS RESULTS", svg_text)
        self.assertIn("FULL LEAGUE VARIANCE TABLE", svg_text)
        self.assertIn("Aston Villa", svg_text)
        self.assertIn("POINTS - xPTS", svg_text)

    def test_render_visualization_asset_supports_goalkeeper_variance_template(self):
        payload = {
            "framework": "custom_svg",
            "render_mode": "custom_svg",
            "template": "goalkeeper_variance_v1",
            "title": "Premier League keeper variance",
            "kicker": "KEEPER VARIANCE",
            "headline": "Martinez is carrying Villa's variance",
            "subtitle": "EPL 2025/26 | starts, xGA, goals conceded, xPTS",
            "footer": "Data source: Understat",
            "focus": {
                "player": "Emiliano Martinez",
                "team": "Aston Villa",
                "starts": 29,
                "record": "15-5-9",
                "xga_minus_ga": 9.83,
                "pts_minus_xpts": 10.51,
                "ga": 33,
                "xga": 42.83,
            },
            "rows": [
                {
                    "rank": 1,
                    "player": "Jordan Pickford",
                    "team": "Everton",
                    "starts": 34,
                    "xga_minus_ga": 11.6,
                    "pts_minus_xpts": 4.87,
                    "ga": 41,
                    "xga": 52.6,
                },
                {
                    "rank": 2,
                    "player": "Emiliano Martinez",
                    "team": "Aston Villa",
                    "starts": 29,
                    "xga_minus_ga": 9.83,
                    "pts_minus_xpts": 10.51,
                    "ga": 33,
                    "xga": 42.83,
                },
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "keepers.svg"
            returned = render_visualization_asset(payload, output)
            svg_text = output.read_text(encoding="utf-8")

        self.assertEqual(returned, output)
        self.assertIn("KEEPER VARIANCE", svg_text)
        self.assertIn("Emiliano Martinez", svg_text)
        self.assertIn("xGA - GA", svg_text)


if __name__ == "__main__":
    unittest.main()
