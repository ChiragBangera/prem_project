# Audit Report — Premier League Analytics Lab

Audit date: 2026-08-12
Scope: architecture review + live behavior verification against Understat, no changes made.

## 1. Summary

The project is **functional and well-structured for a portfolio piece**, not the "dump" the working tree suggests. All 42 tests pass. The FastAPI app boots, and live calls against `understat.com` succeed end-to-end (league table, player search, player data, team compare, coach timeline, league player ranking). The biggest issue is maintainability: `question_answering.py` is a 1768-line god class, and the current clean state is **uncommitted** — the entire restructure exists only in the working tree against a 2-commit history.

## 2. Live verification (all passed)

| Check | Result |
| --- | --- |
| `uvicorn app.api:app` boots | OK |
| `GET /` and `GET /health` | OK, version 0.2.0 |
| `POST /api/v1/endpoints/league_table` EPL 2025 | OK — Arsenal top, 85 pts |
| `prem-analytics run search_players query="haaland"` | OK — Erling Haaland, id 8260 |
| `prem-analytics run player_data player_id=8260` | OK — FW |
| `POST /api/v1/ask` "Compare Arsenal vs Liverpool in 2025" | OK — `team_compare`, real xG/xGA answer |
| `POST /api/v1/ask` "How have Manchester United looked under Ruben Amorim in 2025" | OK — `coach_timeline`, 31 pts/20 matches |
| `POST /api/v1/ask` "who is the best finisher in the EPL in 2025" | OK — `player_ranking`, Harry Wilson +4.24 |
| `python -m unittest discover -s tests` | OK — 42 tests, 0.03s |

## 3. Architecture map

```
src/app/
  api.py                 FastAPI app, lifespan owns one shared UnderstatData + runner + answerer
  cli.py                 argparse CLI + interactive shell
  endpoint_manifest.py   frozen allowlist of 22 Understat operations (security boundary)
  endpoint_runner.py     validates required/optional params, dispatches to client method
  question_answering.py  NL planner + fetcher + answer composer (1768 lines, god class)
  coach_eras.py          curated manager windows (no upstream manager metadata)
  analytics_presets.py   template + Man Utd preset question catalog
  stat_data/understat.py async UnderstatData client (session-sharing, 22 methods)
  utils/utils.py         HTTP, parsing, date/filter helpers
  constants/             urls + headers
tests/                   42 unittest cases (FakeClient for answerer, ASGI transport for API)
```

Data flow: `manifest (allowlist) -> runner (param validation) -> UnderstatData (fetch) -> answerer (plan/fetch/compose)`. No arbitrary upstream URLs are accepted — good security posture.

## 4. Findings

### 4.1 Critical / should fix

- **F1 — Uncommitted restructure.** The clean package only exists in the working tree. `git log` has 2 commits; the diff deletes a nested `prem_project/` dump, notebooks, `outputs/*.svg`, visual_templates, and an egg-info, plus modifies core files. One `rm -rf .git` or accidental `git checkout .` loses everything. Commit it.
- **F2 — `question_answering.py` god class.** `FootballQuestionAnswerer` owns planning, regex entity extraction, async fetch orchestration, and ~550 lines of per-intent answer composition in `_build_answer`. Adding an intent means editing the same giant method. This is the single biggest maintainability blocker. Deep split: `Planner` (entity extraction + intent) / `Fetcher` (data assembly) / `AnswerBuilder` (one composer module per intent, registered in a dict).

### 4.2 Correctness / latent bugs

