from __future__ import annotations

import asyncio
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


def normalize_player_key(name: str) -> str:
    """Accent-folded, lowercased, whitespace-collapsed key ('João  Pedro' == 'joao pedro')."""
    value = unicodedata.normalize("NFD", (name or "").lower())
    folded = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return " ".join(folded.split()).strip()


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


TM_NOTE_TEMPLATE = (
    "Market value from manual Transfermarkt import dated {fetched_at}; "
    "unofficial snapshot, not refreshed automatically."
)


def _ensure_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                player_key TEXT PRIMARY KEY,
                player_name TEXT NOT NULL,
                team_hint TEXT,
                market_value_eur INTEGER,
                contract_end TEXT,
                foot TEXT,
                height_cm REAL,
                fetched_at TEXT
            )
            """
        )


def upsert_player_rows(db_path: str | Path, rows: list[dict]) -> int:
    """Upsert validated enrichment rows; returns number written.

    Row keys: player_name (required), team_hint, market_value_eur, contract_end,
    foot, height_cm, fetched_at. player_key = normalized name + '::' + normalized
    team hint so namesakes at different clubs coexist.
    """
    _ensure_db(db_path)
    written = 0
    with sqlite3.connect(db_path) as conn:
        for row in rows:
            name = (row.get("player_name") or "").strip()
            if not name:
                continue
            team = (row.get("team_hint") or "").strip()
            key = f"{normalize_player_key(name)}::{team.lower()}"
            value = row.get("market_value_eur")
            value = int(value) if value not in (None, "") else None
            conn.execute(
                """
                INSERT INTO players (player_key, player_name, team_hint, market_value_eur,
                                     contract_end, foot, height_cm, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_key) DO UPDATE SET
                    player_name=excluded.player_name,
                    market_value_eur=excluded.market_value_eur,
                    contract_end=excluded.contract_end,
                    foot=excluded.foot,
                    height_cm=excluded.height_cm,
                    fetched_at=excluded.fetched_at
                """,
                (
                    key,
                    name,
                    team or None,
                    value,
                    row.get("contract_end") or None,
                    row.get("foot") or None,
                    row.get("height_cm"),
                    row.get("fetched_at") or None,
                ),
            )
            written += 1
    return written


class CsvEnrichmentProvider:
    """Reads the manual-import SQLite cache built by scripts/enrich_tm_import.py."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        _ensure_db(self.db_path)

    def _lookup_sync(self, player_name: str, team_hint: str | None):
        key_name = normalize_player_key(player_name)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM players WHERE player_key LIKE ?", (f"{key_name}::%",)
            ).fetchall()
        if not rows:
            return None
        if len(rows) > 1 and team_hint:
            wanted = (team_hint or "").strip().lower()
            exact = [r for r in rows if (r["team_hint"] or "").strip().lower() == wanted]
            if exact:
                rows = exact
        # deterministic: most recent fetch first, then team order
        rows.sort(key=lambda r: (r["fetched_at"] or ""), reverse=True)
        return rows[0]

    async def enrich_player(self, player_name: str, team_hint: str | None = None) -> ExternalEnrichment:
        try:
            row = await asyncio.to_thread(self._lookup_sync, player_name, team_hint)
        except Exception:
            return NoopEnrichmentProvider().enrich_player(player_name, team_hint)
        if row is None:
            return ExternalEnrichment(
                source="none",
                honest_note="No manual import entry matched this player.",
            )
        fetched_at = row["fetched_at"]
        return ExternalEnrichment(
            source="transfermarkt-manual",
            fetched_at=fetched_at,
            market_value_eur=row["market_value_eur"],
            contract_end=row["contract_end"],
            foot=row["foot"],
            height_cm=row["height_cm"],
            sofascore_rating=None,
            whoscored_rating=None,
            strengths=[],
            weaknesses=[],
            honest_note=TM_NOTE_TEMPLATE.format(fetched_at=fetched_at or "unknown date"),
        )

    async def enrich_team_squad(self, team_name: str, season: int) -> dict[str, ExternalEnrichment]:
        try:
            def _squad():
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT * FROM players WHERE LOWER(team_hint)=LOWER(?)", (team_name.strip(),)
                    ).fetchall()
                return rows

            rows = await asyncio.to_thread(_squad)
        except Exception:
            return {}
        out = {}
        for row in rows:
            out[row["player_name"]] = await self.enrich_player(row["player_name"], row["team_hint"])
        return out


def provider_from_env() -> EnrichmentProvider:
    """FOOTBALL_ENRICHMENT_DB wins; else repo-default cache/enrichment.db if it exists; else Noop."""
    import os

    root = Path(__file__).resolve().parents[3]
    path = os.environ.get("FOOTBALL_ENRICHMENT_DB") or str(root / "cache" / "enrichment.db")
    if Path(path).exists():
        return CsvEnrichmentProvider(path)
    return NoopEnrichmentProvider()
