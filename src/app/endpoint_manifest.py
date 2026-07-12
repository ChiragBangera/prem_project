from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    method_name: str
    category: str
    description: str
    required_params: tuple[str, ...] = ()
    optional_params: tuple[str, ...] = ()
    example: str = ""


ENDPOINT_MANIFEST = {
    "stats": EndpointSpec(
        name="stats",
        method_name="get_stats",
        category="global",
        description="Global monthly league stats from Understat home page.",
        optional_params=("options",),
        example="run stats",
    ),
    "league_data": EndpointSpec(
        name="league_data",
        method_name="get_league_data",
        category="league",
        description="Raw JSON payload for a league season page.",
        required_params=("league_name", "season"),
        example='run league_data league_name="EPL" season=2025',
    ),
    "teams": EndpointSpec(
        name="teams",
        method_name="get_teams",
        category="league",
        description="League teams list extracted from league data.",
        required_params=("league_name", "season"),
        optional_params=("options",),
        example='run teams league_name="EPL" season=2025',
    ),
    "league_players": EndpointSpec(
        name="league_players",
        method_name="get_league_players",
        category="league",
        description="League player table for a season.",
        required_params=("league_name", "season"),
        optional_params=("options",),
        example='run league_players league_name="EPL" season=2025',
    ),
    "league_results": EndpointSpec(
        name="league_results",
        method_name="get_league_results",
        category="league",
        description="Completed league matches only.",
        required_params=("league_name", "season"),
        optional_params=("options",),
        example='run league_results league_name="EPL" season=2025',
    ),
    "league_fixtures": EndpointSpec(
        name="league_fixtures",
        method_name="get_league_fixtures",
        category="league",
        description="Upcoming league fixtures only.",
        required_params=("league_name", "season"),
        optional_params=("options",),
        example='run league_fixtures league_name="EPL" season=2025',
    ),
    "league_table": EndpointSpec(
        name="league_table",
        method_name="get_league_table",
        category="league",
        description="Derived league table with xG and PPDA style metrics.",
        required_params=("league_name", "season"),
        optional_params=("with_headers", "h_a", "start_date", "end_date"),
        example='run league_table league_name="EPL" season=2025',
    ),
    "league_player_stats": EndpointSpec(
        name="league_player_stats",
        method_name="get_league_player_stats",
        category="league",
        description="Filtered player-table POST endpoint for league pages.",
        required_params=("league_name", "season"),
        optional_params=("start_date", "end_date"),
        example='run league_player_stats league_name="EPL" season=2025 start_date="2025-08-01"',
    ),
    "team_data": EndpointSpec(
        name="team_data",
        method_name="get_team_data_by_season",
        category="team",
        description="Raw JSON payload for a team season page.",
        required_params=("team_name", "season"),
        example='run team_data team_name="Manchester United" season=2025',
    ),
    "team_data_by_year": EndpointSpec(
        name="team_data_by_year",
        method_name="get_team_data_by_year",
        category="team",
        description="Backward-compatible alias for team season data.",
        required_params=("team_name", "year"),
        example='run team_data_by_year team_name="Manchester United" year=2025',
    ),
    "team_stats": EndpointSpec(
        name="team_stats",
        method_name="get_team_stats",
        category="team",
        description="Team-level aggregate stats.",
        required_params=("team_name", "season"),
        example='run team_stats team_name="Manchester United" season=2025',
    ),
    "team_results": EndpointSpec(
        name="team_results",
        method_name="get_team_results",
        category="team",
        description="Completed matches for a team season.",
        required_params=("team_name", "season"),
        optional_params=("options",),
        example='run team_results team_name="Manchester United" season=2025',
    ),
    "team_fixtures": EndpointSpec(
        name="team_fixtures",
        method_name="get_team_fixtures",
        category="team",
        description="Upcoming fixtures for a team season.",
        required_params=("team_name", "season"),
        optional_params=("options",),
        example='run team_fixtures team_name="Manchester United" season=2025',
    ),
    "team_players": EndpointSpec(
        name="team_players",
        method_name="get_team_players",
        category="team",
        description="Team player table for a season.",
        required_params=("team_name", "season"),
        optional_params=("options",),
        example='run team_players team_name="Manchester United" season=2025',
    ),
    "team_player_stats": EndpointSpec(
        name="team_player_stats",
        method_name="get_team_player_stats",
        category="team",
        description="Filtered player-table POST endpoint for team pages.",
        required_params=("team_name", "season"),
        optional_params=("start_date", "end_date"),
        example='run team_player_stats team_name="Manchester United" season=2025 start_date="2025-08-01"',
    ),
    "player_data": EndpointSpec(
        name="player_data",
        method_name="get_player_data",
        category="player",
        description="Raw JSON payload for a player page.",
        required_params=("player_id",),
        example="run player_data player_id=565",
    ),
    "player_shots": EndpointSpec(
        name="player_shots",
        method_name="get_player_shots",
        category="player",
        description="Player shot map data.",
        required_params=("player_id",),
        optional_params=("options",),
        example="run player_shots player_id=565",
    ),
    "player_matches": EndpointSpec(
        name="player_matches",
        method_name="get_player_matches",
        category="player",
        description="Player match log data.",
        required_params=("player_id",),
        optional_params=("options",),
        example="run player_matches player_id=565",
    ),
    "player_matches_via_ajax": EndpointSpec(
        name="player_matches_via_ajax",
        method_name="get_player_matches_via_ajax",
        category="player",
        description="Player match log fetched from the extra AJAX endpoint used on player compare UI.",
        required_params=("player_id",),
        example="run player_matches_via_ajax player_id=565",
    ),
    "player_last_match": EndpointSpec(
        name="player_last_match",
        method_name="get_player_last_match",
        category="player",
        description="Last match object returned by the extra player compare AJAX endpoint.",
        required_params=("player_id",),
        example="run player_last_match player_id=565",
    ),
    "player_stats": EndpointSpec(
        name="player_stats",
        method_name="get_player_stats",
        category="player",
        description="Per-position min/max player stats.",
        required_params=("player_id",),
        optional_params=("positions",),
        example='run player_stats player_id=565 positions=["FW"]',
    ),
    "player_grouped_stats": EndpointSpec(
        name="player_grouped_stats",
        method_name="get_player_grouped_stats",
        category="player",
        description="Grouped player stats blocks from Understat.",
        required_params=("player_id",),
        example="run player_grouped_stats player_id=565",
    ),
    "search_players": EndpointSpec(
        name="search_players",
        method_name="search_players",
        category="search",
        description="Live player search endpoint used by the Understat header search box.",
        required_params=("query",),
        example='run search_players query="haaland"',
    ),
    "match_data": EndpointSpec(
        name="match_data",
        method_name="get_match_data",
        category="match",
        description="Raw JSON payload for a match page.",
        required_params=("match_id",),
        example="run match_data match_id=11652",
    ),
    "match_players": EndpointSpec(
        name="match_players",
        method_name="get_match_players",
        category="match",
        description="Match rosters payload.",
        required_params=("match_id",),
        optional_params=("options",),
        example="run match_players match_id=11652",
    ),
    "match_shots": EndpointSpec(
        name="match_shots",
        method_name="get_match_shots",
        category="match",
        description="Match shot map payload.",
        required_params=("match_id",),
        optional_params=("options",),
        example="run match_shots match_id=11652",
    ),
}


def get_endpoint_manifest():
    return ENDPOINT_MANIFEST


def get_endpoint_spec(endpoint_name: str):
    try:
        return ENDPOINT_MANIFEST[endpoint_name]
    except KeyError as exc:
        available = ", ".join(sorted(ENDPOINT_MANIFEST))
        raise KeyError(
            f"Unknown endpoint '{endpoint_name}'. Available endpoints: {available}"
        ) from exc
