from __future__ import annotations

import re
from datetime import date
from dataclasses import asdict, dataclass

from app.coach_eras import find_coach_eras
from app.stat_data import UnderstatData
from app.visual_templates import VISUAL_TEMPLATE_REGISTRY


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
CURRENT_DATE = date(2026, 4, 6)


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


class FootballQuestionAnswerer:
    def __init__(self, client=None):
        self.client = client or UnderstatData()
        self._owns_client = client is None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._owns_client:
            await self.client.close()

    async def answer(self, question: str):
        plan = await self.plan(question)
        data = await self._fetch_for_plan(plan)
        answer = self._build_answer(plan, data)
        return {
            "plan": asdict(plan),
            "answer": answer,
            "data_summary": self._summarize_data_shapes(data),
            "template": self._template_metadata(plan, answer),
        }

    async def plan(self, question: str):
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
        notes = []

        if player_name and not team_name:
            player_matches = await self.client.search_players(player_name)
            if player_matches:
                player_id = int(player_matches[0]["id"])
                player_name = player_matches[0]["player"]
                notes.append("Resolved player via Understat search endpoint.")

        if comparison_player_name:
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
            season = self._default_coach_season(coach_eras)
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
        default_year = season or CURRENT_DATE.year

        explicit = re.search(
            r"\bfrom\s+(\d{4}-\d{2}-\d{2})\s+(?:to|until)\s+(\d{4}-\d{2}-\d{2})\b",
            question_lower,
        )
        if explicit:
            return explicit.group(1), explicit.group(2)

        since_explicit = re.search(r"\bsince\s+(\d{4}-\d{2}-\d{2})\b", question_lower)
        if since_explicit:
            return since_explicit.group(1), CURRENT_DATE.isoformat()

        for month_name, month_number in MONTH_NAMES.items():
            if f"since {month_name}" in question_lower or f"from {month_name}" in question_lower:
                return f"{default_year}-{month_number:02d}-01", CURRENT_DATE.isoformat()

        return None, None

    def _extract_team(self, question_clean: str, question_lower: str):
        team_names = self._extract_team_names(question_clean, question_lower)
        return team_names[0] if team_names else None

    def _extract_team_names(self, question_clean: str, question_lower: str):
        team_names = []

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

        deduped = []
        seen = set()
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

    async def _fetch_for_plan(self, plan: PlannedQuestion):
        data = {}
        for endpoint in plan.endpoints:
            if endpoint == "coach_era":
                data[endpoint] = await self._fetch_coach_era_data(plan)
            elif endpoint == "league_table":
                data[endpoint] = await self.client.get_league_table(
                    plan.league_name or "EPL",
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "league_fixtures":
                data[endpoint] = await self.client.get_league_fixtures(plan.league_name or "EPL", plan.season or 2025)
            elif endpoint == "league_results":
                data[endpoint] = await self.client.get_league_results(plan.league_name or "EPL", plan.season or 2025)
            elif endpoint == "league_player_stats":
                data[endpoint] = await self.client.get_league_player_stats(
                    plan.league_name or "EPL",
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "league_data":
                seasons = [plan.season, *plan.comparison_seasons]
                data[endpoint] = {
                    current_season: await self.client.get_league_data(
                        plan.league_name or "EPL",
                        current_season or 2025,
                    )
                    for current_season in seasons
                    if current_season is not None
                }
            elif endpoint == "team_stats":
                data[endpoint] = await self.client.get_team_stats(plan.team_name, plan.season or 2025)
            elif endpoint == "team_players":
                data[endpoint] = await self.client.get_team_players(plan.team_name, plan.season or 2025)
            elif endpoint == "team_results":
                data[endpoint] = await self.client.get_team_results(plan.team_name, plan.season or 2025)
            elif endpoint == "team_fixtures":
                data[endpoint] = await self.client.get_team_fixtures(plan.team_name, plan.season or 2025)
            elif endpoint == "team_player_stats":
                data[endpoint] = await self.client.get_team_player_stats(
                    plan.team_name,
                    plan.season or 2025,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_data":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_data(plan.player_id)
            elif endpoint == "player_matches":
                if plan.player_id is None:
                    continue
                matches = await self.client.get_player_matches(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    matches,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_grouped_stats":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_grouped_stats(plan.player_id)
            elif endpoint == "player_shots":
                if plan.player_id is None:
                    continue
                shots = await self.client.get_player_shots(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    shots,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_matches_via_ajax":
                if plan.player_id is None:
                    continue
                matches = await self.client.get_player_matches_via_ajax(plan.player_id)
                data[endpoint] = self._filter_player_rows(
                    matches,
                    season=plan.season,
                    start_date=plan.start_date,
                    end_date=plan.end_date,
                )
            elif endpoint == "player_last_match":
                if plan.player_id is None:
                    continue
                data[endpoint] = await self.client.get_player_last_match(plan.player_id)
            elif endpoint == "stats":
                data[endpoint] = await self.client.get_stats()

        if plan.intent == "player_compare" and plan.comparison_player_id is not None:
            comparison_data = await self.client.get_player_data(plan.comparison_player_id)
            comparison_matches = await self.client.get_player_matches(plan.comparison_player_id)
            data["comparison_player_data"] = comparison_data
            data["comparison_player_matches"] = self._filter_player_rows(
                comparison_matches,
                season=plan.season,
                start_date=plan.start_date,
                end_date=plan.end_date,
            )
        if plan.intent == "team_compare" and plan.comparison_team_name is not None:
            comparison_results = await self.client.get_team_results(plan.comparison_team_name, plan.season or 2025)
            data["comparison_team_results"] = comparison_results
        return data

    async def _fetch_coach_era_data(self, plan: PlannedQuestion):
        primary_era = self._find_coach_era_by_name(plan.coach_name, plan.team_name)
        if primary_era is None:
            return {}

        if plan.intent == "coach_compare":
            comparison_era = self._find_coach_era_by_name(plan.comparison_coach_name, plan.comparison_team_name or plan.team_name)
            if comparison_era is None:
                return {}
            season = plan.season or self._default_coach_season([primary_era, comparison_era])
            primary_window = self._coach_window_for_season(primary_era, season)
            comparison_window = self._coach_window_for_season(comparison_era, season)
            return {
                "season": season,
                "primary": await self._fetch_team_window_bundle(
                    team_name=primary_era.team_name,
                    league_name=primary_era.league_name,
                    season=season,
                    start_date=primary_window[0],
                    end_date=primary_window[1],
                ) if primary_window else None,
                "comparison": await self._fetch_team_window_bundle(
                    team_name=comparison_era.team_name,
                    league_name=comparison_era.league_name,
                    season=season,
                    start_date=comparison_window[0],
                    end_date=comparison_window[1],
                ) if comparison_window else None,
                "primary_window": primary_window,
                "comparison_window": comparison_window,
            }

        seasons = [plan.season] if plan.season is not None else self._coach_covered_seasons(primary_era)
        season_payloads = {}
        for season in seasons:
            window = self._coach_window_for_season(primary_era, season)
            if not window:
                continue
            season_payloads[season] = await self._fetch_team_window_bundle(
                team_name=primary_era.team_name,
                league_name=primary_era.league_name,
                season=season,
                start_date=window[0],
                end_date=window[1],
            )
            season_payloads[season]["window"] = window
        return {
            "coach_name": primary_era.coach_name,
            "team_name": primary_era.team_name,
            "seasons": season_payloads,
        }

    async def _fetch_team_window_bundle(self, team_name: str, league_name: str, season: int, start_date: str, end_date: str):
        league_table = await self.client.get_league_table(
            league_name,
            season,
            start_date=start_date,
            end_date=end_date,
        )
        team_results = await self.client.get_team_results(team_name, season)
        filtered_results = self._filter_rows_by_date(team_results, start_date=start_date, end_date=end_date)
        team_player_stats = await self.client.get_team_player_stats(
            team_name,
            season,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "league_table": league_table,
            "team_results": filtered_results,
            "team_player_stats": team_player_stats,
        }

    def _build_answer(self, plan: PlannedQuestion, data: dict):
        reasons = []
        direct_answer = ""
        social_caption = ""
        viz_context = {}

        timeframe = self._describe_timeframe(plan)

        if plan.intent == "league_table" and "league_table" in data:
            table = data["league_table"]
            top_row = table[1] if len(table) > 1 else None
            if top_row:
                reasons.append(f"{top_row[0]} are top of the table on {top_row[7]} points in the selected view.")
                direct_answer = f"{top_row[0]} are top of the {plan.league_name or 'selected league'} table with {top_row[7]} points {timeframe}."
                social_caption = f"{top_row[0]} lead the table on {top_row[7]} points {timeframe}. Understat-backed snapshot."

        if plan.intent == "league_overview":
            if "league_table" in data and len(data["league_table"]) > 1:
                top_row = data["league_table"][1]
                reasons.append(f"{top_row[0]} lead the table with {top_row[7]} points.")
            if "league_player_stats" in data and data["league_player_stats"]:
                top_scorer = max(data["league_player_stats"], key=lambda row: float(row.get("goals", 0)))
                reasons.append(
                    f"{top_scorer.get('player_name')} is the top scorer in the fetched player table with {top_scorer.get('goals')} goals."
                )
                if not direct_answer:
                    direct_answer = (
                        f"In {plan.league_name or 'the selected league'} {timeframe}, "
                        f"{top_row[0]} lead the table and {top_scorer.get('player_name')} leads the scoring chart with {top_scorer.get('goals')} goals."
                    )
                    social_caption = (
                        f"{top_row[0]} on top. {top_scorer.get('player_name')} leading the scoring race with {top_scorer.get('goals')} goals. "
                        f"Understat check {timeframe}."
                    )

        if plan.intent == "team_xpts_gap" and "league_table" in data:
            table = data["league_table"]
            rows = table[1:] if len(table) > 1 else []
            if rows:
                enriched = []
                for row in rows:
                    pts = float(row[7])
                    xpts = float(row[17])
                    enriched.append(
                        {
                            "team": row[0],
                            "pts": pts,
                            "xpts": xpts,
                            "gap": round(pts - xpts, 2),
                        }
                    )
                if plan.team_name:
                    matching = next((row for row in enriched if row["team"].lower() == plan.team_name.lower()), None)
                    if matching:
                        trend = "overperforming" if matching["gap"] > 0 else "underperforming" if matching["gap"] < 0 else "tracking xPTS almost exactly"
                        direct_answer = (
                            f"{matching['team']} are {trend} {timeframe}: they have {int(matching['pts'])} points versus {matching['xpts']:.2f} xPTS, "
                            f"a gap of {matching['gap']:+.2f}."
                        )
                        reasons.append(
                            f"{matching['team']} have a points-minus-xPTS gap of {matching['gap']:+.2f}."
                        )
                        social_caption = (
                            f"{matching['team']} xPTS check {timeframe}: {int(matching['pts'])} points vs {matching['xpts']:.2f} xPTS "
                            f"({matching['gap']:+.2f})."
                        )
                else:
                    top_gap = max(enriched, key=lambda row: row["gap"])
                    bottom_gap = min(enriched, key=lambda row: row["gap"])
                    direct_answer = (
                        f"The biggest xPTS overperformer {timeframe} is {top_gap['team']} at {top_gap['gap']:+.2f}, "
                        f"while the biggest underperformer is {bottom_gap['team']} at {bottom_gap['gap']:+.2f}."
                    )
                    reasons.append(
                        f"{top_gap['team']} lead the league in positive points-minus-xPTS gap at {top_gap['gap']:+.2f}."
                    )
                    reasons.append(
                        f"{bottom_gap['team']} have the worst points-minus-xPTS gap at {bottom_gap['gap']:+.2f}."
                    )
                    social_caption = direct_answer

        if plan.intent == "process_vs_results" and "league_table" in data:
            process_rows = self._league_process_vs_results_rows(data["league_table"])
            if process_rows:
                points_over = max(process_rows, key=lambda row: row["points_gap"])
                points_under = min(process_rows, key=lambda row: row["points_gap"])
                finishing_over = max(process_rows, key=lambda row: row["finishing_gap"])
                finishing_under = min(process_rows, key=lambda row: row["finishing_gap"])
                defensive_over = max(process_rows, key=lambda row: row["defensive_prevention_gap"])
                defensive_under = min(process_rows, key=lambda row: row["defensive_prevention_gap"])

                direct_answer = (
                    f"Process vs results {timeframe}: {points_over['team']} are getting the biggest results boost "
                    f"({points_over['points_gap']:+.2f} points vs xPTS), while {points_under['team']} are the biggest under-earners "
                    f"({points_under['points_gap']:+.2f})."
                )
                reasons.append(
                    f"Points vs process: {points_over['team']} lead points-minus-xPTS at {points_over['points_gap']:+.2f}; "
                    f"{points_under['team']} are bottom at {points_under['points_gap']:+.2f}."
                )
                reasons.append(
                    f"Finishing variance: {finishing_over['team']} are highest on goals-minus-xG at {finishing_over['finishing_gap']:+.2f}; "
                    f"{finishing_under['team']} are lowest at {finishing_under['finishing_gap']:+.2f}."
                )
                reasons.append(
                    f"Defensive/keeper variance: {defensive_over['team']} are {defensive_over['defensive_prevention_gap']:+.2f} on xGA minus goals against; "
                    f"{defensive_under['team']} are lowest at {defensive_under['defensive_prevention_gap']:+.2f}."
                )
                viz_context = {
                    "categories": [row["team"] for row in sorted(process_rows, key=lambda item: item["points_gap"], reverse=True)],
                    "series": {
                        "points_minus_xpts": [
                            row["points_gap"] for row in sorted(process_rows, key=lambda item: item["points_gap"], reverse=True)
                        ],
                        "goals_minus_xg": [
                            row["finishing_gap"] for row in sorted(process_rows, key=lambda item: item["points_gap"], reverse=True)
                        ],
                        "xga_minus_goals_against": [
                            row["defensive_prevention_gap"] for row in sorted(process_rows, key=lambda item: item["points_gap"], reverse=True)
                        ],
                    },
                    "rankings": {
                        "points_overperformer": points_over,
                        "points_underperformer": points_under,
                        "finishing_overperformer": finishing_over,
                        "finishing_underperformer": finishing_under,
                        "defensive_overperformer": defensive_over,
                        "defensive_underperformer": defensive_under,
                    },
                }
                social_caption = (
                    f"Process vs results {timeframe}: {points_over['team']} are running hottest against xPTS "
                    f"({points_over['points_gap']:+.2f}), while {points_under['team']} are the clearest under-earners "
                    f"({points_under['points_gap']:+.2f})."
                )

        if plan.intent == "team_position_trend" and "league_data" in data:
            season_summaries = []
            for season_key, league_data in data["league_data"].items():
                progression = self._team_position_progression(
                    league_data=league_data,
                    team_name=plan.team_name,
                )
                if progression:
                    season_summaries.append(
                        {
                            "season": season_key,
                            "progression": progression,
                            "start_position": progression[0]["position"],
                            "end_position": progression[-1]["position"],
                            "best_position": min(item["position"] for item in progression),
                            "worst_position": max(item["position"] for item in progression),
                        }
                    )

            if season_summaries:
                latest = sorted(season_summaries, key=lambda item: item["season"], reverse=True)[0]
                direct_answer = (
                    f"{plan.team_name}'s weekly table-position trend is available. "
                    f"In {latest['season']}/{latest['season'] + 1}, they moved from {latest['start_position']} to {latest['end_position']}, "
                    f"with a best position of {latest['best_position']} and worst of {latest['worst_position']}."
                )
                if len(season_summaries) > 1:
                    comparison_text = "; ".join(
                        f"{item['season']}: start {item['start_position']}, finish {item['end_position']}"
                        for item in sorted(season_summaries, key=lambda x: x["season"], reverse=True)
                    )
                    reasons.append(f"Season-over-season weekly table position summaries: {comparison_text}.")
                reasons.append(
                    f"Weekly position progression was derived from Understat league histories for {plan.team_name}."
                )
                social_caption = direct_answer

        if plan.intent == "coach_timeline" and "coach_era" in data:
            coach_payload = data.get("coach_era", {})
            season_payloads = coach_payload.get("seasons", {})
            season_summaries = []
            for season_key, bundle in sorted(season_payloads.items()):
                summary = self._team_bundle_summary(bundle, plan.team_name)
                if summary:
                    summary["season"] = season_key
                    summary["window"] = bundle.get("window")
                    season_summaries.append(summary)

            if season_summaries:
                latest_summary = season_summaries[-1]
                direct_answer = (
                    f"{plan.team_name} under {plan.coach_name} {self._format_window(latest_summary.get('window'))}: "
                    f"{latest_summary['points']} points from {latest_summary['matches']} league matches, "
                    f"{latest_summary['goals_for']}-{latest_summary['goals_against']} goals, xG {self._fmt_num(latest_summary['xg'])}, "
                    f"xGA {self._fmt_num(latest_summary['xga'])}."
                )
                if latest_summary.get("top_scorer"):
                    reasons.append(
                        f"{latest_summary['top_scorer']} leads the scoring in that coach window with {latest_summary['top_scorer_goals']} goals."
                    )
                if latest_summary.get("top_creator"):
                    reasons.append(
                        f"{latest_summary['top_creator']} leads chance creation in that coach window with {latest_summary['top_creator_xa']} xA."
                    )
                if len(season_summaries) > 1:
                    timeline_text = "; ".join(
                        f"{item['season']}/{item['season'] + 1}: {item['points']} pts from {item['matches']} matches"
                        for item in season_summaries
                    )
                    reasons.append(f"Coach timeline by Understat season: {timeline_text}.")
                social_caption = direct_answer

        if plan.intent == "coach_compare" and "coach_era" in data:
            coach_payload = data.get("coach_era", {})
            primary_bundle = coach_payload.get("primary")
            comparison_bundle = coach_payload.get("comparison")
            if primary_bundle and comparison_bundle:
                primary_summary = self._team_bundle_summary(primary_bundle, plan.team_name)
                comparison_summary = self._team_bundle_summary(comparison_bundle, plan.comparison_team_name or plan.team_name)
                if primary_summary and comparison_summary:
                    direct_answer = (
                        f"{plan.coach_name} vs {plan.comparison_coach_name} in the {coach_payload.get('season')}/{coach_payload.get('season', 0) + 1} Understat season: "
                        f"{plan.coach_name} posted {primary_summary['ppg']} points per game with xG {self._fmt_num(primary_summary['xg'])} and xGA {self._fmt_num(primary_summary['xga'])}; "
                        f"{plan.comparison_coach_name} posted {comparison_summary['ppg']} points per game with xG {self._fmt_num(comparison_summary['xg'])} and xGA {self._fmt_num(comparison_summary['xga'])}."
                    )
                    reasons.append(
                        f"{plan.coach_name}'s window ran {self._format_window(coach_payload.get('primary_window'))} and {plan.comparison_coach_name}'s ran {self._format_window(coach_payload.get('comparison_window'))}."
                    )
                    reasons.append(
                        f"Goal output comparison: {plan.coach_name} {primary_summary['goals_for']}-{primary_summary['goals_against']}, "
                        f"{plan.comparison_coach_name} {comparison_summary['goals_for']}-{comparison_summary['goals_against']}."
                    )
                    social_caption = direct_answer

        if plan.intent == "team_recent_form":
            team_results = data.get("team_results", [])
            team_players = data.get("team_player_stats", [])
            match_limit = self._recent_window_from_metric(plan.metric)
            ordered_results = self._sort_rows_by_date(team_results, descending=True)
            sliced_results = ordered_results[:match_limit] if match_limit else ordered_results
            recent_summary = self._team_results_summary(sliced_results)
            points = recent_summary["points"]
            goals_for = recent_summary["goals_for"]
            goals_against = recent_summary["goals_against"]
            top_scorer = None
            if team_players:
                top_scorer = max(team_players, key=lambda row: float(row.get("goals", 0)))
            direct_answer = (
                f"{plan.team_name} over their last {len(sliced_results)} matches: "
                f"{points} points, {goals_for} goals scored, {goals_against} conceded."
            )
            if top_scorer:
                direct_answer += f" The top scorer in the filtered team player table is {top_scorer.get('player_name')} with {top_scorer.get('goals')} goals."
                reasons.append(
                    f"{top_scorer.get('player_name')} leads the team scoring output in the current filtered window."
                )
            reasons.append(
                f"The recent-form sample contains {len(sliced_results)} team results."
            )
            social_caption = direct_answer

        if plan.intent == "team_window_compare":
            team_results = self._sort_rows_by_date(data.get("team_results", []), descending=False)
            window_size = self._window_compare_size(plan.metric)
            if window_size and len(team_results) >= window_size * 2:
                first_window = team_results[:window_size]
                last_window = team_results[-window_size:]
                first_summary = self._team_results_window_summary(first_window)
                last_summary = self._team_results_window_summary(last_window)
                direct_answer = (
                    f"{plan.team_name} first {window_size} vs last {window_size} league matches {timeframe}: "
                    f"points per game moved from {self._fmt_num(first_summary['ppg'])} to {self._fmt_num(last_summary['ppg'])}, "
                    f"xG per game from {self._fmt_num(first_summary['xg_per_game'])} to {self._fmt_num(last_summary['xg_per_game'])}, "
                    f"and xGA per game from {self._fmt_num(first_summary['xga_per_game'])} to {self._fmt_num(last_summary['xga_per_game'])}."
                )
                reasons.append(
                    f"Goal difference shifted from {first_summary['goals_for']}-{first_summary['goals_against']} in the first window to {last_summary['goals_for']}-{last_summary['goals_against']} in the last window."
                )
                reasons.append(
                    f"That is a {self._trend_label(last_summary['xga_per_game'], first_summary['xga_per_game'], lower_is_better=True)} defensive process on xGA per game."
                )
                viz_context = {
                    "categories": ["First window", "Last window"],
                    "series": {
                        "points_per_game": [first_summary["ppg"], last_summary["ppg"]],
                        "xg_per_game": [first_summary["xg_per_game"], last_summary["xg_per_game"]],
                        "xga_per_game": [first_summary["xga_per_game"], last_summary["xga_per_game"]],
                    },
                }
                social_caption = direct_answer

        if plan.intent == "team_defensive_trend":
            team_results = self._sort_rows_by_date(data.get("team_results", []), descending=False)
            if len(team_results) >= 10:
                recent_window = team_results[-5:]
                previous_window = team_results[-10:-5]
                recent_summary = self._team_results_window_summary(recent_window)
                previous_summary = self._team_results_window_summary(previous_window)
                direct_answer = (
                    f"{plan.team_name}'s defensive trend {timeframe}: over the latest 5 league matches they have conceded "
                    f"{recent_summary['goals_against']} goals with xGA {self._fmt_num(recent_summary['xga'])} "
                    f"({self._fmt_num(recent_summary['xga_per_game'])} per game), compared with "
                    f"{previous_summary['goals_against']} goals and xGA {self._fmt_num(previous_summary['xga'])} "
                    f"({self._fmt_num(previous_summary['xga_per_game'])} per game) in the prior 5."
                )
                reasons.append(
                    f"The defensive process is {self._trend_label(recent_summary['xga_per_game'], previous_summary['xga_per_game'], lower_is_better=True)} on xGA per game."
                )
                if recent_summary["shots_against"] is not None and previous_summary["shots_against"] is not None:
                    reasons.append(
                        f"Shots allowed moved from {previous_summary['shots_against']} in the prior 5 to {recent_summary['shots_against']} in the latest 5."
                    )
                viz_context = {
                    "categories": ["Previous 5", "Latest 5"],
                    "series": {
                        "xga_per_game": [previous_summary["xga_per_game"], recent_summary["xga_per_game"]],
                        "goals_against": [previous_summary["goals_against"], recent_summary["goals_against"]],
                    },
                }
                social_caption = direct_answer

        if plan.intent == "team_chance_profile":
            team_stats = data.get("team_stats", {})
            chance_profile = self._team_chance_profile(team_stats)
            if chance_profile:
                direct_answer = (
                    f"{plan.team_name}'s chance-creation profile {timeframe}: their biggest xG source is {chance_profile['top_situation']['label']} "
                    f"({self._fmt_num(chance_profile['top_situation']['xg'])} xG), while their highest-volume shooting zone is "
                    f"{chance_profile['top_zone']['label']} ({chance_profile['top_zone']['shots']} shots, {self._fmt_num(chance_profile['top_zone']['xg'])} xG)."
                )
                reasons.append(
                    f"Best attacking speed bucket by xG is {chance_profile['top_speed']['label']} at {self._fmt_num(chance_profile['top_speed']['xg'])}."
                )
                reasons.append(
                    f"Peak scoring window is {chance_profile['top_timing']['label']} with {self._fmt_num(chance_profile['top_timing']['xg'])} xG created."
                )
                viz_context = {
                    "categories": [
                        chance_profile["top_situation"]["label"],
                        chance_profile["top_zone"]["label"],
                        chance_profile["top_timing"]["label"],
                    ],
                    "series": {
                        "xg": [
                            chance_profile["top_situation"]["xg"],
                            chance_profile["top_zone"]["xg"],
                            chance_profile["top_timing"]["xg"],
                        ],
                        "shots": [
                            chance_profile["top_situation"]["shots"],
                            chance_profile["top_zone"]["shots"],
                            chance_profile["top_timing"]["shots"],
                        ],
                    },
                }
                social_caption = direct_answer

        if plan.intent == "team_compare" and "league_table" in data:
            left_row = self._find_team_table_row(data["league_table"], plan.team_name)
            right_row = self._find_team_table_row(data["league_table"], plan.comparison_team_name)
            left_results = self._sort_rows_by_date(data.get("team_results", []), descending=True)[:5]
            right_results = self._sort_rows_by_date(data.get("comparison_team_results", []), descending=True)[:5]
            if left_row and right_row:
                left_profile = self._team_table_profile(left_row)
                right_profile = self._team_table_profile(right_row)
                left_recent = self._team_results_summary(left_results)
                right_recent = self._team_results_summary(right_results)
                attack_winner = left_profile["team"] if left_profile["xg"] > right_profile["xg"] else right_profile["team"]
                defense_winner = left_profile["team"] if left_profile["xga"] < right_profile["xga"] else right_profile["team"]
                direct_answer = (
                    f"{left_profile['team']} vs {right_profile['team']} {timeframe}: "
                    f"{attack_winner} have the stronger attacking process on xG ({left_profile['team']} {self._fmt_num(left_profile['xg'])}, "
                    f"{right_profile['team']} {self._fmt_num(right_profile['xg'])}), while {defense_winner} have the better defensive process on xGA "
                    f"({left_profile['team']} {self._fmt_num(left_profile['xga'])}, {right_profile['team']} {self._fmt_num(right_profile['xga'])})."
                )
                reasons.append(
                    f"{left_profile['team']} carry a non-penalty xG difference of {self._fmt_num(left_profile['npxgd'])}, compared with {right_profile['team']} at {self._fmt_num(right_profile['npxgd'])}."
                )
                reasons.append(
                    f"Recent five-match output: {left_profile['team']} have {left_recent['points']} points and {left_recent['goals_for']}-{left_recent['goals_against']} goals; "
                    f"{right_profile['team']} have {right_recent['points']} points and {right_recent['goals_for']}-{right_recent['goals_against']}."
                )
                reasons.append(
                    f"W-D-L form over the same stretch: {left_profile['team']} {left_recent['wins']}-{left_recent['draws']}-{left_recent['losses']}, "
                    f"{right_profile['team']} {right_recent['wins']}-{right_recent['draws']}-{right_recent['losses']}."
                )
                viz_context = {
                    "categories": [left_profile["team"], right_profile["team"]],
                    "series": {
                        "points_last_5": [left_recent["points"], right_recent["points"]],
                        "goals_for_last_5": [left_recent["goals_for"], right_recent["goals_for"]],
                        "goals_against_last_5": [left_recent["goals_against"], right_recent["goals_against"]],
                        "xg_last_5": [left_recent["xg"], right_recent["xg"]],
                        "xga_last_5": [left_recent["xga"], right_recent["xga"]],
                    },
                    "records": {
                        left_profile["team"]: f"{left_recent['wins']}-{left_recent['draws']}-{left_recent['losses']}",
                        right_profile["team"]: f"{right_recent['wins']}-{right_recent['draws']}-{right_recent['losses']}",
                    },
                    "result_sequences": {
                        left_profile["team"]: self._team_result_sequence(left_results),
                        right_profile["team"]: self._team_result_sequence(right_results),
                    },
                }
                social_caption = direct_answer

        if plan.intent == "team_player_ranking" and "team_player_stats" in data:
            ranking_rows = data["team_player_stats"]
            ranked = self._rank_players(ranking_rows, plan.metric)
            if ranked:
                top = ranked[0]
                metric_label = top["metric_label"]
                direct_answer = (
                    f"{top['player_name']} has been {plan.team_name}'s standout for {metric_label} {timeframe}, "
                    f"leading the squad with {top['metric_value']}."
                )
                reasons.append(
                    f"{top['player_name']} ranks first in the filtered {plan.team_name} player table on {metric_label}."
                )
                if len(ranked) > 1:
                    reasons.append(
                        f"The next-best squad mark belongs to {ranked[1]['player_name']} at {ranked[1]['metric_value']}."
                    )
                social_caption = (
                    f"{plan.team_name} leader for {metric_label} {timeframe}: "
                    f"{top['player_name']} on {top['metric_value']}."
                )

        if plan.intent == "team_attack_defense":
            league_table = data.get("league_table", [])
            team_results = data.get("team_results", [])
            team_players = data.get("team_player_stats", [])
            table_row = self._find_team_table_row(league_table, plan.team_name)
            xg_for = None
            xg_against = None
            xg_diff = None
            npxgd = None
            if table_row:
                xg_for = float(table_row[8])
                xg_against = float(table_row[10])
                npxgd = round(float(table_row[12]), 2)
            if xg_for is not None and xg_against is not None:
                xg_diff = round(xg_for - xg_against, 2)

            attacking_leader = self._rank_players(team_players, "goals")
            creative_leader = self._rank_players(team_players, "creativity")
            recent_results = self._sort_rows_by_date(team_results, descending=True)[:5]
            recent_summary = self._team_results_summary(recent_results)
            recent_points = recent_summary["points"]
            recent_scored = recent_summary["goals_for"]
            recent_conceded = recent_summary["goals_against"]

            if xg_for is not None or xg_against is not None:
                direct_answer = (
                    f"{plan.team_name}'s attack-defense profile {timeframe}: "
                    f"{f'xG {self._fmt_num(xg_for)}' if xg_for is not None else 'xG unavailable'}"
                    f"{f', xGA {self._fmt_num(xg_against)}' if xg_against is not None else ''}"
                    f"{f', xG difference {self._fmt_num(xg_diff)}' if xg_diff is not None else ''}. "
                    f"Across their latest {len(recent_results)} team results, they scored {recent_scored} and conceded {recent_conceded} for {recent_points} points."
                )
                reasons.append(
                    f"{plan.team_name}'s league-table row gives us attack/defense anchors through xG and xGA."
                )
                if xg_diff is not None:
                    trend_label = "positive" if xg_diff > 0 else "negative" if xg_diff < 0 else "neutral"
                    reasons.append(
                        f"The club's xG difference is {trend_label} at {self._fmt_num(xg_diff)}."
                    )
                if npxgd is not None:
                    reasons.append(
                        f"The club's non-penalty xG difference sits at {self._fmt_num(npxgd)}."
                    )
                if attacking_leader:
                    reasons.append(
                        f"{attacking_leader[0]['player_name']} is the leading scorer in the filtered squad table with {attacking_leader[0]['metric_value']} goals."
                    )
                if creative_leader:
                    reasons.append(
                        f"{creative_leader[0]['player_name']} leads the squad for xA with {creative_leader[0]['metric_value']}."
                    )
                social_caption = (
                    f"{plan.team_name} attack/defense snapshot {timeframe}: "
                    f"{f'xG {self._fmt_num(xg_for)}, ' if xg_for is not None else ''}"
                    f"{f'xGA {self._fmt_num(xg_against)}, ' if xg_against is not None else ''}"
                    f"{recent_scored}-{recent_conceded} goals across the latest {len(recent_results)} results."
                )

        if plan.intent == "player_ranking" and "league_player_stats" in data:
            ranking_rows = data["league_player_stats"]
            ranked = self._rank_players(ranking_rows, plan.metric)
            if ranked:
                top = ranked[0]
                metric_label = top["metric_label"]
                direct_answer = (
                    f"The best {self._humanize_metric(plan.metric) or 'attacking'} profile {timeframe} is {top['player_name']} ({top['team_title']}), "
                    f"leading the league on {metric_label}: {top['metric_value']}."
                )
                reasons.append(
                    f"{top['player_name']} ranks first on {metric_label} among the fetched league player table."
                )
                if len(ranked) > 1:
                    reasons.append(
                        f"Next best is {ranked[1]['player_name']} at {ranked[1]['metric_value']}."
                    )
                social_caption = (
                    f"{top['player_name']} is leading the league for {metric_label} {timeframe} with {top['metric_value']}."
                )

        if plan.intent == "team_overview":
            team_stats = data.get("team_stats", {})
            team_players = data.get("team_player_stats", [])
            if team_stats:
                for stat_name in ("xG", "xGA", "ppda"):
                    if stat_name in team_stats:
                        reasons.append(f"{plan.team_name} has {stat_name} data available for evidence-backed analysis.")
                        break
            if team_players:
                top_scorer = max(team_players, key=lambda row: float(row.get("goals", 0)))
                reasons.append(
                    f"{top_scorer.get('player_name')} leads {plan.team_name} in the filtered player table with {top_scorer.get('goals')} goals."
                )
                xg_for = self._safe_get_metric(team_stats, "xG")
                xg_against = self._safe_get_metric(team_stats, "xGA")
                direct_answer = (
                    f"{plan.team_name} look analyzable {timeframe}: they have team-level Understat data"
                    f"{f' with xG {xg_for}' if xg_for is not None else ''}"
                    f"{f' and xGA {xg_against}' if xg_against is not None else ''}, "
                    f"and {top_scorer.get('player_name')} leads the squad on {top_scorer.get('goals')} goals."
                )
                social_caption = (
                    f"{plan.team_name} snapshot {timeframe}: "
                    f"{top_scorer.get('player_name')} leads the team with {top_scorer.get('goals')} goals."
                )

        if plan.intent in {"player_overview", "player_shots", "player_compare"}:
            player_data = data.get("player_data", {})
            player_core = player_data.get("player", {})
            matches = data.get("player_matches") or data.get("player_matches_via_ajax") or []
            shots = data.get("player_shots", [])
            if player_core:
                reasons.append(
                    f"{player_core.get('name')} is listed by Understat with favorite position {player_core.get('favorite_position')}."
                )
            if matches:
                reasons.append(f"The fetched match log includes {len(matches)} matches, giving us a usable sample size.")
            if shots:
                reasons.append(f"The shot map contains {len(shots)} shots, which supports finishing and chance-quality analysis.")
            if player_core:
                goals = self._sum_metric(matches, "goals")
                xg = self._sum_metric(matches, "xG")
                assists = self._sum_metric(matches, "assists")
                minutes = self._sum_metric(matches, "time")
                overperformance = None if xg is None or goals is None else round(goals - xg, 2)
                over_text = ""
                if overperformance is not None:
                    if overperformance > 0:
                        over_text = f" That is {overperformance} goals above xG."
                    elif overperformance < 0:
                        over_text = f" That is {abs(overperformance)} goals below xG."
                    else:
                        over_text = " Goals and xG are roughly level."
                direct_answer = (
                    f"{player_core.get('name')} has {self._fmt_num(goals)} goals, {self._fmt_num(assists)} assists, "
                    f"and {self._fmt_num(xg)} xG across {len(matches)} matches and {self._fmt_num(minutes, digits=0)} minutes {timeframe}."
                    f"{over_text}"
                )
                social_caption = (
                    f"{player_core.get('name')} {timeframe}: {self._fmt_num(goals)} goals, "
                    f"{self._fmt_num(xg)} xG, {self._fmt_num(assists)} assists in {len(matches)} matches."
                )
            if plan.intent == "player_compare" and "comparison_player_data" in data:
                comparison_core = data["comparison_player_data"].get("player", {})
                comparison_matches = data.get("comparison_player_matches", [])
                base_summary = self._player_summary(matches)
                comparison_summary = self._player_summary(comparison_matches)
                direct_answer = (
                    f"{player_core.get('name')} vs {comparison_core.get('name')} {timeframe}: "
                    f"{player_core.get('name')} has {base_summary['goals']} goals, {base_summary['xg']} xG, {base_summary['assists']} assists, "
                    f"and {base_summary['goal_contrib_per90']} goal contributions per 90 in {base_summary['matches']} matches; "
                    f"{comparison_core.get('name')} has {comparison_summary['goals']} goals, {comparison_summary['xg']} xG, "
                    f"{comparison_summary['assists']} assists, and {comparison_summary['goal_contrib_per90']} goal contributions per 90 in {comparison_summary['matches']} matches."
                )
                reasons.append(
                    f"{player_core.get('name')} goal-xG gap is {base_summary['goal_xg_gap']:+.2f}, while {comparison_core.get('name')} is at {comparison_summary['goal_xg_gap']:+.2f}."
                )
                reasons.append(
                    f"{player_core.get('name')} average shot quality is {base_summary['xg_per_shot']}, while {comparison_core.get('name')} is at {comparison_summary['xg_per_shot']}."
                )
                social_caption = direct_answer

        if not reasons:
            reasons.append("The planner fetched the relevant Understat data, but this question needs a more specific analysis template.")
        if not direct_answer:
            direct_answer = "I found the relevant Understat data, but this question still needs a more specific analysis template."
        if not social_caption:
            social_caption = direct_answer

        return {
            "question": plan.question,
            "intent": plan.intent,
            "direct_answer": direct_answer,
            "caveat": self._build_caveat(plan, data),
            "resolved_entities": {
                "league_name": plan.league_name,
                "team_name": plan.team_name,
                "comparison_team_name": plan.comparison_team_name,
                "coach_name": plan.coach_name,
                "comparison_coach_name": plan.comparison_coach_name,
                "player_name": plan.player_name,
                "player_id": plan.player_id,
                "comparison_player_name": plan.comparison_player_name,
                "comparison_player_id": plan.comparison_player_id,
                "metric": plan.metric,
                "season": plan.season,
                "start_date": plan.start_date,
                "end_date": plan.end_date,
            },
            "reasons": reasons,
            "social_ready": self._build_social_payload(plan, direct_answer, reasons, social_caption, viz_context),
            "next_step": "Use this as the assistant-facing answer scaffold when the user asks football questions here.",
        }

    def _filter_rows_by_date(self, rows, start_date=None, end_date=None):
        if not start_date and not end_date:
            return rows

        filtered = []
        for row in rows:
            row_date = self._row_date_value(row)
            if not row_date:
                filtered.append(row)
                continue

            current = row_date[:10]
            if start_date and current < start_date:
                continue
            if end_date and current > end_date:
                continue
            filtered.append(row)

        return filtered

    def _filter_player_rows(self, rows, season=None, start_date=None, end_date=None):
        filtered = rows
        if season is not None:
            filtered = [
                row for row in filtered
                if str(row.get("season", season)) == str(season)
            ]

        return self._filter_rows_by_date(
            filtered,
            start_date=start_date,
            end_date=end_date,
        )

    def _sum_metric(self, rows, key):
        if not rows:
            return 0
        total = 0.0
        for row in rows:
            try:
                total += float(row.get(key, 0))
            except (TypeError, ValueError):
                continue
        return round(total, 2)

    def _fmt_num(self, value, digits=2):
        if value is None:
            return "N/A"
        if digits == 0:
            return str(int(round(value)))
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.{digits}f}"

    def _safe_get_metric(self, payload, key):
        value = payload.get(key)
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _describe_timeframe(self, plan: PlannedQuestion):
        if plan.start_date and plan.end_date:
            return f"from {plan.start_date} to {plan.end_date}"
        if plan.start_date:
            return f"since {plan.start_date}"
        if plan.season:
            return f"in the {plan.season}/{plan.season + 1} Understat season"
        return "in the selected timeframe"

    def _build_hook(self, plan: PlannedQuestion, direct_answer: str):
        if plan.intent == "team_chance_profile" and plan.team_name:
            return f"Where does {plan.team_name}'s chance creation really come from?"
        if plan.intent == "team_defensive_trend" and plan.team_name:
            return f"Is {plan.team_name}'s defending actually improving?"
        if plan.intent == "team_window_compare" and plan.team_name:
            return f"How different do {plan.team_name}'s first and last windows look?"
        if plan.intent == "coach_compare" and plan.coach_name and plan.comparison_coach_name:
            return f"Which coach had the stronger underlying numbers: {plan.coach_name} or {plan.comparison_coach_name}?"
        if plan.intent == "coach_timeline" and plan.coach_name and plan.team_name:
            return f"What has {plan.team_name} looked like under {plan.coach_name}?"
        if plan.intent == "team_compare" and plan.team_name and plan.comparison_team_name:
            return f"Which side has the stronger underlying process: {plan.team_name} or {plan.comparison_team_name}?"
        if plan.intent == "team_player_ranking" and plan.team_name and plan.metric:
            return f"Who is really leading {plan.team_name} for {self._humanize_metric(plan.metric)}?"
        if plan.intent == "team_attack_defense" and plan.team_name:
            return f"How balanced are {plan.team_name} between attack and defense?"
        if plan.intent == "process_vs_results":
            return f"Which teams are getting results that do not match the process?"
        if plan.intent == "player_ranking" and plan.metric:
            return f"Who is really leading the league for {self._humanize_metric(plan.metric)}?"
        if plan.intent == "team_position_trend" and plan.team_name:
            return f"How has {plan.team_name}'s table position shifted across the season?"
        if plan.intent == "team_recent_form" and plan.team_name:
            return f"How strong has {plan.team_name}'s recent form really been?"
        if plan.player_name:
            return f"How good has {plan.player_name} really been?"
        if plan.team_name:
            return f"What do the Understat numbers say about {plan.team_name}?"
        if plan.league_name:
            return f"Quick Understat read on {plan.league_name}."
        return direct_answer

    def _rank_players(self, rows, metric):
        ranked = []
        for row in rows:
            minutes = float(row.get("time", 0) or 0)
            if minutes < 450:
                continue

            if metric == "finishing":
                value = round(float(row.get("goals", 0)) - float(row.get("xG", 0) or 0), 2)
                label = "goals minus xG"
            elif metric == "creativity":
                value = round(float(row.get("xA", 0) or 0), 2)
                label = "xA"
            elif metric == "shot_quality":
                shots = float(row.get("shots", 0) or 0)
                xg = float(row.get("xG", 0) or 0)
                value = round(0 if shots == 0 else xg / shots, 3)
                label = "xG per shot"
            else:
                value = round(float(row.get("goals", 0) or 0), 2)
                label = "goals"

            ranked.append(
                {
                    "player_name": row.get("player_name"),
                    "team_title": row.get("team_title"),
                    "metric_value": value,
                    "metric_label": label,
                }
            )

        return sorted(ranked, key=lambda item: item["metric_value"], reverse=True)

    def _player_summary(self, matches):
        goals = self._sum_metric(matches, "goals")
        xg = self._sum_metric(matches, "xG")
        assists = self._sum_metric(matches, "assists")
        minutes = self._sum_metric(matches, "time")
        shots = self._sum_metric(matches, "shots")
        goal_contrib = goals + assists
        goal_contrib_per90 = 0 if minutes == 0 else round(goal_contrib * 90 / minutes, 2)
        xg_per_shot = 0 if shots == 0 else round(xg / shots, 3)
        return {
            "goals": self._fmt_num(goals),
            "xg": self._fmt_num(xg),
            "assists": self._fmt_num(assists),
            "matches": len(matches),
            "goal_xg_gap": round(goals - xg, 2),
            "goal_contrib_per90": self._fmt_num(goal_contrib_per90),
            "xg_per_shot": self._fmt_num(xg_per_shot, digits=3),
        }

    def _recent_window_from_metric(self, metric):
        if not metric or not metric.startswith("recent_"):
            return None
        try:
            return int(metric.split("_", 1)[1])
        except (TypeError, ValueError):
            return None

    def _league_process_vs_results_rows(self, table):
        if not table or len(table) <= 1:
            return []

        rows = []
        for row in table[1:]:
            try:
                goals_for = float(row[5])
                goals_against = float(row[6])
                points = float(row[7])
                xg = float(row[8])
                xga = float(row[10])
                xpts = float(row[17])
            except (TypeError, ValueError, IndexError):
                continue

            rows.append(
                {
                    "team": row[0],
                    "points": points,
                    "xpts": xpts,
                    "points_gap": round(points - xpts, 2),
                    "goals": goals_for,
                    "xg": xg,
                    "finishing_gap": round(goals_for - xg, 2),
                    "goals_against": goals_against,
                    "xga": xga,
                    "defensive_prevention_gap": round(xga - goals_against, 2),
                }
            )

        return rows

    def _template_metadata(self, plan: PlannedQuestion, answer: dict):
        template_name = {
            "coach_timeline": "coach_timeline",
            "coach_compare": "coach_comparison",
            "process_vs_results": "process_vs_results",
            "player_ranking": "league_player_ranking",
            "team_compare": "team_comparison",
            "team_window_compare": "team_window_comparison",
            "team_defensive_trend": "team_defensive_trend",
            "team_chance_profile": "team_chance_profile",
            "team_player_ranking": "team_player_ranking",
            "team_attack_defense": "team_attack_defense",
            "team_xpts_gap": "league_xpts_gap",
            "player_compare": "player_comparison",
            "team_position_trend": "team_position_trend",
            "team_recent_form": "team_recent_form",
            "player_overview": "player_overview",
            "team_overview": "team_overview",
            "league_table": "league_table",
        }.get(plan.intent, "generic_analysis")

        return {
            "name": template_name,
            "intent": plan.intent,
            "metric": plan.metric,
            "question_style": "analytical",
            "assistant_usage": "Use this template structure when answering similar football analytics questions in chat.",
            "fields": sorted(list(answer.keys())),
        }

    def _sort_rows_by_date(self, rows, descending=False):
        if not rows:
            return rows

        dated_rows = [row for row in rows if self._row_date_value(row)]
        undated_rows = [row for row in rows if not self._row_date_value(row)]

        if not dated_rows:
            return rows

        dated_rows = sorted(
            dated_rows,
            key=lambda row: self._row_date_value(row),
            reverse=descending,
        )
        return dated_rows + undated_rows

    def _row_date_value(self, row):
        value = row.get("date") or row.get("datetime") or ""
        return value[:19]

    def _team_results_summary(self, rows):
        summary = {
            "points": 0,
            "goals_for": 0,
            "goals_against": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
        }

        for row in rows:
            summary["points"] += self._team_result_points(row)
            goals_for, goals_against = self._team_result_scoreline(row)
            summary["goals_for"] += goals_for
            summary["goals_against"] += goals_against
            result = row.get("result")
            if result == "w":
                summary["wins"] += 1
            elif result == "d":
                summary["draws"] += 1
            elif result == "l":
                summary["losses"] += 1

        summary["xg"] = self._sum_team_result_xg(rows, for_team=True)
        summary["xga"] = self._sum_team_result_xg(rows, for_team=False)

        return summary

    def _team_result_sequence(self, rows):
        sequence = []
        for row in reversed(rows):
            result = str(row.get("result", "")).upper()
            if result in {"W", "D", "L"}:
                sequence.append(result)
        return sequence

    def _team_result_points(self, row):
        if row.get("pts") is not None:
            return int(row.get("pts", 0))

        result = row.get("result")
        if result == "w":
            return 3
        if result == "d":
            return 1
        return 0

    def _team_result_scoreline(self, row):
        if row.get("scored") is not None or row.get("missed") is not None:
            return int(row.get("scored", 0)), int(row.get("missed", 0))

        goals = row.get("goals", {})
        side = row.get("side")
        if side == "h":
            return int(goals.get("h", 0)), int(goals.get("a", 0))
        if side == "a":
            return int(goals.get("a", 0)), int(goals.get("h", 0))
        return 0, 0

    def _team_position_progression(self, league_data: dict, team_name: str):
        teams = league_data.get("teams", {})
        histories = {
            team_data.get("title"): team_data.get("history", [])
            for team_data in teams.values()
        }
        if team_name not in histories:
            return []

        max_week = max((len(history) for history in histories.values()), default=0)
        progression = []

        for week in range(1, max_week + 1):
            rows = []
            for current_team, history in histories.items():
                slice_history = history[:week]
                pts = sum(match.get("pts", 0) for match in slice_history)
                goals_for = sum(match.get("scored", 0) for match in slice_history)
                goals_against = sum(match.get("missed", 0) for match in slice_history)
                rows.append(
                    {
                        "team": current_team,
                        "pts": pts,
                        "gd": goals_for - goals_against,
                        "gf": goals_for,
                    }
                )

            ranked = sorted(
                rows,
                key=lambda row: (-row["pts"], -row["gd"], -row["gf"], row["team"]),
            )
            for position, row in enumerate(ranked, start=1):
                if row["team"] == team_name:
                    progression.append({"week": week, "position": position, "points": row["pts"]})
                    break

        return progression

    def _find_team_table_row(self, table, team_name: str | None):
        if not table or not team_name:
            return None

        for row in table[1:]:
            if str(row[0]).lower() == team_name.lower():
                return row
        return None

    def _team_table_profile(self, row):
        return {
            "team": row[0],
            "xg": float(row[8]),
            "xga": float(row[10]),
            "npxgd": float(row[12]),
            "points": float(row[7]),
            "xpts": float(row[17]),
        }

    def _humanize_metric(self, metric: str | None):
        if metric is None:
            return None
        return {
            "xpts_gap": "xPTS gap",
            "table_position": "table position",
            "finishing": "finishing",
            "creativity": "creativity",
            "shot_quality": "shot quality",
            "attack_defense": "attack and defense",
            "goals": "goals",
            "xg": "xG",
            "process_vs_results": "process vs results",
        }.get(metric, metric.replace("_", " "))

    def _build_caveat(self, plan: PlannedQuestion, data: dict):
        if plan.intent in {"player_compare", "player_overview"}:
            matches = data.get("player_matches") or data.get("player_matches_via_ajax") or []
            if matches and len(matches) < 5:
                return "Small sample warning: this answer is built from fewer than five matches."
        if plan.intent in {"team_recent_form", "team_attack_defense", "team_compare"}:
            rows = data.get("team_results", [])
            if rows and len(rows) < 5:
                return "Small sample warning: the recent-form layer is based on fewer than five results."
        return None

    def _build_social_payload(self, plan: PlannedQuestion, direct_answer: str, reasons: list[str], social_caption: str, viz_context: dict | None = None):
        hook = self._build_hook(plan, direct_answer)
        stat_lines = reasons[:3]
        carousel_cards = self._build_carousel_cards(plan, direct_answer, stat_lines)
        visualizations = self._build_visualization_payload(plan, stat_lines, viz_context or {})
        visualizations = self._attach_visual_template_status(visualizations)
        return {
            "hook": hook,
            "caption": social_caption,
            "x_post": f"{hook} {social_caption}",
            "x_thread": [hook, social_caption, *stat_lines],
            "instagram_caption": f"{hook}\n\n{social_caption}\n\nKey points: " + " | ".join(stat_lines),
            "stat_lines": stat_lines,
            "instagram_carousel": carousel_cards,
            "visualizations": visualizations,
        }

    def _attach_visual_template_status(self, visualization_payload: dict):
        template_name = visualization_payload.get("template")
        if not template_name:
            visualization_payload["template_status"] = "unregistered"
            return visualization_payload

        template_metadata = VISUAL_TEMPLATE_REGISTRY.get(template_name)
        if not template_metadata:
            visualization_payload["template_status"] = "unregistered"
            return visualization_payload

        visualization_payload["template_status"] = template_metadata["status"]
        visualization_payload["template_notes"] = template_metadata["notes"]
        visualization_payload["template_requirements"] = template_metadata["requirements"]
        return visualization_payload

    def _find_coach_era_by_name(self, coach_name: str | None, team_name: str | None = None):
        if coach_name is None:
            return None
        for era in find_coach_eras(coach_name.lower()):
            if era.coach_name == coach_name and (team_name is None or era.team_name == team_name):
                return era
        return None

    def _default_coach_season(self, eras):
        if not eras:
            return None
        shared = None
        for era in eras:
            seasons = set(self._coach_covered_seasons(era))
            shared = seasons if shared is None else shared & seasons
        if shared:
            return max(shared)
        return max(self._coach_covered_seasons(eras[0]))

    def _coach_covered_seasons(self, era):
        end_date = era.end_date or CURRENT_DATE.isoformat()
        start_season = self._season_from_date(era.start_date)
        end_season = self._season_from_date(end_date)
        return list(range(start_season, end_season + 1))

    def _season_from_date(self, date_string: str):
        year, month, _ = (int(part) for part in date_string.split("-"))
        return year if month >= 7 else year - 1

    def _coach_window_for_season(self, era, season: int):
        season_start = f"{season}-07-01"
        season_end = f"{season + 1}-06-30"
        era_end = era.end_date or CURRENT_DATE.isoformat()
        start_date = max(era.start_date, season_start)
        end_date = min(era_end, season_end)
        if start_date > end_date:
            return None
        return start_date, end_date

    def _team_bundle_summary(self, bundle: dict, team_name: str | None):
        table_row = self._find_team_table_row(bundle.get("league_table", []), team_name)
        if not table_row:
            return None

        results = bundle.get("team_results", [])
        summary = self._team_results_summary(results)
        player_rows = bundle.get("team_player_stats", [])
        top_scorer = max(player_rows, key=lambda row: float(row.get("goals", 0))) if player_rows else None
        top_creator = max(player_rows, key=lambda row: float(row.get("xA", 0) or 0)) if player_rows else None
        matches = len(results)
        ppg = 0 if matches == 0 else round(summary["points"] / matches, 2)

        return {
            "matches": matches,
            "points": summary["points"],
            "ppg": self._fmt_num(ppg),
            "goals_for": summary["goals_for"],
            "goals_against": summary["goals_against"],
            "xg": float(table_row[8]),
            "xga": float(table_row[10]),
            "top_scorer": top_scorer.get("player_name") if top_scorer else None,
            "top_scorer_goals": self._fmt_num(float(top_scorer.get("goals", 0))) if top_scorer else None,
            "top_creator": top_creator.get("player_name") if top_creator else None,
            "top_creator_xa": self._fmt_num(float(top_creator.get("xA", 0) or 0)) if top_creator else None,
        }

    def _format_window(self, window):
        if not window:
            return "in the selected window"
        return f"from {window[0]} to {window[1]}"

    def _window_compare_size(self, metric: str | None):
        if not metric or not metric.startswith("window_compare_"):
            return None
        try:
            return int(metric.split("_")[-1])
        except (TypeError, ValueError):
            return None

    def _team_results_window_summary(self, rows):
        summary = self._team_results_summary(rows)
        matches = len(rows)
        xg = self._sum_team_result_xg(rows, for_team=True)
        xga = self._sum_team_result_xg(rows, for_team=False)
        shots_against = self._sum_team_result_shots(rows, for_team=False)
        return {
            **summary,
            "matches": matches,
            "ppg": 0 if matches == 0 else round(summary["points"] / matches, 2),
            "xg": xg,
            "xga": xga,
            "xg_per_game": 0 if matches == 0 else round(xg / matches, 2),
            "xga_per_game": 0 if matches == 0 else round(xga / matches, 2),
            "shots_against": shots_against,
        }

    def _sum_team_result_xg(self, rows, for_team=True):
        total = 0.0
        for row in rows:
            xg = row.get("xG", {})
            side = row.get("side")
            if not isinstance(xg, dict) or side not in {"h", "a"}:
                continue
            key = side if for_team else ("a" if side == "h" else "h")
            total += float(xg.get(key, 0) or 0)
        return round(total, 2)

    def _sum_team_result_shots(self, rows, for_team=True):
        total = 0
        found = False
        for row in rows:
            shots = row.get("shots", {})
            side = row.get("side")
            if not isinstance(shots, dict) or not shots or side not in {"h", "a"}:
                continue
            found = True
            key = side if for_team else ("a" if side == "h" else "h")
            total += int(shots.get(key, 0) or 0)
        return total if found else None

    def _trend_label(self, current, previous, lower_is_better=False):
        if current == previous:
            return "stable"
        if lower_is_better:
            return "improving" if current < previous else "regressing"
        return "improving" if current > previous else "regressing"

    def _team_chance_profile(self, team_stats: dict):
        if not team_stats:
            return None

        situation = self._top_team_stats_entry(team_stats.get("situation", {}), metric_key="xG")
        zone = self._top_team_stats_entry(team_stats.get("shotZone", {}), metric_key="shots")
        speed = self._top_team_stats_entry(team_stats.get("attackSpeed", {}), metric_key="xG")
        timing = self._top_team_stats_entry(team_stats.get("timing", {}), metric_key="xG")
        if not all((situation, zone, speed, timing)):
            return None
        return {
            "top_situation": situation,
            "top_zone": zone,
            "top_speed": speed,
            "top_timing": timing,
        }

    def _top_team_stats_entry(self, category_stats: dict, metric_key: str):
        if not category_stats:
            return None
        ranked = []
        for label, payload in category_stats.items():
            try:
                ranked.append(
                    {
                        "label": label,
                        "shots": int(payload.get("shots", 0) or 0),
                        "goals": int(payload.get("goals", 0) or 0),
                        "xg": float(payload.get("xG", 0) or 0),
                        "metric": float(payload.get(metric_key, 0) or 0),
                    }
                )
            except (TypeError, ValueError, AttributeError):
                continue
        if not ranked:
            return None
        return max(ranked, key=lambda item: item["metric"])

    def _build_carousel_cards(self, plan: PlannedQuestion, direct_answer: str, stat_lines: list[str]):
        cards = [
            {"title": "Main Takeaway", "body": direct_answer},
        ]
        for idx, line in enumerate(stat_lines[:3], start=2):
            cards.append({"title": f"Key Stat {idx - 1}", "body": line})
        return cards

    def _team_compare_headline(self, viz_context: dict):
        categories = viz_context.get("categories", [])
        series = viz_context.get("series", {})
        if len(categories) < 2:
            return "Recent form comparison"

        left_team, right_team = categories[:2]
        left_points = float(series.get("points_last_5", [0, 0])[0] or 0)
        right_points = float(series.get("points_last_5", [0, 0])[1] or 0)
        left_xga = float(series.get("xga_last_5", [0, 0])[0] or 0)
        right_xga = float(series.get("xga_last_5", [0, 0])[1] or 0)

        if left_points > right_points:
            return f"{left_team} have the stronger recent league form"
        if right_points > left_points:
            return f"{right_team} have the stronger recent league form"
        if left_xga < right_xga:
            return f"{left_team} edge it on defensive control"
        if right_xga < left_xga:
            return f"{right_team} edge it on defensive control"
        return f"{left_team} and {right_team} are level on recent form"

    def _team_compare_cards(self, viz_context: dict):
        categories = viz_context.get("categories", [])
        series = viz_context.get("series", {})
        records = viz_context.get("records", {})
        result_sequences = viz_context.get("result_sequences", {})
        metric_map = [
            ("goals_for_last_5", "Goals Scored"),
            ("goals_against_last_5", "Goals Conceded"),
            ("xg_last_5", "Expected Goals"),
            ("xga_last_5", "Expected Goals Against"),
        ]
        cards = []

        for index, team_name in enumerate(categories[:2]):
            palette = self._team_palette(team_name, index=index)
            points = float(series.get("points_last_5", [0, 0])[index] or 0)
            team_metrics = []

            for metric_key, metric_label in metric_map:
                values = series.get(metric_key, [0, 0])
                current_value = float(values[index] or 0)
                maximum = max([float(value or 0) for value in values] + [1.0])
                team_metrics.append(
                    {
                        "label": metric_label,
                        "value": self._fmt_num(current_value),
                        "ratio": round(current_value / maximum, 4),
                    }
                )

            cards.append(
                {
                    "name": team_name,
                    "short_name": self._team_abbreviation(team_name),
                    "accent": palette["accent"],
                    "accent_soft": palette["accent_soft"],
                    "points": self._fmt_num(points),
                    "record": records.get(team_name, "-"),
                    "results": result_sequences.get(team_name, []),
                    "metrics": team_metrics,
                    "summary": f"{records.get(team_name, '-')} | {self._fmt_num(points)} pts",
                }
            )

        return cards

    def _team_abbreviation(self, team_name: str | None):
        if not team_name:
            return "TEAM"

        abbreviations = {
            "Manchester United": "MUN",
            "Manchester City": "MCI",
            "Arsenal": "ARS",
            "Liverpool": "LIV",
            "Chelsea": "CHE",
            "Tottenham": "TOT",
            "Newcastle United": "NEW",
            "Aston Villa": "AVL",
            "Brighton": "BHA",
            "West Ham": "WHU",
        }
        if team_name in abbreviations:
            return abbreviations[team_name]

        parts = [part for part in str(team_name).replace("_", " ").split() if part]
        if len(parts) == 1:
            return parts[0][:3].upper()
        return "".join(part[0] for part in parts[:3]).upper()

    def _team_palette(self, team_name: str | None, index: int = 0):
        palettes = {
            "Manchester United": {"accent": "#C8102E", "accent_soft": "#F59E0B"},
            "Arsenal": {"accent": "#EF4444", "accent_soft": "#3B82F6"},
            "Liverpool": {"accent": "#DC2626", "accent_soft": "#10B981"},
            "Chelsea": {"accent": "#2563EB", "accent_soft": "#F59E0B"},
            "Manchester City": {"accent": "#38BDF8", "accent_soft": "#F8FAFC"},
            "Tottenham": {"accent": "#E2E8F0", "accent_soft": "#60A5FA"},
            "Newcastle United": {"accent": "#F8FAFC", "accent_soft": "#94A3B8"},
            "Aston Villa": {"accent": "#8B5CF6", "accent_soft": "#F472B6"},
        }
        if team_name in palettes:
            return palettes[team_name]
        fallback = [
            {"accent": "#E76F51", "accent_soft": "#F4A261"},
            {"accent": "#2A9D8F", "accent_soft": "#84CC16"},
        ]
        return fallback[index % len(fallback)]

    def _build_visualization_payload(self, plan: PlannedQuestion, stat_lines: list[str], viz_context: dict):
        if plan.intent == "team_window_compare":
            return {
                "framework": "echarts",
                "chart_type": "grouped_bar",
                "title": f"{plan.team_name}: first vs last window",
                "series": ["points_per_game", "xg_per_game", "xga_per_game"],
                "card_type": "before_after_comparison",
                "stat_lines": stat_lines,
                "echarts_option": self._build_echarts_option(
                    chart_type="grouped_bar",
                    title=f"{plan.team_name}: first vs last window",
                    categories=viz_context.get("categories", []),
                    series=viz_context.get("series", {}),
                ),
            }
        if plan.intent == "team_compare":
            return {
                "framework": "custom_svg",
                "render_mode": "custom_svg",
                "template": "premium_team_compare_v1",
                "chart_type": "comparison_bar",
                "title": f"{plan.team_name} vs {plan.comparison_team_name}: recent form",
                "series": list(viz_context.get("series", {}).keys()),
                "card_type": "team_form_comparison",
                "stat_lines": stat_lines,
                "record_labels": viz_context.get("records", {}),
                "headline": self._team_compare_headline(viz_context),
                "kicker": "FORM CHECK",
                "subtitle": "Last 5 league matches | points, W-D-L, goals, xG, xGA",
                "footer": "Data source: Understat | Window: latest 5 league matches",
                "teams": self._team_compare_cards(viz_context),
            }
        if plan.intent == "team_defensive_trend":
            return {
                "framework": "echarts",
                "chart_type": "line",
                "title": f"{plan.team_name}: defensive trend",
                "series": ["xga_per_game", "goals_against"],
                "card_type": "trend_card",
                "stat_lines": stat_lines,
                "echarts_option": self._build_echarts_option(
                    chart_type="line",
                    title=f"{plan.team_name}: defensive trend",
                    categories=viz_context.get("categories", []),
                    series=viz_context.get("series", {}),
                ),
            }
        if plan.intent == "team_chance_profile":
            return {
                "framework": "echarts",
                "chart_type": "stacked_bar",
                "title": f"{plan.team_name}: chance profile",
                "series": ["xg", "shots"],
                "card_type": "profile_card",
                "stat_lines": stat_lines,
                "echarts_option": self._build_echarts_option(
                    chart_type="stacked_bar",
                    title=f"{plan.team_name}: chance profile",
                    categories=viz_context.get("categories", []),
                    series=viz_context.get("series", {}),
                ),
            }
        if plan.intent == "process_vs_results":
            return {
                "framework": "custom_svg",
                "render_mode": "custom_svg",
                "template": "process_vs_results_lens_v1",
                "chart_type": "grouped_bar",
                "title": f"{plan.league_name or 'League'}: process vs results",
                "headline": "Results are not always process",
                "subtitle": f"{plan.league_name or 'League'} {plan.season}: points vs xPTS, finishing, defensive variance",
                "kicker": "PROCESS VS RESULTS",
                "footer": "Data source: Understat | Positive xGA-GA means conceding fewer than expected",
                "series": ["points_minus_xpts", "goals_minus_xg", "xga_minus_goals_against"],
                "card_type": "process_vs_results_lens",
                "categories": viz_context.get("categories", []),
                "metric_series": viz_context.get("series", {}),
                "stat_lines": stat_lines,
                "rankings": viz_context.get("rankings", {}),
                "echarts_option": self._build_echarts_option(
                    chart_type="grouped_bar",
                    title=f"{plan.league_name or 'League'}: process vs results",
                    categories=viz_context.get("categories", []),
                    series=viz_context.get("series", {}),
                ),
            }
        return {
            "framework": "echarts",
            "chart_type": "stat_card",
            "title": plan.question,
            "series": [],
            "card_type": "summary_card",
            "stat_lines": stat_lines,
            "echarts_option": self._build_echarts_option(
                chart_type="stat_card",
                title=plan.question,
                categories=[],
                series={},
                stat_lines=stat_lines,
            ),
        }

    def _build_echarts_option(self, chart_type: str, title: str, categories: list[str], series: dict, stat_lines: list[str] | None = None, extra: dict | None = None):
        palette = ["#111827", "#E76F51", "#2A9D8F", "#E9C46A", "#264653"]
        base = {
            "backgroundColor": "#F7F3EA",
            "title": {
                "text": title,
                "left": 20,
                "top": 16,
                "textStyle": {
                    "color": "#111827",
                    "fontFamily": "Georgia, Times New Roman, serif",
                    "fontSize": 18,
                    "fontWeight": "bold",
                },
            },
            "color": palette[1:],
            "grid": {"left": 48, "right": 24, "top": 72, "bottom": 44},
            "tooltip": {"trigger": "axis"},
        }

        if chart_type == "grouped_bar":
            base.update(
                {
                    "legend": {"top": 42},
                    "xAxis": {"type": "category", "data": categories},
                    "yAxis": {"type": "value"},
                    "series": [
                        {"name": name, "type": "bar", "data": values, "barMaxWidth": 26}
                        for name, values in series.items()
                    ],
                }
            )
            return base

        if chart_type == "line":
            base.update(
                {
                    "legend": {"top": 42},
                    "xAxis": {"type": "category", "data": categories},
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "name": name,
                            "type": "line",
                            "data": values,
                            "smooth": True,
                            "symbolSize": 10,
                            "lineStyle": {"width": 4},
                        }
                        for name, values in series.items()
                    ],
                }
            )
            return base

        if chart_type == "comparison_bar":
            left_team, right_team = categories
            left_color = "#FF6B57"
            right_color = "#2EC4B6"
            ink = "#F8F4EC"
            muted = "#94A3B8"
            card_bg = "#101826"
            track = "#1E293B"
            metrics = [
                ("goals_for_last_5", "Goals Scored"),
                ("goals_against_last_5", "Goals Conceded"),
                ("xg_last_5", "Expected Goals"),
                ("xga_last_5", "Expected Goals Against"),
            ]
            left_values = {key: series.get(key, [0, 0])[0] for key, _ in metrics}
            right_values = {key: series.get(key, [0, 0])[1] for key, _ in metrics}
            left_points = float(series.get("points_last_5", [0, 0])[0])
            right_points = float(series.get("points_last_5", [0, 0])[1])

            if left_points > right_points:
                verdict = f"{left_team} have the stronger recent form"
            elif right_points > left_points:
                verdict = f"{right_team} have the stronger recent form"
            else:
                verdict = "Recent form is level on points"

            def metric_max(key):
                return max(float(left_values[key]), float(right_values[key]), 1)

            def format_metric_value(value):
                value = float(value)
                return f"{value:.2f}" if not value.is_integer() else str(int(value))

            def metric_row(x, y, width, label, value, maximum, color):
                fill_width = max(24, (float(value) / maximum) * width)
                return [
                    {
                        "type": "text",
                        "left": x,
                        "top": y - 4,
                        "style": {
                            "text": label,
                            "fill": muted,
                            "font": "12px Helvetica Neue, Arial, sans-serif",
                        },
                    },
                    {
                        "type": "text",
                        "left": x + width + 12,
                        "top": y - 7,
                        "style": {
                            "text": format_metric_value(value),
                            "fill": ink,
                            "font": "bold 13px Helvetica Neue, Arial, sans-serif",
                        },
                    },
                    {
                        "type": "rect",
                        "shape": {"x": x, "y": y + 18, "width": width, "height": 10, "r": 5},
                        "style": {"fill": track},
                    },
                    {
                        "type": "rect",
                        "shape": {"x": x, "y": y + 18, "width": fill_width, "height": 10, "r": 5},
                        "style": {"fill": color},
                    },
                ]

            graphics = [
                {"type": "rect", "shape": {"x": 0, "y": 0, "width": 1200, "height": 675}, "style": {"fill": "#07101B"}},
                {"type": "rect", "shape": {"x": 36, "y": 26, "width": 1128, "height": 623, "r": 30}, "style": {"fill": "#0B1523"}},
                {"type": "rect", "shape": {"x": 80, "y": 58, "width": 196, "height": 28, "r": 14}, "style": {"fill": "#172235"}},
                {"type": "text", "left": 100, "top": 64, "style": {"text": "SOCIAL READY FORM CARD", "fill": "#D7DEE9", "font": "700 12px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 80, "top": 104, "style": {"text": "MANCHESTER UNITED VS ARSENAL", "fill": ink, "font": "700 34px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 82, "top": 148, "style": {"text": "LAST 5 LEAGUE MATCHES | POINTS, W-D-L, GF, GA, XG, XGA", "fill": muted, "font": "13px Helvetica Neue, Arial, sans-serif"}},
                {"type": "rect", "shape": {"x": 80, "y": 182, "width": 364, "height": 44, "r": 22}, "style": {"fill": "#121E2F"}},
                {"type": "text", "left": 102, "top": 194, "style": {"text": verdict.upper(), "fill": ink, "font": "700 15px Helvetica Neue, Arial, sans-serif"}},
                {"type": "rect", "shape": {"x": 78, "y": 256, "width": 492, "height": 302, "r": 28}, "style": {"fill": card_bg, "stroke": "#1F2937", "lineWidth": 1}},
                {"type": "rect", "shape": {"x": 630, "y": 256, "width": 492, "height": 302, "r": 28}, "style": {"fill": card_bg, "stroke": "#1F2937", "lineWidth": 1}},
                {"type": "circle", "shape": {"cx": 122, "cy": 292, "r": 8}, "style": {"fill": left_color}},
                {"type": "circle", "shape": {"cx": 674, "cy": 292, "r": 8}, "style": {"fill": right_color}},
                {"type": "text", "left": 144, "top": 278, "style": {"text": left_team.upper(), "fill": ink, "font": "700 26px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 696, "top": 278, "style": {"text": right_team.upper(), "fill": ink, "font": "700 26px Helvetica Neue, Arial, sans-serif"}},
                {"type": "rect", "shape": {"x": 110, "y": 324, "width": 132, "height": 34, "r": 17}, "style": {"fill": "#162334"}},
                {"type": "rect", "shape": {"x": 662, "y": 324, "width": 132, "height": 34, "r": 17}, "style": {"fill": "#162334"}},
                {"type": "text", "left": 127, "top": 333, "style": {"text": f"W-D-L {(extra or {}).get(left_team, '-')}", "fill": ink, "font": "700 13px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 679, "top": 333, "style": {"text": f"W-D-L {(extra or {}).get(right_team, '-')}", "fill": ink, "font": "700 13px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 110, "top": 390, "style": {"text": "POINTS IN LAST 5", "fill": muted, "font": "12px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 662, "top": 390, "style": {"text": "POINTS IN LAST 5", "fill": muted, "font": "12px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 110, "top": 412, "style": {"text": str(int(left_points)), "fill": left_color, "font": "700 60px Helvetica Neue, Arial, sans-serif"}},
                {"type": "text", "left": 662, "top": 412, "style": {"text": str(int(right_points)), "fill": right_color, "font": "700 60px Helvetica Neue, Arial, sans-serif"}},
            ]

            row_y_start = 446
            row_gap = 42
            for index, (metric_key, metric_label) in enumerate(metrics, start=0):
                y = row_y_start + (index * row_gap)
                graphics.extend(metric_row(110, y, 260, metric_label, left_values[metric_key], metric_max(metric_key), left_color))
                graphics.extend(metric_row(662, y, 260, metric_label, right_values[metric_key], metric_max(metric_key), right_color))

            graphics.extend(
                [
                    {"type": "text", "left": 80, "top": 606, "style": {"text": (stat_lines or [""])[0] if stat_lines else "", "fill": ink, "font": "14px Helvetica Neue, Arial, sans-serif"}},
                    {"type": "text", "left": 80, "top": 630, "style": {"text": (stat_lines or ["", ""])[1] if len(stat_lines) > 1 else "", "fill": muted, "font": "13px Helvetica Neue, Arial, sans-serif"}},
                ]
            )

            return {
                "backgroundColor": "#09111F",
                "animation": False,
                "graphic": graphics,
            }

        if chart_type == "stacked_bar":
            base.update(
                {
                    "legend": {"top": 42},
                    "xAxis": {"type": "category", "data": categories},
                    "yAxis": {"type": "value"},
                    "series": [
                        {
                            "name": name,
                            "type": "bar",
                            "data": values,
                            "stack": "total" if name == "xg" else None,
                            "barMaxWidth": 36,
                        }
                        for name, values in series.items()
                    ],
                }
            )
            return base

        return {
            **base,
            "graphic": [
                {
                    "type": "text",
                    "left": 20,
                    "top": 74,
                    "style": {
                        "text": "\n".join(stat_lines or []),
                        "fill": "#111827",
                        "font": "14px Georgia, Times New Roman, serif",
                        "lineHeight": 24,
                        "width": 700,
                    },
                }
            ],
        }

    def _summarize_data_shapes(self, data: dict):
        summary = {}
        for key, value in data.items():
            if isinstance(value, list):
                summary[key] = {"type": "list", "length": len(value)}
            elif isinstance(value, dict):
                summary[key] = {"type": "dict", "keys": sorted(list(value.keys()))[:10]}
            else:
                summary[key] = {"type": type(value).__name__}
        return summary
