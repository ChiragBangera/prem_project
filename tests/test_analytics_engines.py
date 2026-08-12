import unittest

from app.analytics import league as league_engine
from app.analytics import match as match_engine
from app.analytics import percentiles
from app.analytics import player as player_engine
from app.analytics import team as team_engine


# ---------------------------------------------------------------- percentiles

class PercentilesTestCase(unittest.TestCase):
    def test_per90_normalizes_to_full_ninety_minutes(self):
        self.assertEqual(percentiles.per90(10, 90), 10.0)
        self.assertEqual(percentiles.per90(5, 45), 10.0)
        self.assertEqual(percentiles.per90(0, 900), 0.0)

    def test_per90_guards_non_positive_minutes(self):
        self.assertEqual(percentiles.per90(10, 0), 0.0)
        self.assertEqual(percentiles.per90(10, -90), 0.0)

    def test_percentile_rank_uses_average_rank_for_ties(self):
        # Two 10s tie at ranks 1 and 2 -> average rank 1.5 -> 25th percentile.
        self.assertEqual(percentiles.percentile_rank(10, [10, 10, 20]), 25.0)
        # Two 20s tie at ranks 3 and 4 -> average rank 3.5 -> 75th percentile.
        self.assertEqual(percentiles.percentile_rank(20, [10, 20, 20]), 75.0)

    def test_percentile_rank_edges(self):
        self.assertEqual(percentiles.percentile_rank(10, [10, 20, 30]), 0.0)
        self.assertEqual(percentiles.percentile_rank(30, [10, 20, 30]), 100.0)
        self.assertEqual(percentiles.percentile_rank(0, []), 50.0)

    def test_percentile_rank_caps_at_100_when_above_all_peers(self):
        # Value strictly above every peer used to blow past 100.
        self.assertEqual(percentiles.percentile_rank(2.0, [0.5, 1.0, 1.5]), 100.0)

    def test_position_group_maps_understat_codes(self):
        self.assertEqual(percentiles.position_group("F S"), "F")
        self.assertEqual(percentiles.position_group("D"), "D")
        self.assertEqual(percentiles.position_group("M"), "M")
        self.assertEqual(percentiles.position_group("GK"), "GK")
        self.assertEqual(percentiles.position_group("AM"), "M")
        self.assertEqual(percentiles.position_group("DC"), "D")
        self.assertEqual(percentiles.position_group("FW"), "F")

    def test_position_group_weird_inputs(self):
        self.assertEqual(percentiles.position_group(""), "")
        self.assertEqual(percentiles.position_group(None), "")
        self.assertEqual(percentiles.position_group("  D  "), "D")
        # Unrecognized head is returned uppercased rather than crashing.
        self.assertEqual(percentiles.position_group("Random Role"), "RANDOM")

    def test_filter_by_minutes_uses_time_threshold(self):
        rows = [
            {"player_name": "A", "time": "1200"},
            {"player_name": "B", "time": "800"},
            {"player_name": "C", "time": "900"},
        ]
        filtered = percentiles.filter_by_minutes(rows, 900)
        self.assertEqual([r["player_name"] for r in filtered], ["A", "C"])

    def test_filter_by_position_groups_rows(self):
        rows = [
            {"player_name": "Striker", "position": "F S"},
            {"player_name": "Defender", "position": "D"},
            {"player_name": "Midfielder", "position": "M"},
            {"player_name": "Keeper", "position": "GK"},
            {"player_name": "Unknown", "position": None},
        ]
        forwards = percentiles.filter_by_position(rows, "F")
        self.assertEqual([r["player_name"] for r in forwards], ["Striker"])
        all_rows = percentiles.filter_by_position(rows, "")
        self.assertEqual(len(all_rows), len(rows))

    def test_radar_profile_returns_sensible_percentiles_and_shape(self):
        player = {
            "id": "1", "time": "900", "goals": "20", "xG": "18", "assists": "4",
            "xA": "3", "shots": "40", "key_passes": "20", "xGChain": "50",
            "xGBuildup": "25", "npxG": "17",
        }
        peers = [
            {
                "id": "2", "time": "900", "goals": "2", "xG": "1", "assists": "0",
                "xA": "0", "shots": "5", "key_passes": "1", "xGChain": "4",
                "xGBuildup": "2", "npxG": "1",
            },
            {
                "id": "3", "time": "900", "goals": "3", "xG": "2", "assists": "1",
                "xA": "1", "shots": "6", "key_passes": "2", "xGChain": "5",
                "xGBuildup": "3", "npxG": "2",
            },
        ]
        profile = percentiles.radar_profile(player, peers)

        self.assertEqual(len(profile), len(percentiles.PLAYER_RADAR_METRICS))
        for entry in profile:
            self.assertIn("key", entry)
            self.assertIn("label", entry)
            self.assertIn("raw", entry)
            self.assertIn("per90", entry)
            self.assertIn("percentile", entry)
            self.assertIn("higher_is_better", entry)
            self.assertGreaterEqual(entry["percentile"], 0.0)
            self.assertLessEqual(entry["percentile"], 100.0)
            self.assertEqual(entry["per90"], percentiles.per90(
                percentiles.to_float(player.get(entry["key"], 0)), 900,
            ))
        # The clearly-best player should be at (or capped to) the 100th percentile.
        self.assertEqual([e["percentile"] for e in profile], [100.0] * len(profile))

    def test_radar_profile_ranks_best_player_at_100_with_player_in_peers(self):
        player = {
            "id": "1", "time": "900", "goals": "10", "xG": "9", "assists": "2",
            "xA": "1", "shots": "20", "key_passes": "8", "xGChain": "30",
            "xGBuildup": "15", "npxG": "8",
        }
        peers = [
            dict(player),
            {
                "id": "2", "time": "900", "goals": "1", "xG": "1", "assists": "0",
                "xA": "0", "shots": "3", "key_passes": "1", "xGChain": "4",
                "xGBuildup": "2", "npxG": "1",
            },
        ]
        profile = percentiles.radar_profile(player, peers)
        self.assertEqual([e["percentile"] for e in profile], [100.0] * len(profile))


