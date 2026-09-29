"""Insight primitives: a structured finding, formatting helpers, ranking.

An insight is one specific, evidence-backed sentence plus the numbers behind it
and a link to where the reader can dig in. Generators are pure functions over
analytics output; they never fetch. Two rules keep them honest:

* every threshold is expressed against noise (a z-score or a sample floor), so a
  small-sample blip is not presented as news;
* wording states what the numbers *say* ("scored 8 more than expected"), and
  hedges what they merely *suggest* ("tends to shrink").
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Iterable, Sequence

TONES = ("positive", "negative", "warning", "neutral", "info")


@dataclass
class Insight:
    id: str
    kind: str
    headline: str
    detail: str = ""
    tone: str = "neutral"
    score: float = 50.0
    confidence: str = "medium"  # high | medium | low (driven by sample size)
    evidence: list[dict] = field(default_factory=list)  # [{"label", "value"}]
    entities: list[dict] = field(default_factory=list)  # [{"type", "name", "id"?}]
    link: dict | None = None  # {"route": "team", "params": {...}}

    def to_dict(self) -> dict:
        data = asdict(self)
        data["score"] = round(self.score, 1)
        return data


def ev(label: str, value) -> dict:
    return {"label": label, "value": value if isinstance(value, str) else str(value)}


def team_link(team: str, **extra) -> dict:
    return {"route": "team", "params": {"team": team, **extra}}


def player_link(player_id: int, **extra) -> dict:
    return {"route": "player", "params": {"id": player_id, **extra}}


def match_link(match_id: int, **extra) -> dict:
    return {"route": "match", "params": {"id": match_id, **extra}}


# ---------------------------------------------------------------------- formatting


def f1(x: float) -> str:
    return f"{x:.1f}"


def f2(x: float) -> str:
    return f"{x:.2f}"


def signed(x: float, digits: int = 1) -> str:
    text = f"{abs(x):.{digits}f}"
    return f"+{text}" if x > 0 else f"−{text}" if x < 0 else text


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def plural(n: int, singular: str, plural_form: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural_form or singular + 's')}"


def confidence_from_matches(n: int) -> str:
    return "low" if n < 8 else "medium" if n < 20 else "high"


def confidence_from_minutes(minutes: int) -> str:
    return "low" if minutes < 450 else "medium" if minutes < 1500 else "high"


# ---------------------------------------------------------------------- ranking


def rank(insights: Iterable[Insight], limit: int | None = None, per_kind: int | None = None, diversify: bool = False) -> list[Insight]:
    """Best first, with an optional cap per kind so one theme cannot crowd out the rest.

    ``diversify`` puts the best insight of each kind ahead of the second-best of any kind, so the first few
    cards a person sees cover different ground.
    """
    ordered = sorted(insights, key=lambda i: (-i.score, i.id))
    if per_kind is not None:
        seen: dict[str, int] = {}
        capped = []
        for insight in ordered:
            if seen.get(insight.kind, 0) >= per_kind:
                continue
            seen[insight.kind] = seen.get(insight.kind, 0) + 1
            capped.append(insight)
        ordered = capped
    if diversify:
        firsts, rest, kinds = [], [], set()
        for insight in ordered:
            (rest if insight.kind in kinds else firsts).append(insight)
            kinds.add(insight.kind)
        ordered = firsts + rest
    return ordered[:limit] if limit else ordered


def clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def dicts(insights: Sequence[Insight]) -> list[dict]:
    return [i.to_dict() for i in insights]
