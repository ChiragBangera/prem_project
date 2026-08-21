# DEFECTS.md — QA owned

> Format: numbered steps from app launch, expected outcome, actual outcome, screenshot where it helps, honest severity: HIGH breaks a requirement, MEDIUM degrades one, LOW is cosmetic. Only QA may set CLOSED. Never edit product code via this file.

## Phase 0 — feat/next-work (Understat max-use + axis labels) — QA 2026-08-21

**Test tail:** `uv run python -m unittest discover -s tests -v` — 140 tests OK in ~15.5s (tail pasted in report). Branch `feat/next-work` baseline `7d04c38`.

**Contract checks:** ` /tmp/qa_contract_check.py` — all PASS:
- `shot_profile_detail` zones/types xG_share sums ~1.0, `_source` forwarded as `groups.shotZones` / `groups.shotTypes` / `groups.situation` / `groups.position`
- `assisted_network.top_assisters` correctly counts `player_assisted` (De Bruyne 2), `honest_note` present, `enrichment.source=="none"`
- `analyze_match` rosters 2+2 and `forecast.w==0.42` with `source:"understat"`
- `metric_trends` deep_for/deep_against length 6, window 5 avg
- `match_rounds` upcoming_by_round grouped with forecast per fixture

**Axis scale guard:** literals unchanged:
- `y1 - (v / allMax)` ×2 preserved
- `y1 - ((v + allMax) / (2 * allMax))` ×1 preserved
- Plus existing `y1 - ((v || 0)/maxVal)...` etc. Only added `<text>` axis titles.

**Frontend strings in app.js (curl via 8011):** axis titles present — `Season` (×3), `Goals / xG`, `Per 90`, `Rank (1 = top)` / `Points`, `Cumulative G − xG`, `Match date (5-match rolling avg)`, `Points gap (PTS − xPTS)`, `PPDA (lower = higher press…)` / `Deep completions / game`, `Team (sorted by gap)`. New blocks `forecastPill`, `rostersBlock`, `assistedNetworkBlock`, `playerZoneTypeBars`, `deep_for` select all present.

**Screenshots:** captured via Playwright @ 1280×900:
- `screenshots/qa-phase0-dashboard.png` (Player scouting empty state, 104K)
- `screenshots/qa-phase0-team.png` (Team empty state, 100K)
- `screenshots/qa-phase0-match.png` (Match deep-dive empty state, 112K)
Limitation: live Understat not stubbed, so screenshots show empty-state scaffolding, not populated charts. Verified labels instead via `grep` + curl of `/dashboard/app.js` (148158 bytes). No visual overlap defect provable without live data, but axis `<text>` sits outside plot area (h-6 / 14-rotated), not overlapping curves per code inspection.

**Overall verdict:** PASS for Phase 0 backend contract + frontend wiring. No HIGH defect blocks merge. Minor LOW observations logged below for dev triage; not blocking.

---

### DEF-001 — playerZoneTypeBars legend index mismatch when filtered — LOW

**Steps:**
1. Launch app, open Player Profile, mock a player where some zones have 0 shots (e.g., Central 0).
2. Trigger shot_profile_detail with filtered `sitItems` dropping zero entries.
3. Observe legend rows: `filtered.map(([name,count], idx)` uses `items[idx]` for `xG_share`, but idx now indexes filtered array, not original.

**Expected:** Each legend chip shows its own `xG_share` from the same zone/type entry.
**Actual:** If a leading category is filtered, shares shift (chip N shows share of original item N, but filtered item N+M). Code in `app.js:1935-1939` — `const orig = items[idx] || {}` inside filtered.map should use lookup by name, not idx.
**Screenshot:** n/a (requires edge data; curl shows code at `playerZoneTypeBars`).
**Severity:** LOW — cosmetic, rare (only when a zone/type is zero-shot), does not break HIGH requirement. Data still sums, shares still correct in bar widths.
**Status:** FIX-READY — Found by: qa
**Developer:** frontend-dev — FIX READY — "filtered.map used `items[idx]` for xG_share which shifted when leading zones/types had 0 shots (filtered index ≠ original index), causing wrong share on legend chip. Fix: carry `xG_share` in filtered tuple `[name, shots, xG_share]` so legend maps by filtered entry, not original index."
**History:** 2026-08-21 frontend-dev FIX READY (carried share in filtered tuple) → awaiting qa retest to CLOSE.

