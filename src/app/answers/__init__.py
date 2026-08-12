from __future__ import annotations

from . import tables, teams, players, coaches


ANSWER_BUILDERS = {
    "league_table": tables.league_table,
    "league_overview": tables.league_overview,
    "team_xpts_gap": tables.team_xpts_gap,
    "process_vs_results": tables.process_vs_results,
    "overview": tables.overview,

    "team_compare": teams.team_compare,
    "team_overview": teams.team_overview,
    "team_recent_form": teams.team_recent_form,
    "team_window_compare": teams.team_window_compare,
    "team_defensive_trend": teams.team_defensive_trend,
    "team_chance_profile": teams.team_chance_profile,
    "team_player_ranking": teams.team_player_ranking,
    "team_attack_defense": teams.team_attack_defense,
    "team_position_trend": teams.team_position_trend,

    "player_overview": players.player_overview,
    "player_shots": players.player_shots,
    "player_compare": players.player_compare,
    "player_ranking": players.player_ranking,

    "coach_timeline": coaches.coach_timeline,
    "coach_compare": coaches.coach_compare,
}


def build_answer(plan, data) -> dict:
    builder = ANSWER_BUILDERS.get(plan.intent, tables.overview)
    return builder(plan, data)
