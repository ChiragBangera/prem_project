ANALYTICS_TEMPLATES = {
    "league_player_ranking": {
        "description": "Rank league players by a chosen attacking metric.",
        "question_patterns": [
            "Who has been the best finisher in the EPL in 2025?",
            "Who are the most creative players in the EPL in 2025?",
            "Who are the top scorers in the EPL in 2025?",
        ],
    },
    "league_xpts_gap": {
        "description": "Find the biggest overperformers and underperformers versus xPTS.",
        "question_patterns": [
            "Which team is overperforming xPTS most in the EPL in 2025?",
            "Which team is underperforming xPTS most in the EPL in 2025?",
        ],
    },
    "process_vs_results": {
        "description": "League-wide variance lens for points vs xPTS, goals vs xG, and goals against vs xGA.",
        "question_patterns": [
            "Show the EPL process vs results lens in 2025",
            "Which Premier League teams are getting results that do not match the process in 2025?",
            "Show EPL variance by xPTS, finishing, and xGA in 2025",
        ],
    },
    "player_comparison": {
        "description": "Compare two players on goals, xG, assists, and goal-xG gap.",
        "question_patterns": [
            "Compare Erling Haaland vs Bukayo Saka in 2025",
            "Compare Bruno Fernandes vs Martin Odegaard in 2025",
        ],
    },
    "coach_timeline": {
        "description": "Summarize team performance inside a manager's date window.",
        "question_patterns": [
            "How have Arsenal looked under Mikel Arteta in 2024?",
            "How have Manchester United looked under Ruben Amorim in 2025?",
        ],
    },
    "coach_comparison": {
        "description": "Compare two coach windows on points, xG, xGA, and goal output.",
        "question_patterns": [
            "Compare Mikel Arteta vs Arne Slot in 2024",
            "Compare Erik ten Hag vs Ruben Amorim in 2024",
        ],
    },
    "team_comparison": {
        "description": "Compare two teams on xG, xGA, and recent output.",
        "question_patterns": [
            "Compare Arsenal vs Liverpool in 2025",
            "Manchester United vs Chelsea underlying numbers in 2025",
        ],
    },
    "team_recent_form": {
        "description": "Summarize recent-form output over the last 3, 5, or 10 matches.",
        "question_patterns": [
            "How has Arsenal looked over the last 5 matches in 2025?",
            "How has Arsenal looked over the last 8 matches in 2025?",
            "How has Manchester United looked over the last 10 matches in 2025?",
        ],
    },
    "team_window_comparison": {
        "description": "Compare a team's first and last windows of league matches.",
        "question_patterns": [
            "Compare Arsenal first 5 vs last 5 league matches in 2025",
            "Compare Manchester United first 10 vs last 10 league matches in 2025",
        ],
    },
    "team_defensive_trend": {
        "description": "Track whether a team's defensive process is improving or regressing.",
        "question_patterns": [
            "What are Arsenal's defensive trends in 2025?",
            "How are Liverpool defending lately in 2025?",
        ],
    },
    "team_chance_profile": {
        "description": "Break down where a team creates chances by situation, zone, timing, and speed.",
        "question_patterns": [
            "Show Arsenal chance creation by zone and type in 2025",
            "Where does Manchester United's chance creation come from in 2025?",
        ],
    },
    "team_player_ranking": {
        "description": "Rank players within one team for finishing, creativity, or goals.",
        "question_patterns": [
            "Who has been Manchester United's best finisher in 2025?",
            "Who has been Manchester United's most creative player in 2025?",
            "Who has the best shot quality for Manchester United in 2025?",
            "Who is Arsenal's top scorer in 2025?",
        ],
    },
    "team_attack_defense": {
        "description": "Summarize a team's attacking and defensive profile with xG/xGA and recent outputs.",
        "question_patterns": [
            "How do Manchester United look in attack and defense in 2025?",
            "Are Liverpool stronger in attack or defense in 2025?",
        ],
    },
    "team_position_trend": {
        "description": "Track a team's table position by matchweek and compare season-over-season movement.",
        "question_patterns": [
            "How has Manchester United's table position changed across weeks in 2025?",
            "Manchester United table position over the years compared across weeks",
        ],
    },
    "team_overview": {
        "description": "General team analytics summary built from team stats and player table.",
        "question_patterns": [
            "How are Manchester United performing on Understat in 2025?",
            "What do the numbers say about Liverpool in 2025?",
        ],
    },
}


MANCHESTER_UNITED_PRESETS = [
    {
        "name": "United xPTS Check",
        "question": "Are Manchester United overperforming or underperforming xPTS in 2025?",
        "template": "league_xpts_gap",
    },
    {
        "name": "United Recent Form",
        "question": "How has Manchester United looked over the last 5 matches in 2025?",
        "template": "team_recent_form",
    },
    {
        "name": "United First vs Last 5",
        "question": "Compare Manchester United first 5 vs last 5 league matches in 2025",
        "template": "team_window_comparison",
    },
    {
        "name": "United Table Trend",
        "question": "How has Manchester United's table position changed across weeks in 2025 and over the years?",
        "template": "team_position_trend",
    },
    {
        "name": "United Finishing",
        "question": "Who has been Manchester United's best finisher in 2025?",
        "template": "team_player_ranking",
    },
    {
        "name": "United Creativity",
        "question": "Who has been Manchester United's most creative player in 2025?",
        "template": "team_player_ranking",
    },
    {
        "name": "United Attack vs Defense",
        "question": "How do Manchester United look in attack and defense in 2025?",
        "template": "team_attack_defense",
    },
    {
        "name": "United Defensive Trend",
        "question": "What are Manchester United's defensive trends in 2025?",
        "template": "team_defensive_trend",
    },
    {
        "name": "United Chance Profile",
        "question": "Show Manchester United chance creation by zone and type in 2025",
        "template": "team_chance_profile",
    },
    {
        "name": "United Comparison",
        "question": "Compare Bruno Fernandes vs Amad in 2025",
        "template": "player_comparison",
    },
    {
        "name": "United Amorim Timeline",
        "question": "How have Manchester United looked under Ruben Amorim in 2025?",
        "template": "coach_timeline",
    },
    {
        "name": "United Coach Compare",
        "question": "Compare Erik ten Hag vs Ruben Amorim in 2024",
        "template": "coach_comparison",
    },
    {
        "name": "United vs Arsenal",
        "question": "Compare Manchester United vs Arsenal in 2025",
        "template": "team_comparison",
    },
]
