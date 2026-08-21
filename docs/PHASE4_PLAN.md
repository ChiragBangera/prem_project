# Phase 4 Plan — Transfermarkt Manual-Import Enrichment

**Branch:** `feat/next-work` · **Depends on:** Phase 0 `EnrichmentProvider` seam (`ad68d82`)
**Goal:** Market value / contract / foot surfaced from a **dated manual Transfermarkt CSV import** — no scraping, TOS-honest, graceful `source:"none"` everywhere when no DB exists.

---

## 1. Design (no new fetches ever)

```
data/transfermarkt/manual.csv  ──(python scripts/enrich_tm_import.py)──▶  cache/enrichment.db (SQLite)
                                                                                 │
AnalyticsService(enrichment=CsvEnrichmentProvider(db))  ◀────────────────────────┘
        └─ analyze_player → report["enrichment"] = {...}   (source:"transfermarkt-manual", dated)
           fallback: NoopEnrichmentProvider → source:"none"  (current behavior, unchanged)
```

Wiring rule (api.py lifespan): `FOOTBALL_ENRICHMENT_DB` env wins; else default `<repo>/cache/enrichment.db`; **if the file does not exist → Noop**. Never crash, never fake.

## 2. Contract

### 2.1 CSV format (`data/transfermarkt/manual.csv.example` ships as template)
```csv
player_name,team_hint,market_value_eur,contract_end,foot,height_cm,fetched_at
Mohamed Salah,Liverpool,55000000,2027-06-30,Left,175,2026-08-21
```
Validation on import: `market_value_eur` positive int or empty; `contract_end` YYYY-MM-DD or empty; `fetched_at` defaults to today; duplicate `player_key` (accent-folded lowercase name + normalized team) upserts.

### 2.2 `POST /api/v1/analyze/player` — `enrichment` becomes real when provider present (fields already existed since Phase 0)
```jsonc
"enrichment": {
  "source": "transfermarkt-manual",
  "fetched_at": "2026-08-21",
  "market_value_eur": 55000000,
  "contract_end": "2027-06-30",
  "foot": "Left",
  "height_cm": 175,
  "sofascore_rating": null, "whoscored_rating": null,
  "strengths": [], "weaknesses": [],
  "honest_note": "Market value from manual Transfermarkt import dated 2026-08-21; unofficial snapshot, not refreshed automatically."
}
```
Matching: accent-folded case-insensitive exact name; `team_hint` disambiguifies namesakes; no fuzzy guessing — miss ⇒ nulls with source still `"none"`.

### 2.3 Frontend (Player hero, null-safe)
Pills appear **only when `source !== "none"`**: `💶 €55.0m` · `📅 Contract to 2027` · `🦶 Left`. Tooltip carries `honest_note`. Discover/squad enrichment deferred (needs pool-wide batch); noted honestly in UI nothing shown when absent.

## 3. Tasks
- BE-005: `CsvEnrichmentProvider` + SQLite helpers in `analytics/enrichment.py`; `scripts/enrich_tm_import.py` (argparse `--csv/--db`, validation, upsert, prints summary); lifespan wiring; example CSV. Tests `tests/test_phase4_enrichment.py`: `test_import_parses_and_upserts`, `test_provider_match_and_namesake_disambiguation`, `test_provider_miss_returns_none_fields`, `test_analyze_player_uses_provider`, `test_lifespan_factory_noop_when_db_missing`.
- FE-005: hero pills per §2.3; verify with a seeded DB on a scratch server port + screenshots `p4-player-enriched.png`.
