from __future__ import annotations

from dataclasses import asdict
from datetime import date

from app.answers import build_answer, ANSWER_BUILDERS
from app.fetcher import Fetcher
from app.planner import Planner, PlannedQuestion
from app.stat_data import UnderstatData


class FootballQuestionAnswerer:
    """Orchestrates planning, fetching and answer composition for free-text questions."""

    __INTENT_TEMPLATES = {
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
    }

    def __init__(self, client=None, today: date | None = None):
        self.client = client or UnderstatData()
        self._owns_client = client is None
        self._today = today
        self._planner = Planner(client=self.client, today=today)
        self._fetcher = Fetcher(client=self.client, today=self.today.isoformat())

    @property
    def today(self) -> date:
        return self._today or date.today()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def close(self):
        if self._owns_client:
            await self.client.close()

    async def answer(self, question: str):
        plan = await self.plan(question)
        data = await self._fetcher.fetch(plan)
        answer = self._build_answer(plan, data)
        return {
            "plan": asdict(plan),
            "answer": answer,
            "data_summary": self._summarize_data_shapes(data),
            "template": self._template_metadata(plan, answer),
        }

    async def plan(self, question: str) -> PlannedQuestion:
        return await self._planner.plan(question)

    def _build_answer(self, plan: PlannedQuestion, data: dict) -> dict:
        reasons: list[str] = []
        direct_answer = ""
        social_caption = ""

        builder = ANSWER_BUILDERS.get(plan.intent)
        if builder is not None:
            payload = build_answer(plan, data)
            direct_answer = payload["direct_answer"]
            reasons = payload["reasons"]
            social_caption = payload["social_caption"]

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
            "share_copy": self._build_share_copy(plan, direct_answer, reasons, social_caption),
        }

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

    def _build_share_copy(self, plan: PlannedQuestion, direct_answer: str, reasons: list[str], social_caption: str):
        hook = self._build_hook(plan, direct_answer)
        stat_lines = reasons[:3]
        return {
            "hook": hook,
            "caption": social_caption,
            "x_post": f"{hook} {social_caption}",
            "x_thread": [hook, social_caption, *stat_lines],
            "instagram_caption": f"{hook}\n\n{social_caption}\n\nKey points: " + " | ".join(stat_lines),
            "stat_lines": stat_lines,
        }

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
            from app.answers._helpers import humanize_metric
            return f"Who is really leading {plan.team_name} for {humanize_metric(plan.metric)}?"
        if plan.intent == "team_attack_defense" and plan.team_name:
            return f"How balanced are {plan.team_name} between attack and defense?"
        if plan.intent == "process_vs_results":
            return f"Which teams are getting results that do not match the process?"
        if plan.intent == "player_ranking" and plan.metric:
            from app.answers._helpers import humanize_metric
            return f"Who is really leading the league for {humanize_metric(plan.metric)}?"
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

    def _template_metadata(self, plan: PlannedQuestion, answer: dict):
        template_name = self.__INTENT_TEMPLATES.get(plan.intent, "generic_analysis")
        return {
            "name": template_name,
            "intent": plan.intent,
            "metric": plan.metric,
            "question_style": "analytical",
            "assistant_usage": "Use this template structure when answering similar football analytics questions in chat.",
            "fields": sorted(list(answer.keys())),
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


FootballAnalyticsEngine = FootballQuestionAnswerer