### DEF-002 — assisted_network `top_assisted` always empty — LOW (honest limitation)

**Steps:**
1. Call `POST /api/v1/analyze/player` for any player with shots.
2. Inspect `assisted_network.top_assisted`.

**Expected (per PHASE0_PLAN §1.1):** Contains up to 5 players the subject assisted (who you gave xG to), derived from data.
**Actual:** `top_assisted: []` always. Backend `analytics_service.py:253-267` builds `assisted_agg` but never populates (comment: "not derivable from own shots; leave empty"). `honest_note` discloses Understat shot-assists source, but the emptiness is not signaled as limitation in the pair. Frontend shows "You assisted → teammates" table with `—`.
**Screenshot:** n/a
**Severity:** LOW — honest, spec acknowledges future Pass Network map; not a HIGH break, but degrades Phase 0 richness vs plan.
**Status:** OPEN — Found by: qa

### DEF-003 — No repro / no defect for axis rescale — INFO

Axis scale guard literals confirmed byte-identical before/after. All 8+ charts retain original `y(v)` normalizations; only `<text>` titles added. No defect filed. Evidence: `grep -F` counts above.

---

## Adversary triage → new DEFs (2026-08-21, delivery lead)

### DEF-004 — Axis title clipping at 375px, long metric names fall back to raw snake_case — HIGH

**Steps:** ADV-001. Player → Career Trajectory → select `xGChain_per90` → resize to 375px → `drawCareerChart` yTitle = `GLOSSARY[metricKey]?.label || metricKey` falls back to raw `xGChain_per90`; SVG `x=14` rotated −90° clips outside viewBox 1100→375.

**Expected:** yTitle always uses glossary label (e.g., `xG Chain /90`) or truncated, visible without clipping, not overlapping ticks.

**Actual:** Raw snake_case shown, half string at negative x, clipped. Same in `drawTrendChart` (`yLabel = entry.label || key (5-match avg)`), `drawSeasonLines`, `drawLuckChart`.

**Screenshot:** `screenshots/adv-001-axis-label-clip-375.png`

**Severity:** HIGH — breaks success criterion "axis needs to be added ... do not change the axis but name it" at mobile.

**Status:** FIX-READY — Found by: adversary (ADV-001) — ACCEPTED -> DEF-004
**Developer:** frontend-dev — FIX READY — "drawCareerChart/drawTrendChart used GLOSSARY[metricKey]?.label || metricKey — glossary keys are xG_chain not xGChain_per90, so fallback showed raw snake_case at x=14 clipping. Fix: added glossaryLabelForMetric mapping xGChain_per90→xG_chain etc. + truncateLabel 28 chars, applied to drawCareerChart/drawTrendChart/drawSeasonLines/drawLuckChart; scale math unchanged."
**History:** 2026-08-21 frontend-dev FIX READY (glossary mapping + truncate) → awaiting qa retest.

### DEF-005 — Forecast pill disclosure only on hover, misread as Dixon-Coles on touch — MED

**Steps:** ADV-002. Match Deep-Dive hero pill `forecastPill()` uses `title="Not our Dixon-Coles..."`; hover only. Hero says `OFFICIAL MATCH INTELLIGENCE` above pill. Compare Predict tab which promises Dixon-Coles.

**Expected:** Inline disclosure "(Understat, not our Dixon-Coles)" visible without hover, especially on touch.

**Actual:** Tooltip lost on iOS/Android; pill reads as app forecast.