# --------------------------------------------------------------------- player

class PlayerEnginesTestCase(unittest.TestCase):
    def _player(self, **overrides):
        base = {
            "id": "1", "player_name": "Bruno", "team_title": "Manchester United",
            "position": "F S", "time": "1800", "games": "20", "goals": "20",
            "xG": "18", "npxG": "17", "assists": "4", "xA": "3", "shots": "40",
            "key_passes": "20", "xGChain": "50", "xGBuildup": "25",
        }
        base.update(overrides)
        return base

    def test_per90_breakdown_normalizes_and_keeps_identity(self):
        breakdown = player_engine.per90_breakdown(self._player())

        self.assertEqual(breakdown["raw"]["goals"], 20.0)
        self.assertEqual(breakdown["per90"]["goals"], 1.0)
        self.assertEqual(breakdown["per90"]["xG"], 0.9)
        self.assertEqual(breakdown["per90"]["npxG"], 0.85)
        self.assertEqual(breakdown["per90"]["assists"], 0.2)
        self.assertEqual(breakdown["per90"]["xA"], 0.15)
        self.assertEqual(breakdown["per90"]["shots"], 2.0)
        self.assertEqual(breakdown["per90"]["key_passes"], 1.0)
        self.assertEqual(breakdown["per90"]["xGChain"], 2.5)
        self.assertEqual(breakdown["per90"]["xGBuildup"], 1.25)
        self.assertEqual(breakdown["games"], 20.0)
        self.assertEqual(breakdown["minutes"], 1800.0)
        self.assertEqual(breakdown["team_title"], "Manchester United")
        self.assertEqual(breakdown["position_group"], "F")

    def test_involvement_profile_buildup_share_of_chain(self):
        profile = player_engine.involvement_profile(self._player())
        self.assertEqual(profile["buildup_share_of_chain"], 0.5)
        self.assertEqual(profile["xGChain_per90"], 2.5)
        self.assertEqual(profile["xGBuildup_per90"], 1.25)

    def test_involvement_profile_none_branch_when_no_chain(self):
        profile = player_engine.involvement_profile(
            {"time": "900", "xGChain": "0", "xGBuildup": "5"}
        )
        self.assertIsNone(profile["buildup_share_of_chain"])
        self.assertEqual(profile["xGBuildup_per90"], 0.5)

    def test_shot_selection_profile_rates_quality_and_volume(self):
        profile = player_engine.shot_selection_profile(
            self._player(npg="17", npxG="16")
        )
        self.assertEqual(profile["shots"], 40.0)
        self.assertEqual(profile["shots_per90"], 2.0)
        self.assertEqual(profile["xG_per_shot"], 0.45)
        self.assertEqual(profile["npxG_per_shot"], 0.4)
        self.assertEqual(profile["penalty_shots"], 2.0)
        self.assertEqual(profile["non_penalty_goals"], 17.0)

    def test_finishing_overperformance_ci_present_when_shots_positive(self):
        result = player_engine.finishing_overperformance(
            {"goals": "22", "xG": "20.1", "npg": "21", "npxG": "19.0", "shots": "110"}
        )
        self.assertEqual(result["g_minus_xg"], 1.9)
        self.assertIsNotNone(result["g_minus_xg_std_error"])
        ci = result["g_minus_xg_ci95"]
        self.assertIsNotNone(ci)
        self.assertLessEqual(ci["low"], result["g_minus_xg"])
        self.assertGreaterEqual(ci["high"], result["g_minus_xg"])

    def test_finishing_overperformance_ci_none_when_no_shots(self):
        result = player_engine.finishing_overperformance(
            {"goals": "0", "xG": "0", "npg": "0", "npxG": "0", "shots": "0"}
        )
        self.assertEqual(result["g_minus_xg"], 0.0)
        self.assertIsNone(result["g_minus_xg_std_error"])
        self.assertIsNone(result["g_minus_xg_ci95"])

    def test_finishing_overperformance_sign(self):
        positive = player_engine.finishing_overperformance(
            {"goals": "5", "xG": "2", "npg": "4", "npxG": "1.5", "shots": "10"}
        )
        negative = player_engine.finishing_overperformance(
            {"goals": "1", "xG": "4", "npg": "1", "npxG": "3.5", "shots": "12"}
        )
        self.assertGreater(positive["g_minus_xg"], 0)
        self.assertLess(negative["g_minus_xg"], 0)

    def test_creative_dominance_is_share_of_team_xa(self):
        result = player_engine.creative_dominance(
            {"team_title": "Manchester United", "xA": "7.9"},
            [
                {"team_title": "Manchester United", "xA": "7.9"},
                {"team_title": "Manchester United", "xA": "4.2"},
                {"team_title": "Manchester United", "xA": "1.8"},
                {"team_title": "Arsenal", "xA": "20"},
            ],
        )
        self.assertEqual(result["team_xA"], 13.9)
        self.assertEqual(result["xA_share"], 0.568)
        self.assertEqual(result["player_xA"], 7.9)

    def test_creative_dominance_none_share_without_team_xa(self):
        result = player_engine.creative_dominance(
            {"team_title": "X", "xA": "2"},
            [{"team_title": "X", "xA": "0"}],
        )
        self.assertIsNone(result["xA_share"])

    def test_similar_players_excludes_target_and_ranks_clone_first(self):
        target = self._player(player_name="Target", position="M", goals="10", xG="9",
                              assists="8", xA="7", shots="30", key_passes="25",
                              xGChain="60", xGBuildup="30", npxG="8")
        clone = self._player(id="2", player_name="Clone", position="M", goals="10",
                             xG="9", assists="8", xA="7", shots="30",
                             key_passes="25", xGChain="60", xGBuildup="30", npxG="8")
        different = self._player(id="3", player_name="Diff", position="M",
                                 goals="0", xG="0", assists="0", xA="0", shots="0",
                                 key_passes="0", xGChain="0", xGBuildup="0", npxG="0")
        defender = self._player(id="4", player_name="Def", position="D",
                                goals="0", xG="0", assists="0", xA="0", shots="0",
                                key_passes="0", xGChain="0", xGBuildup="0", npxG="0")

        result = player_engine.similar_players(target, [target, clone, different, defender])

        self.assertEqual(result["target"], "Target")
        self.assertEqual(result["pool_after_filters"], 2)
        names = [m["player_name"] for m in result["matches"]]
        self.assertNotIn("Target", names)
        self.assertNotIn("Def", names)
        self.assertEqual(names[0], "Clone")
        self.assertEqual(result["matches"][0]["similarity"], 1.0)
        similarities = [m["similarity"] for m in result["matches"]]
        self.assertEqual(similarities, sorted(similarities, reverse=True))

    def test_player_report_smoke_returns_full_structure(self):
        player = self._player()
        peers = [player, self._player(id="9", player_name="Peer", goals="3", xG="2")]
        report = player_engine.player_report(player, peers, team_roster=peers)

        for key in (
            "player", "per90_breakdown", "involvement_profile", "shot_selection",
            "finishing_overperformance", "radar", "creative_dominance",
            "similar_players", "limitations",
        ):
            self.assertIn(key, report)
        self.assertEqual(report["player"]["name"], "Bruno")
        self.assertIsInstance(report["limitations"], list)


