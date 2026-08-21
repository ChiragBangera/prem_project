from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ExternalEnrichment:
    source: str = "none"
    fetched_at: str | None = None
    market_value_eur: int | None = None
    contract_end: str | None = None
    foot: str | None = None
    height_cm: int | None = None
    sofascore_rating: float | None = None
    whoscored_rating: float | None = None
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    honest_note: str = "Enrichment not configured (Understat-only in this deploy)."
    # allow extra but keep spec


class EnrichmentProvider(Protocol):
    async def enrich_player(self, player_name: str, team_hint: str | None = None) -> ExternalEnrichment: ...

    async def enrich_team_squad(self, team_name: str, season: int) -> dict[str, ExternalEnrichment]: ...


class NoopEnrichmentProvider:
    async def enrich_player(self, player_name: str, team_hint: str | None = None) -> ExternalEnrichment:
        return ExternalEnrichment(
            source="none",
            fetched_at=None,
            market_value_eur=None,
            contract_end=None,
            foot=None,
            height_cm=None,
            sofascore_rating=None,
            whoscored_rating=None,
            strengths=[],
            weaknesses=[],
            honest_note="Enrichment not configured (Understat-only in this deploy).",
        )

    async def enrich_team_squad(self, team_name: str, season: int) -> dict[str, ExternalEnrichment]:
        return {}