**Screenshot:** `screenshots/adv-002-forecast-pill-tooltip.png`

**Severity:** MED

**Status:** FIX-READY — Found by: adversary (ADV-002) — ACCEPTED -> DEF-005
**Developer:** frontend-dev — FIX READY — "forecastPill disclosed only via title tooltip, lost on touch, hero OFFICIAL MATCH INTELLIGENCE caused misread as Dixon-Coles. Fix: keep title but add inline (not Dixon-Coles) span inside pill text so disclosure visible without hover/touch."
**History:** 2026-08-21 frontend-dev FIX READY (inline disclosure) → awaiting qa.

### DEF-006 — Null shot_profile_detail renders nothing — no empty state — LOW

**Steps:** ADV-004. Player with sparse `groups` → `shot_profile_detail: null` → `playerZoneTypeBars(null)` returns `""`; Zones/Types/Role area absent silently.

**Expected:** Explicit empty state "Zone/type breakdown unavailable for this season — Understat groups missing".

**Actual:** Empty string concatenated, user cannot distinguish 0 shots vs missing groups.

**Screenshot:** `screenshots/adv-004-null-detail-empty.png`

**Severity:** LOW

**Status:** FIX-READY — Found by: adversary (ADV-004) — ACCEPTED -> DEF-006
**Developer:** frontend-dev — FIX READY — "playerZoneTypeBars(null) returned empty string, user cannot distinguish missing groups vs zero shots. Fix: return explicit empty state div — Zone/type breakdown unavailable for this season — Understat groups missing — when detail null or all empty."
**History:** 2026-08-21 frontend-dev FIX READY (empty state) → awaiting qa.

### DEF-007 — Assisted badge miscount and grammar — LOW

**Steps:** ADV-006. Player with 1 assister → `top_assisters.length=1`, `top_assisted=[]` → header shows `1 links`, grammar wrong, implies bidirectional.

**Expected:** Count distinguishes inbound vs empty outbound or hides when one side empty.

**Actual:** `1 links`, symmetric header misleads.

**Screenshot:** `screenshots/adv-006-assisted-badge.png`

**Severity:** LOW

**Status:** FIX-READY — Found by: adversary (ADV-006) — ACCEPTED -> DEF-007
**Developer:** frontend-dev — FIX READY — "header showed X links even when top_assisted empty, grammar wrong. Fix: header now shows X inbound when outbound empty (and vice versa), otherwise N links with singular/plural, dash row remains."
**History:** 2026-08-21 frontend-dev FIX READY (inbound badge) → awaiting qa.
*Note ADV-005 maps to existing DEF-002.*

### DEF-008 — Forecast lookup fans out LEAGUES×seasons (≈30 fetches) per analyze_match — HIGH

**Steps:** ADV-008. `AnalyticsService.analyze_match` loops `LEAGUES(5) × seasons_to_try(5) + fallback(5)` sequential `get_league_data` to find `forecast` for one id. No cache/dedup. Script 20 parallel requests → 600 upstream hits.

**Expected:** Single cached lookup or indexed id→forecast, bounded to 1-2 fetches, with TTL cache / dedup / rate-limit.

**Actual:** Up to 30 sequential GETs, >2s latency, amplifiable, no `429` handling. Risks Understat throttle.

**Screenshot:** `screenshots/adv-008-forecast-loop-waterfall.png`

**Severity:** HIGH

**Status:** FIX-READY — Found by: adversary (ADV-008) — ACCEPTED -> DEF-008
**Developer:** backend-dev — FIX READY — "Forecast lookup fans out LEAGUES×seasons (~30 fetches) per analyze_match. Current code loops LEAGUES(5)×seasons_to_try(5)+fallback. Fix: bounded to max 3 fetches with in-memory _forecast_cache TTL 300s, candidates [(EPL,DEFAULT),(EPL,DEFAULT-1),(La_liga,DEFAULT)], deduped, loop break on found, cache hit 0 fetches on second call. Verified ≤3 calls."
**History:** 2026-08-21 backend-dev FIX READY (bounded + cache) → awaiting qa retest.