# ----------------------------------------------------------------------- team

class TeamEnginesTestCase(unittest.TestCase):
    # Real get_league_table column layout:
    # [Team, M, W, D, L, G, GA, PTS, xG, NPxG, xGA, NPxGA, NPxGD, PPDA, OPPDA, DC, ODC, xPTS]
    LIVERPOOL_ROW = [
        "Liverpool", 30, 20, 5, 5, 60, 25, 65, 58.2, 55.0, 26.1, 25.0, 30.0,
        10.2, 12.4, 300, 200, 58.3,
    ]

    def test_style_profile_reads_real_table_columns(self):
        style = team_engine.style_profile(self.LIVERPOOL_ROW)

        self.assertEqual(style["team"], "Liverpool")
        self.assertEqual(style["matches"], 30)
        self.assertEqual(style["xG_per_game"], 1.94)
        self.assertEqual(style["xGA_per_game"], 0.87)
        self.assertEqual(style["xG_diff_per_game"], 1.07)
        self.assertEqual(style["npxGD"], 30.0)
        self.assertEqual(style["PPDA"], 10.2)
        self.assertEqual(style["OPPDA"], 12.4)
        self.assertEqual(style["deep_completions"], 300)
        self.assertEqual(style["deep_completions_allowed"], 200)
        self.assertEqual(style["xPTS"], 58.3)

    def test_ppda_home_away_splits_by_side(self):
        history = [
            {"ppda": {"att": 100, "def": 10}, "h_a": "h"},
            {"ppda": {"att": 90, "def": 10}, "h_a": "a"},
            {"ppda": {"att": 80, "def": 20}, "h_a": "h"},
            {"ppda": {"att": 99, "def": 11}, "h_a": "a"},
        ]
        split = team_engine.ppda_home_away(history)

        self.assertEqual(split["ppda_home"], 7.0)
        self.assertEqual(split["ppda_away"], 9.0)
        self.assertEqual(split["matches_home"], 2)
        self.assertEqual(split["matches_away"], 2)

    def test_form_momentum_rolling_length_matches_input(self):
        history = [
            {"date": "2025-01-04", "xG": 1.8, "xGA": 0.6},
            {"date": "2025-01-11", "xG": 1.1, "xGA": 1.0},
            {"date": "2025-01-18", "xG": 2.3, "xGA": 0.9},
            {"date": "2025-01-25", "xG": 0.7, "xGA": 1.8},
            {"date": "2025-02-01", "xG": 1.9, "xGA": 0.7},
        ]
        result = team_engine.form_momentum(history)

        self.assertEqual(len(result["rolling_xgd"]), len(history))
        self.assertEqual(len(result["momentum"]), len(history))
        self.assertEqual([r["rolling_xGD"] for r in result["rolling_xgd"]],
                         [1.2, 0.65, 0.9, 0.4, 0.56])
        self.assertEqual(result["season_mean_xGD"], 0.56)
        self.assertEqual(result["recent_xGD"], 0.56)

    def test_form_momentum_is_a_running_cusum(self):
        history = [
            {"date": "2025-01-04", "xG": 1.8, "xGA": 0.6},
            {"date": "2025-01-11", "xG": 1.1, "xGA": 1.0},
            {"date": "2025-01-18", "xG": 2.3, "xGA": 0.9},
            {"date": "2025-01-25", "xG": 0.7, "xGA": 1.8},
            {"date": "2025-02-01", "xG": 1.9, "xGA": 0.7},
        ]
        result = team_engine.form_momentum(history)
        self.assertEqual([r["momentum"] for r in result["momentum"]],
                         [0.64, 0.18, 1.02, -0.64, 0.0])

    def test_form_momentum_empty_history(self):
        result = team_engine.form_momentum([])
        self.assertEqual(result["rolling_xgd"], [])
        self.assertEqual(result["momentum"], [])
        self.assertIsNone(result["season_mean_xGD"])
        self.assertIsNone(result["recent_xGD"])

    def test_situational_xg_share_ignores_opponent_shots(self):
        shots = [
            {"h_team": "Arsenal", "xG": 0.5, "situation": "OpenPlay"},
            {"h_team": "Arsenal", "xG": 0.3, "situation": "FromCorner"},
            {"h_team": "Arsenal", "xG": 0.2, "situation": "SetPiece"},
            {"h_team": "Opponent", "xG": 0.9, "situation": "OpenPlay"},
        ]
        result = team_engine.situational_xg_share(shots, "Arsenal")

        self.assertEqual(result["own_shots"], 3)
        self.assertEqual(result["by_situation"]["OpenPlay"], {"xG": 0.5, "share": 0.5})
        self.assertEqual(result["by_situation"]["FromCorner"], {"xG": 0.3, "share": 0.3})
        self.assertEqual(result["set_piece_xG_share"], 0.5)


