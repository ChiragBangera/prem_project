from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.coach_eras import (
    find_coach_eras,
    default_coach_season,
    coach_covered_seasons,
    coach_window_for_season,
    season_from_date,
    find_coach_era_by_name,
)


LEAGUE_ALIASES = {
    "epl": "EPL",
    "prem": "EPL",
    "premier": "EPL",
    "premier league": "EPL",
    "la liga": "La_liga",
    "laliga": "La_liga",
    "bundesliga": "Bundesliga",
    "serie a": "Serie_A",
    "ligue 1": "Ligue_1",
    "rfpl": "RFPL",
    "russian premier league": "RFPL",
}
TEAM_ALIASES = {
    "manchester united": "Manchester United",
    "manchester city": "Manchester City",
    "man united": "Manchester United",
    "man utd": "Manchester United",
    "man city": "Manchester City",
    "newcastle united": "Newcastle United",
    "aston villa": "Aston Villa",
    "nottingham forest": "Nottingham Forest",
    "wolverhampton wanderers": "Wolverhampton Wanderers",
    "spurs": "Tottenham",
    "wolves": "Wolverhampton Wanderers",
    "newcastle": "Newcastle United",
    "brighton": "Brighton",
}
TEAM_MARKERS = {
    "united", "city", "town", "rovers", "athletic", "atletico", "real",
    "inter", "milan", "juventus", "arsenal", "chelsea", "liverpool",
    "tottenham", "spur", "forest", "villa", "palace", "bournemouth",
    "getafe", "barcelona", "madrid", "betis", "sevilla", "valencia",
}
QUESTION_STOPWORDS = {
    "how", "what", "why", "when", "where", "who", "is", "are", "was", "were",
    "the", "a", "an", "for", "of", "in", "on", "at", "to", "from", "since",
    "this", "that", "these", "those", "has", "have", "had", "been", "be",
    "show", "tell", "me", "about", "best", "good", "bad",
}
LEADING_ENTITY_VERBS = {"compare", "show", "tell", "analyse", "analyze", "breakdown"}
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class PlannedQuestion:
    question: str
    intent: str
    metric: str | None
    season: int | None
    comparison_seasons: list[int]
    league_name: str | None
    team_name: str | None
    comparison_team_name: str | None
    coach_name: str | None
    comparison_coach_name: str | None
    player_name: str | None
    player_id: int | None
    comparison_player_name: str | None
    comparison_player_id: int | None
    start_date: str | None
    end_date: str | None
    endpoints: list[str]
    notes: list[str]