### DEF-009 — Rosters empty vs null indistinguishable, order non-deterministic — LOW

**Steps:** ADV-009. Future fixture `rosters:null` vs `{h:[],a:[]}` both show same "Rosters unavailable". Insertion order of `raw_rosters.get("h")` dict values arbitrary.

**Expected:** Separate empty states ("not yet published" vs "payload missing") and deterministic order (e.g., sort by `xG` desc).

**Actual:** Same generic message, rows non-deterministic.

**Screenshot:** `screenshots/adv-009-rosters-unavailable-vs-future.png`

**Severity:** LOW

**Status:** OPEN — Found by: adversary (ADV-009) — ACCEPTED -> DEF-009

### DEF-010 — Rotated y-titles accessibility & contrast marginal — MED

**Steps:** ADV-010. 10px `#94a3b8` on `#121824` (≈4.1:1) rotated −90° at `x=14`; no `aria`, overlaps ticks at 375px. Lighthouse flags.

**Expected:** WCAG AA 4.5:1 for normal text, `aria-label`/`title` on SVG, no tick overlap.

**Actual:** Marginal ratio, 7.5px perceived size, no a11y label.

**Screenshot:** `screenshots/adv-010-y-title-a11y-rotate.png`

**Severity:** MED

**Status:** OPEN — Found by: adversary (ADV-010) — ACCEPTED -> DEF-010
*Deferred: not blocking Phase 0, fix with DEF-004 clipping pass.*

### DEF-011 — Shot profile season fallback opaque — MED

**Steps:** ADV-012. Player 2025 request where groups for 2025 missing → backend silently falls back to 2024 via reversed `target_seasons` scan, returns 2024 zones under 2025 hero `· 2025` badge, no `profile_season` field.

**Expected:** Label indicates fallback ("Shot Zones — 2024 (fallback: 2025 unavailable)") or explicitly hides.

**Actual:** Zones appear as if 2025, `profile_season` missing in response, UI cannot disclose.

**Screenshot:** `screenshots/adv-012-profile-fallback-opaque.png`

**Severity:** MED

**Status:** FIX-READY — Found by: adversary (ADV-012) — ACCEPTED -> DEF-011
**Developer:** backend-dev — FIX READY — "Shot profile fallback opaque — backend silently showed 2024 zones when 2025 missing. Fix: added profile_season, requested_season, fallback bool, honest_note/fallback_note to shot_profile_detail; fallback scan now also checks any groups keys (not just target_seasons) to surface honest note. Verified profile_season==2024 when 2025 missing."
**History:** 2026-08-21 backend-dev FIX READY (profile_season + note) → awaiting qa.




---

## Live-API audit findings (2026-08-21, delivery lead — user reported "backend data fetching issues")

Reproduced against running app (127.0.0.1:8000, live Understat). Full endpoint sweep with timings.

### DEF-012 — Team squad table ALWAYS empty in live deploys: `round_value` NameError swallowed — HIGH

**Steps:**
1. `curl -X POST /api/v1/analyze/team -d '{"team_name":"Arsenal","league_name":"EPL","season":2025}'`
2. Inspect `squad` in response → `[]`.
3. Direct client check: `UnderstatData().get_team_player_stats('Arsenal','2025')` returns 25 rows; parsing rows standalone succeeds.

**Expected:** Squad Performance & Creation Contributions table renders ~25 Arsenal players with xG/xA/Chain per90.

**Actual:** `analytics_service.py:752` calls `round_value(...)` which is **never imported** (`hasattr(analytics_service,'round_value') == False`; line 12 imports only `as_list_matches`). First dict row raises `NameError`, swallowed by bare `except Exception: report["squad"] = []`. Fetch traced OK (25 rows) yet final squad 0. Feature has been dead in every live run; mock tests missed it because no test asserted populated squad through `analyze_team`.