- **F3 — `TEAM_MARKERS` produces wrong teams for non-EPL leagues.** Single-word markers like `real`, `barcelona`, `madrid`, `betis`, `sevilla`, `valencia` get capitalized to `Real`, `Barcelona`, etc. and appended as teams. EPL is unaffected (markers there are full words matching aliases), but any La Liga / Serie A question can fabricate a "Real" team. Either drop the bare-word marker loop for leagues that rely on multi-word names, or resolve markers against the league's actual team list.
- **F4 — `_extract_player_names` misfire risk.** Any two consecutive capitalized words that are not team markers become a "player" (e.g. "Premier League", "Understat Season"). Currently masked because most such phrases also contain a marker or alias, but it is fragile. Consider requiring the planner to confirm a candidate via `search_players` before treating it as a player.
- **F5 — `coach_eras.py` curation drift.** `COACH_ERAS_LAST_VERIFIED = 2026-07-17`. The Darren Fletcher window (2026-01-05 → 2026-01-13) between Amorim and Carrick is unusual for a first-team manager era and may be a data error (Fletcher was a coach/technical director, not interim manager). No automated verification; relies on the comment to prompt manual review.
- **F6 — No caching.** Every `/ask` call issues multiple synchronous upstream requests (a `team_compare` made 3+ Understat calls). On free Render this is slow and rate-limit-prone. An in-memory TTL cache keyed on `(endpoint, params)` would cut repeat latency dramatically with no persistence needed.

### 4.3 API surface

- **F7 — Unhandled non-Understat exceptions become 500.** `run_endpoint` catches `KeyError`/`ValueError`; `UnderstatRequestError` -> 502. But a `TypeError`/`KeyError`-from-upstream-shape-change inside the client surfaces as a raw 500. Either broaden the 502 handler or add a catch-all that returns a structured error.
- **F8 — `options` optional param is opaque.** Many endpoints declare `optional_params=("options",)` where `options` is a passthrough filter dict consumed by `Utils.filter_data`. The spec does not document its shape. Either document it or replace with concrete typed filters per endpoint.
- **F9 — `league_table` positional indexing is brittle.** `AnswerBuilder` reads `row[7]` for PTS, `row[8]`/`row[10]` for xG/xGA, `row[12]`/`row[17]` for npxGD/xPTS. A column reorder silently corrupts every answer. Introduce a named-index map (or dataclass) shared with the table builder.

### 4.4 Test coverage gaps

- No test for the **502 path** (`UnderstatRequestError` -> 502 JSON).
- No test for **`run_endpoint` returning live-shaped data** (only `FakeClient`).
- Intents without a dedicated test: `team_overview`, `league_overview`, `fixtures`, `results`, `player_overview`, `player_shots`, `player_compare` summary fields.
- No test for **`interactive_shell`** (acceptable — hard to test; skip or extract a command dispatcher).
- No lint/typecheck configured in `pyproject.toml` (no ruff/mypy). `httpx` is a dev dep but no `pytest`/`ruff`/`mypy` entries.

### 4.5 Minor

- **F10 — Dead branch in `Utils.get_data`.** The `finally` closes the session only when `session is None`, but `UnderstatData._get_data` always passes a non-None session. Harmless, but confusing.
- **F11 — `Understat = UnderstatData` alias** at the bottom of `understat.py` is unused in the app; only matters if external code imports it.
- **F12 — `parse_param_value` CSV split** would break a team name containing a comma (none exist today).

## 5. What is good

- Clean security boundary: the manifest is an allowlist; users cannot supply arbitrary upstream URLs.
- Consistent error translation to `502 upstream_data_error`; health endpoint never touches Understat.
- One async HTTP session shared for app lifetime via `lifespan`.
- Solid FakeClient-based test suite covering 14 of the intents with realistic shapes.
- `docs/understat_endpoint_inventory.md` is genuinely useful and honest about what is confirmed vs unconfirmed.

## 6. Proposed plan (in order, after sign-off)

1. **Commit the restructure** as-is (no behaviour change) so nothing is lost.
2. **Split `question_answering.py`** into `planner.py`, `fetcher.py`, and an `answers/` package with one composer per intent, registered in a dict. Keep the public `FootballQuestionAnswerer.answer` surface identical so tests stay green.
3. **Add a `TABLE_COLUMNS` named-index map** to kill F9 positional brittleness.
4. **Add an in-memory TTL cache** around `UnderstatData` fetches (F6).
5. **Broaden API error handling** + add 502 test (F7).
6. **Fix `TEAM_MARKERS` for non-EPL leagues** (F3).
7. Then move to **features** (separate proposal).