class Planner:
    """Extracts entities, detects intent and selects endpoints for a question."""

    def __init__(self, client=None, today: date | None = None):
        self.client = client
        self._today = today

    @property
    def today(self) -> date:
        return self._today or date.today()

    async def plan(self, question: str) -> PlannedQuestion:
        question_clean = " ".join(question.strip().split())
        question_lower = question_clean.lower()

        season = self._extract_season(question_lower)
        all_seasons = self._extract_all_seasons(question_lower)
        league_name = self._extract_league(question_lower)
        team_names = self._extract_team_names(question_clean, question_lower)
        team_name = team_names[0] if team_names else None
        comparison_team_name = team_names[1] if len(team_names) > 1 else None
        player_names = self._extract_player_names(question_clean)
        player_name = player_names[0] if player_names else None
        comparison_player_name = player_names[1] if len(player_names) > 1 else None
        start_date, end_date = self._extract_date_range(question_lower, season)
        player_id = None
        comparison_player_id = None
        notes: list[str] = []

        if player_name and not team_name and self.client is not None:
            player_matches = await self.client.search_players(player_name)
            if player_matches:
                player_id = int(player_matches[0]["id"])
                player_name = player_matches[0]["player"]
                notes.append("Resolved player via Understat search endpoint.")

        if comparison_player_name and self.client is not None:
            comparison_matches = await self.client.search_players(comparison_player_name)
            if comparison_matches:
                comparison_player_id = int(comparison_matches[0]["id"])
                comparison_player_name = comparison_matches[0]["player"]
                notes.append("Resolved comparison player via Understat search endpoint.")

        metric = self._extract_metric(question_lower)
        comparison_seasons = [year for year in all_seasons if year != season]
        coach_eras = find_coach_eras(question_lower)
        coach_name = coach_eras[0].coach_name if coach_eras else None
        comparison_coach_name = coach_eras[1].coach_name if len(coach_eras) > 1 else None

        if coach_eras:
            coach_name_set = {era.coach_name for era in coach_eras}
            filtered_players = [name for name in player_names if name not in coach_name_set]
            player_name = filtered_players[0] if filtered_players else None
            comparison_player_name = filtered_players[1] if len(filtered_players) > 1 else None
            if team_name is None:
                team_name = coach_eras[0].team_name
            if league_name is None:
                league_name = coach_eras[0].league_name
            if len(coach_eras) == 1:
                comparison_team_name = None
            elif comparison_team_name is None and len(coach_eras) > 1:
                comparison_team_name = coach_eras[1].team_name

        if season is None and coach_eras:
            season = default_coach_season(coach_eras, self.today.isoformat())
            if season is not None:
                notes.append(f"Defaulted coach analysis to the {season}/{season + 1} Understat season.")

        intent = self._detect_intent(
            question_lower,
            has_player=player_id is not None or bool(player_name),
            has_team=bool(team_name),
            has_comparison_team=bool(comparison_team_name),
            has_league=bool(league_name),
            has_comparison_player=comparison_player_id is not None or bool(comparison_player_name),
            has_coach=bool(coach_name),
            has_comparison_coach=bool(comparison_coach_name),
            metric=metric,
        )
        endpoints = self._select_endpoints(intent, player_id=player_id, team_name=team_name, league_name=league_name)

        if season is None and (team_name or league_name):
            season = 2025
            notes.append("Defaulted season to 2025 because Understat routes are season-based.")
            if start_date is None and end_date is None and ("since" in question_lower or "from " in question_lower):
                start_date, end_date = self._extract_date_range(question_lower, season)

        if league_name is None and (team_name or comparison_team_name):
            league_name = "EPL"
            notes.append("Defaulted league to EPL for club-level analytics that need league context.")

        if intent == "team_position_trend" and not comparison_seasons:
            comparison_seasons = [year for year in [2024, 2023] if season is not None and year != season]
            if comparison_seasons:
                notes.append("Defaulted to a three-season view for year-over-year table-position comparison.")

        if player_name and player_id is None:
            notes.append("Player name was detected, but Understat search could not resolve a player id.")

        return PlannedQuestion(
            question=question_clean,
            intent=intent,
            metric=metric,
            season=season,
            comparison_seasons=comparison_seasons,
            league_name=league_name,
            team_name=team_name,
            comparison_team_name=comparison_team_name,
            coach_name=coach_name,
            comparison_coach_name=comparison_coach_name,
            player_name=player_name,
            player_id=player_id,
            comparison_player_name=comparison_player_name,
            comparison_player_id=comparison_player_id,
            start_date=start_date,
            end_date=end_date,
            endpoints=endpoints,
            notes=notes,
        )

    def _extract_season(self, question_lower: str):
        match = re.search(r"\b(20\d{2})\b", question_lower)
        return int(match.group(1)) if match else None

    def _extract_all_seasons(self, question_lower: str):
        return [int(match) for match in re.findall(r"\b(20\d{2})\b", question_lower)]

    def _extract_league(self, question_lower: str):
        for alias, canonical in sorted(LEAGUE_ALIASES.items(), key=lambda item: -len(item[0])):
            if alias in question_lower:
                return canonical
        return None

    def _extract_date_range(self, question_lower: str, season: int | None):
        default_year = season or self.today.year

        explicit = re.search(
            r"\bfrom\s+(\d{4}-\d{2}-\d{2})\s+(?:to|until)\s+(\d{4}-\d{2}-\d{2})\b",
            question_lower,
        )
        if explicit:
            return explicit.group(1), explicit.group(2)

        since_explicit = re.search(r"\bsince\s+(\d{4}-\d{2}-\d{2})\b", question_lower)
        if since_explicit:
            return since_explicit.group(1), self.today.isoformat()

        for month_name, month_number in MONTH_NAMES.items():
            if f"since {month_name}" in question_lower or f"from {month_name}" in question_lower:
                return f"{default_year}-{month_number:02d}-01", self.today.isoformat()

        return None, None

    def _extract_team_names(self, question_clean: str, question_lower: str):
        team_names: list[str] = []

        for alias, canonical in sorted(TEAM_ALIASES.items(), key=lambda item: -len(item[0])):
            if alias in question_lower:
                team_names.append(canonical)

        for candidate in self._capitalized_phrases(question_clean):
            normalized_candidate = self._normalize_entity_text(candidate)
            words = normalized_candidate.split()
            while words and words[0].lower() in LEADING_ENTITY_VERBS:
                words = words[1:]
            normalized_candidate = " ".join(words)
            if not normalized_candidate:
                continue
            normalized_lower = normalized_candidate.lower()
            if normalized_lower in TEAM_ALIASES:
                team_names.append(TEAM_ALIASES[normalized_lower])
                continue
            candidate_words = {word.lower() for word in normalized_candidate.split()}
            if candidate_words & TEAM_MARKERS:
                team_names.append(normalized_candidate)

        for marker in sorted(TEAM_MARKERS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(marker)}\b", question_lower):
                team_names.append(" ".join(word.capitalize() for word in marker.split()))

        deduped: list[str] = []
        seen: set[str] = set()
        for team_name in team_names:
            key = team_name.lower()
            if key in seen:
                continue
            deduped.append(team_name)
            seen.add(key)

        return deduped

    def _extract_player_names(self, question_clean: str):
        candidates = self._capitalized_phrases(question_clean)
        players = []
        for candidate in candidates:
            candidate = self._normalize_entity_text(candidate)
            words = candidate.split()
            while words and words[0].lower() in LEADING_ENTITY_VERBS:
                words = words[1:]
            candidate = " ".join(words)
            if not candidate:
                continue
            words = candidate.split()
            candidate_words = {word.lower() for word in words}
            if candidate.lower() in TEAM_ALIASES:
                continue
            if len(words) >= 2 and not (candidate_words & TEAM_MARKERS):
                players.append(candidate)
        return players

    def _normalize_entity_text(self, text: str):
        return text.strip().rstrip("?!.,").removesuffix("'s").strip()

    def _capitalized_phrases(self, text: str):
        pattern = r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+)+)\b"
        return re.findall(pattern, text)

    def _extract_metric(self, question_lower: str):
        if (
            "process vs results" in question_lower
            or "process versus results" in question_lower
            or "results vs process" in question_lower
            or "results versus process" in question_lower
            or "variance" in question_lower
        ):
            return "process_vs_results"
        if "xpts" in question_lower:
            return "xpts_gap"
        if "table position" in question_lower or "positions across weeks" in question_lower:
            return "table_position"
        first_last_match = re.search(r"\bfirst\s+(\d{1,2}).*\blast\s+\1\b", question_lower)
        if first_last_match:
            return f"window_compare_{first_last_match.group(1)}"
        recent_window_match = re.search(r"\blast\s+(\d{1,2})\b", question_lower)
        if recent_window_match:
            return f"recent_{recent_window_match.group(1)}"
        if "last three" in question_lower:
            return "recent_3"
        if "last five" in question_lower:
            return "recent_5"
        if "last ten" in question_lower:
            return "recent_10"
        if "best finisher" in question_lower or "finishing" in question_lower:
            return "finishing"
        if "chance creation by zone" in question_lower or "chance creation by type" in question_lower or "chance profile" in question_lower:
            return "chance_profile"
        if "creative" in question_lower or "chance creation" in question_lower or "xA".lower() in question_lower:
            return "creativity"
        if "defensive trend" in question_lower or "defensive trends" in question_lower or "defensively" in question_lower or "conceding" in question_lower:
            return "defensive_trend"
        if "shot quality" in question_lower or "quality of chances" in question_lower:
            return "shot_quality"
        if (
            "attack and defense" in question_lower
            or "attack vs defense" in question_lower
            or "attacking and defensive" in question_lower
            or "creating chances" in question_lower
            or "defensively" in question_lower
            or "xga" in question_lower
        ):
            return "attack_defense"
        if "chance quality" in question_lower:
            return "shot_quality"
        if "top scorer" in question_lower or "goals" in question_lower:
            return "goals"
        if "xg" in question_lower:
            return "xg"
        return None

    def _detect_intent(self, question_lower: str, has_player: bool, has_team: bool, has_comparison_team: bool, has_league: bool, has_comparison_player: bool, has_coach: bool, has_comparison_coach: bool, metric: str | None):
        if has_comparison_coach and ("compare" in question_lower or "vs" in question_lower):
            return "coach_compare"
        if has_coach and ("under " in question_lower or "coach" in question_lower or "manager" in question_lower or "timeline" in question_lower):
            return "coach_timeline"
        if has_comparison_player and ("compare" in question_lower or "vs" in question_lower):
            return "player_compare"
        if has_team and has_comparison_team and ("compare" in question_lower or "vs" in question_lower or " than " in question_lower):
            return "team_compare"
        if has_team and metric and metric.startswith("window_compare_"):
            return "team_window_compare"
        if has_team and ("table position" in question_lower or "across weeks" in question_lower or "over the years" in question_lower):
            return "team_position_trend"
        if metric and metric.startswith("recent_") and has_team:
            return "team_recent_form"
        if metric == "process_vs_results":
            return "process_vs_results"
        if metric == "xpts_gap" and ("overperform" in question_lower or "underperform" in question_lower):
            return "team_xpts_gap" if has_team or has_league else "league_overview"
        if has_team and metric == "defensive_trend":
            return "team_defensive_trend"
        if has_team and metric == "chance_profile":
            return "team_chance_profile"
        if has_team and metric in {"finishing", "creativity", "goals", "shot_quality"} and ("best" in question_lower or "most" in question_lower or "top" in question_lower):
            return "team_player_ranking"
        if has_team and metric == "attack_defense":
            return "team_attack_defense"
        if ("best" in question_lower or "most" in question_lower or "top" in question_lower) and metric in {"finishing", "creativity", "goals", "shot_quality"}:
            return "player_ranking"
        if "top scorer" in question_lower or "top scorers" in question_lower:
            return "league_overview"
        if "table" in question_lower or "standings" in question_lower:
            return "league_table"
        if "xg" in question_lower or "overperform" in question_lower or "underperform" in question_lower:
            return "player_overview" if has_player else "team_overview" if has_team else "league_overview"
        if "fixture" in question_lower or "upcoming" in question_lower:
            return "fixtures"
        if "result" in question_lower or "recent match" in question_lower:
            return "results"
        if "shot" in question_lower or "finishing" in question_lower:
            return "player_shots" if has_player else "match_shots"
        if "compare" in question_lower:
            return "player_compare" if has_player else "overview"
        if has_player:
            return "player_overview"
        if has_team:
            return "team_overview"
        if has_league:
            return "league_overview"
        return "overview"

    def _select_endpoints(self, intent: str, player_id=None, team_name=None, league_name=None):
        if intent == "league_table":
            return ["league_table"]
        if intent in {"coach_timeline", "coach_compare"}:
            return ["coach_era"]
        if intent == "team_compare":
            return ["league_table", "team_results"]
        if intent == "team_window_compare":
            return ["team_results"]
        if intent == "team_position_trend":
            return ["league_data"]
        if intent == "team_xpts_gap":
            return ["league_table"]
        if intent == "process_vs_results":
            return ["league_table"]
        if intent == "team_recent_form":
            return ["team_results", "team_player_stats"]
        if intent == "team_defensive_trend":
            return ["team_results", "team_stats", "league_table"]
        if intent == "team_chance_profile":
            return ["team_stats"]
        if intent == "team_player_ranking":
            return ["team_player_stats"]
        if intent == "team_attack_defense":
            return ["league_table", "team_results", "team_player_stats"]
        if intent == "player_ranking":
            return ["league_player_stats"]
        if intent == "fixtures":
            return ["team_fixtures"] if team_name else ["league_fixtures"]
        if intent == "results":
            return ["team_results"] if team_name else ["league_results"]
        if intent == "player_shots":
            return ["player_data", "player_shots", "player_grouped_stats"]
        if intent == "player_compare":
            return ["player_data", "player_matches_via_ajax", "player_last_match"]
        if intent == "player_overview":
            return ["player_data", "player_matches", "player_grouped_stats", "player_shots"]
        if intent == "team_overview":
            return ["team_stats", "team_players", "team_results", "team_player_stats"]
        if intent == "league_overview":
            return ["league_table", "league_player_stats"]
        return ["stats"]

    def _default_coach_season(self, eras):
        return default_coach_season(eras, self.today.isoformat())

    def _coach_covered_seasons(self, era):
        return coach_covered_seasons(era, self.today.isoformat())

    def _season_from_date(self, date_string: str):
        return season_from_date(date_string)

    def _coach_window_for_season(self, era, season: int):
        return coach_window_for_season(era, season, self.today.isoformat())