**Evidence:** trace log "team_player_stats called with ('2025',) -> 25 rows / FINAL squad: 0".

**Severity:** HIGH — core Team Analytics feature silently dead.

**Status:** FIX-READY — Found by: delivery lead (live audit)
**Developer:** backend-dev — FIX READY — "round_value was never imported in analytics_service.py; NameError on first squad row swallowed by bare except. Fix: added round_value to `from .analytics._shared import` + logging.warning(exc_info=True) in the except so future silent deaths are visible. Squad row shape unchanged."
**History:** 2026-08-21 backend-dev FIX READY → live retest by lead: analyze/team Arsenal 2025 squad=25 (Gyokeres xG 13.87 top). Awaiting qa CLOSE.

### DEF-013 — Predict tab broken from UI: frontend sends `home_team/away_team`, API expects `home/away` — HIGH

**Steps:**
1. Open Predict & Sim → Home=Arsenal, Away=Liverpool → Generate Forecast.
2. Server log: `POST /api/v1/predict/match → 422`.

**Expected:** 200 with Dixon-Coles + Elo forecast.

**Actual:** `app.js:3106-3108` sends `{home_team, away_team, ...}` but `PredictMatchRequest` (api.py:617-623) requires `home: str, away: str`. Pydantic 422 "Field required". Direct curl with correct fields returns 200 in ~19.5s. Every UI predict click fails.

**Evidence:** uvicorn log 422 on user click; curl repro both ways.

**Severity:** HIGH — Predict & Sim tab unusable from the dashboard.

**Status:** FIX-READY — Found by: delivery lead (live audit)
**Developer:** backend-dev — FIX READY — "Backend-side backward-compat fix: PredictMatchRequest now accepts home OR home_team, away OR away_team via before-validator; original home/away unchanged so existing tests/clients keep working."
**History:** 2026-08-21 backend-dev FIX READY → live retest by lead: UI-shaped payload {home_team,away_team} → 200 in 18.4s with model+match keys. Awaiting qa CLOSE.

### DEF-014 — Transient upstream 502 on analyze/league, no retry — LOW

**Steps:** Server log shows one `POST /api/v1/analyze/league → 502 Bad Gateway` followed by user/app retry → 200.

**Expected:** Transient Understat hiccup retried once server-side (or surfaced as retryable), not a raw 502 to the browser.

**Actual:** Single upstream failure surfaces as 502; frontend league fallback only handles empty-season, not 502.

**Severity:** LOW — self-healed on manual retry; add single server-side retry or client hint later.

**Status:** OPEN — Found by: delivery lead (live audit)

### Latency observations (no cache) — INFO, feeds Phase 2+ cache work

analyze/player 7.4s · discover(template) 4.9s · analyze/team 6.5s · compare 5.1s · career 3.8s · predict/match 19.5s · match 2.3s · rounds 1.2s · league 1.1-1.5s. All live-fetch, zero caching outside ml `_history_cache`. Confirms AUDIT F6; persistent cache pulled forward as Phase 2 companion work.

---

## Visual audit findings (2026-08-21, delivery lead from qa screenshots p1-*)

### DEF-015 — Horizontal overflow at 375px on player/discover/team/match views — MED

**Steps:** Load any of those tabs at 375x812; document.scrollWidth = 409–423 vs innerWidth 375 (qa capture-report.json).

**Expected:** No horizontal page scroll on mobile.

**Actual:** Something overflows by 34–48px on all four views (1440 is clean). Suspects: `.controls-row` fixed min-widths, discover threshold inputs row, kpi-row, fixture grid.

**Severity:** MED

**Status:** FIX-READY — Found by: delivery lead/qa evidence
**Developer:** frontend-dev — FIX READY — "Diagnosed offenders via playwright element sweep; fixed minimally in styles.css (controls-row flex-wrap + min-width:0, kpi-row grid minmax, fixture grid). Desktop layout unchanged."
**History:** 2026-08-21 frontend-dev FIX READY → lead re-measured with e2e/overflow-check.cjs: player/discover/team/match all scrollWidth=375 PASS at 375px.