# --------------------------------------------------------------------- league

class LeagueEnginesTestCase(unittest.TestCase):
    TABLE = [
        ["Team", "M", "W", "D", "L", "G", "GA", "PTS", "xG", "NPxG", "xGA",
         "NPxGA", "NPxGD", "PPDA", "OPPDA", "DC", "ODC", "xPTS"],
        ["Alpha", 30, 20, 5, 5, 60, 25, 65, 58.0, 55.0, 25.0, 24.0, 30.0,
         10.2, 12.4, 300, 200, 58.3],
        ["Beta", 30, 19, 6, 5, 55, 24, 63, 57.0, 54.0, 24.0, 23.0, 30.0,
         9.8, 11.9, 290, 210, 60.1],
        ["Gamma", 30, 14, 7, 9, 47, 38, 49, 49.0, 46.0, 36.0, 35.0, 10.0,
         11.2, 13.1, 255, 245, 48.7],
        ["Delta", 30, 12, 8, 10, 48, 40, 44, 50.0, 47.0, 38.0, 37.0, 10.0,
         11.0, 12.8, 250, 260, 50.8],
    ]

    def test_league_is_lying_sorts_rows_by_xpts_gap_desc(self):
        result = league_engine.league_is_lying(self.TABLE)

        gaps = [r["xPTS_gap"] for r in result["rows"]]
        self.assertEqual(gaps, sorted(gaps, reverse=True))
        self.assertEqual([r["team"] for r in result["rows"]],
                         ["Alpha", "Beta", "Gamma", "Delta"])
        self.assertEqual(result["biggest_overperformer"]["team"], "Alpha")
        self.assertEqual(result["biggest_underperformer"]["team"], "Delta")
        # Alpha: 65 pts - 58.3 xPTS.
        self.assertEqual(result["biggest_overperformer"]["xPTS_gap"], 6.7)

    def test_finishing_and_defensive_variance_stdev(self):
        result = league_engine.finishing_and_defensive_variance(self.TABLE)

        self.assertEqual(result["finishing_variance"]["mean_g_minus_xg"], -1.0)
        self.assertEqual(result["finishing_variance"]["stdev_g_minus_xg"], 2.0)
        self.assertEqual(result["defensive_variance"]["mean_xga_minus_ga"], -1.0)
        self.assertAlmostEqual(
            result["defensive_variance"]["stdev_xga_minus_ga"], 1.15, places=2,
        )

    def test_ppda_ranking_sorted_ascending(self):
        result = league_engine.ppda_ranking(self.TABLE)

        ppdas = [r["PPDA"] for r in result["ranking"]]
        self.assertEqual(ppdas, sorted(ppdas))
        self.assertEqual([r["team"] for r in result["ranking"]],
                         ["Beta", "Alpha", "Delta", "Gamma"])
        self.assertEqual(result["most_intense_press"]["team"], "Beta")
        self.assertEqual(result["least_intense_press"]["team"], "Gamma")

    def test_process_pace_league_averages(self):
        result = league_engine.process_pace(self.TABLE)

        self.assertEqual(result["matches"], 120)
        self.assertAlmostEqual(result["xG_per_game"], 1.78, places=2)
        self.assertAlmostEqual(result["xGA_per_game"], 1.02, places=2)

    def test_league_report_smoke(self):
        report = league_engine.league_report(self.TABLE)
        for key in ("is_lying", "variance", "ppda_ranking", "pace", "limitations"):
            self.assertIn(key, report)