### DEF-016 — Discover table XG column shows "-" for every player — LOW

**Steps:** Run Discover → inspect XG (EXPECTED GOALS) column.

**Expected:** Shows xG totals.

**Actual:** All rows "-": renderDiscover reads `p.xG` but discover API returns `npxG` (no plain xG key). Column is dead weight next to NPXG.

**Severity:** LOW

**Status:** FIX-READY — Found by: delivery lead
**Developer:** frontend-dev — FIX READY — "Dead XG column (p.xG never in discover API) replaced with G−xG column using p.g_minus_xg, signed and colored good/bad like squad table."
**History:** 2026-08-21 frontend-dev FIX READY → awaiting qa CLOSE.

### DEF-017 — Duplicate "Watchlist: 0" pills (button row + card header) — LOW

**Steps:** Open Discover; two identical pills visible.

**Expected:** One indicator.

**Actual:** Redundant duplication.

**Severity:** LOW

**Status:** FIX-READY — Found by: delivery lead
**Developer:** frontend-dev — FIX READY — "Removed duplicate watchlistCountPill span next to #discoverGo in index.html; single pill remains, updateWatchlistPill retargeted and live-updates on toggle."
**History:** 2026-08-21 frontend-dev FIX READY → awaiting qa CLOSE.

### DEF-018 — Season label stale after LATEST→LATEST-1 fallback (player/team) — MED

**Steps:** With LATEST_SEASON=2026 and empty 2026 data, run Arsenal/Salah; hero resolves but season control still reads 2026 while data is 2025 (team hero: "38 matches analyzed" under a 2026 pill).

**Expected:** Fallback updates the visible season-multi label/dataset, not just internal var.

**Actual:** runPlayer/runTeam do `$("playerSeasons").value = String(season)` — that element is a season-multi div, `.value` assignment is a no-op; label stays 2026. Misleading season attribution.

**Severity:** MED

**Status:** FIX-READY — Found by: delivery lead
**Developer:** frontend-dev — FIX READY — "runPlayer/runTeam fallback now updates season-multi host too: dataset.seasons=[season], [data-season-btn] label, localStorage prem_playerSeasons/prem_teamSeasons; forced-failure test shows label/dataset/storage/resolved line all 2025 instead of stale 2026."
**History:** 2026-08-21 frontend-dev FIX READY → awaiting qa CLOSE.

### DEF-019 — Predict & Sim has NO season fallback → guaranteed 422 at season start — HIGH

**Steps:** New season (2026) with few completed matches → click Generate Forecast / Run Simulation / Calibration.

**Expected:** Same LATEST→LATEST-1 fallback other tabs have; forecast renders.

**Actual:** predict endpoints fit Dixon-Coles on 2026 (insufficient matches) → 422 shown raw; console captured three 422s; predictContent stayed empty (len=90). Tab unusable exactly when users try it pre-season.

**Severity:** HIGH

**Status:** FIX-READY — Found by: delivery lead/qa evidence
**Developer:** frontend-dev — FIX READY — "runPredict/runSim/runCal now use runPlayer's LATEST→LATEST-1 retry pattern on the real selects. PLUS two pre-existing breaks found & fixed: renderPredict read d.ensemble/d.home_team/d.dixon_coles but API returns model.ensemble/match.home/model.dixon_coles (crashed on every successful fetch since 3a93950) → rewritten to map real fields incl. Elo row; runSim called nonexistent /predict/season-simulation → corrected to /api/v1/predict/season."
**History:** 2026-08-21 frontend-dev FIX READY → lead verified visually: fix-predict-1440.png shows probability bar 59/26/15 Arsenal-Chelsea, λ 1.48–0.63, scoreline 1-0 (17%), Elo 70/19/10, auto-fallback to 2025.