# ---------------------------------------------------------------------- match

class MatchEnginesTestCase(unittest.TestCase):
    BASE_SHOT = {
        "h_team": "Arsenal", "a_team": "Chelsea", "situation": "OpenPlay",
        "shotType": "LeftFoot", "lastAction": "Pass", "player": "Somebody",
    }

    def _shot(self, minute, xg, result, **overrides):
        shot = dict(self.BASE_SHOT, minute=minute, xG=xg, result=result)
        shot.update(overrides)
        return shot

    def _base_shots(self):
        # Home out-xG'd but lost: h xG 0.7 vs a xG 0.8, scoreline 1-0.
        return {
            "h": [
                self._shot(55, "0.3", "Shot", X=0.6, Y=0.2),
                self._shot(12, "0.4", "Goal", X=0.8, Y=0.3),
            ],
            "a": [self._shot(30, "0.8", "Shot", X=0.2, Y=0.5)],
        }

    def test_calibration_sign_and_totals(self):
        result = match_engine.calibration(self._base_shots())

        self.assertEqual(result["xG"], {"h": 0.7, "a": 0.8})
        self.assertEqual(result["goals_from_shots"], {"h": 1, "a": 0})
        self.assertEqual(result["g_minus_xg"], {"h": 0.3, "a": -0.8})
        # Home outperformed xG (scored more than expected); away underperformed.
        self.assertGreater(result["g_minus_xg"]["h"], 0)
        self.assertLess(result["g_minus_xg"]["a"], 0)

    def test_big_chance_inventory_default_threshold(self):
        shots = {
            "h": [self._shot(10, "0.4", "Shot"), self._shot(20, "0.1", "Shot")],
            "a": [self._shot(30, "0.8", "Shot"), self._shot(40, "0.05", "Shot")],
        }
        result = match_engine.big_chance_inventory(shots)

        self.assertEqual(result["xG_threshold"], 0.20)
        self.assertEqual([s["xG"] for s in result["home"]], [0.4])
        self.assertEqual([s["xG"] for s in result["away"]], [0.8])

    def test_big_chance_inventory_custom_threshold(self):
        shots = {
            "h": [self._shot(10, "0.4", "Shot"), self._shot(20, "0.1", "Shot")],
            "a": [self._shot(30, "0.8", "Shot"), self._shot(40, "0.05", "Shot")],
        }
        result = match_engine.big_chance_inventory(shots, xg_threshold=0.5)

        self.assertEqual(result["xG_threshold"], 0.5)
        self.assertEqual(result["home"], [])
        self.assertEqual([s["xG"] for s in result["away"]], [0.8])

    def test_situation_breakdown_aggregates(self):
        shots = {
            "h": [
                self._shot(12, "0.4", "Goal"),
                self._shot(55, "0.3", "Shot", situation="FromCorner"),
            ],
            "a": [self._shot(30, "0.8", "Shot")],
        }
        result = match_engine.situation_breakdown(shots)

        self.assertEqual(result["home"]["OpenPlay"],
                         {"shots": 1, "xG": 0.4, "goals": 1})
        self.assertEqual(result["home"]["FromCorner"],
                         {"shots": 1, "xG": 0.3, "goals": 0})
        self.assertEqual(result["away"]["OpenPlay"],
                         {"shots": 1, "xG": 0.8, "goals": 0})

    def test_shot_map_normalizes_side_coordinates(self):
        result = match_engine.shot_map(self._base_shots())

        self.assertEqual(len(result["home"]), 2)
        self.assertEqual(len(result["away"]), 1)
        self.assertTrue(all(p["side"] == "h" for p in result["home"]))
        self.assertTrue(all(p["side"] == "a" for p in result["away"]))
        self.assertEqual(result["home"][1]["X"], 0.8)

    def test_xg_timeline_cumulative_sums_sorted_by_minute(self):
        result = match_engine.xg_timeline(self._base_shots())

        # Home shots are fed out of order; timeline must sort by minute.
        self.assertEqual([p["minute"] for p in result["home"]], [12, 55])
        self.assertEqual([p["cumulative_xG"] for p in result["home"]], [0.4, 0.7])
        self.assertEqual([p["cumulative_xG"] for p in result["away"]], [0.8])

    def test_match_narrative_out_xgd_but_lost_home(self):
        shots = {
            "h": [self._shot(10, "0.9", "Shot")],
            "a": [self._shot(20, "0.4", "Goal")],
        }
        narrative = match_engine.match_narrative(
            {"h": "Arsenal", "a": "Chelsea"}, shots,
        )["narrative"]
        self.assertIn("Arsenal out-xG'd Chelsea 0.90-0.40", narrative)
        self.assertIn("but lost on the scoreboard", narrative)

    def test_match_narrative_won_both_xg_and_scoreline(self):
        shots = {
            "h": [self._shot(10, "0.9", "Goal")],
            "a": [self._shot(20, "0.4", "Shot")],
        }
        narrative = match_engine.match_narrative(
            {"h": "Arsenal", "a": "Chelsea"}, shots,
        )["narrative"]
        self.assertIn("Arsenal won both xG (0.90-0.40) and the scoreline", narrative)

    def test_match_narrative_away_out_xgd_but_lost(self):
        shots = {
            "h": [self._shot(10, "0.4", "Goal")],
            "a": [self._shot(20, "0.9", "Shot")],
        }
        narrative = match_engine.match_narrative(
            {"h": "Arsenal", "a": "Chelsea"}, shots,
        )["narrative"]
        self.assertIn("Chelsea out-xG'd Arsenal 0.90-0.40", narrative)
        self.assertIn("but lost on the scoreboard", narrative)

    def test_match_narrative_away_won_both_xg_and_scoreline(self):
        shots = {
            "h": [self._shot(10, "0.4", "Shot")],
            "a": [self._shot(20, "0.9", "Goal")],
        }
        narrative = match_engine.match_narrative(
            {"h": "Arsenal", "a": "Chelsea"}, shots,
        )["narrative"]
        self.assertIn("Chelsea won both xG (0.90-0.40) and the scoreline", narrative)

    def test_match_narrative_default_branch(self):
        # xG tied, scoreline decisive -> falls through to the else branch.
        shots = {
            "h": [self._shot(10, "0.6", "Shot")],
            "a": [self._shot(20, "0.6", "Goal")],
        }
        narrative = match_engine.match_narrative(
            {"h": "Arsenal", "a": "Chelsea"}, shots,
        )["narrative"]
        self.assertIn("xG 0.60-0.60, decisive on the scoreboard", narrative)

    def test_match_report_smoke(self):
        report = match_engine.match_report(
            {"h": "Arsenal", "a": "Chelsea"}, self._base_shots(),
        )
        for key in ("calibration", "big_chance_inventory", "situation_breakdown",
                    "shot_map", "xg_timeline", "narrative", "limitations"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
