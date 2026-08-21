# Adversarial Review — Phase 0 (feat/next-work)

> Branch: `feat/next-work` · Phase 0 (Understat max-use + axis labels, no rescale, noop enrichment)  
> Reviewer: muse-spark-1.2-contributor (adversary) · Date: 2026-08-21  
> Scope: Hostile, unscripted review of `src/app/analytics_service.py`, `src/app/dashboard/app.js` (`forecastPill`, `playerZoneTypeBars`, `assistedNetworkBlock`, `drawCareerChart`/`drawTrendChart`/`drawSeasonLines`), rosters/forecast lookups, `src/app/analytics/enrichment.py`, `src/app/stat_data/understat.py`.  
> Mode: Do NOT fix. Record observations only. Disposition belongs to delivery lead.

---

## ADV-001: Axis title clipping & overlap at 375 px — long metric names (xGChain_per90) clipped vs yTitle

- **Severity**: HIGH
- **Steps to Repro**:
  1. Open Player → search any player (e.g. `Erling Haaland`) → click `Career Trajectory`.
  2. In the career metric dropdown select `xGChain_per90` (or `xGBuildup_per90`, `goal_involvement_per90`).
  3. Resize viewport to 375 px (iPhone SE) / Chrome DevTools responsive.
  4. Inspect the left-rotated yTitle in `#careerChart` and the trend chart `#trendChart` (Team view → 5-Match Rolling → `npxGD`).
- **Expected**: Rotated y-axis title remains fully visible, does not overlap tick labels or y-axis line, wraps or truncates gracefully; long metric names are localised via glossary labels, not raw snake_case.
- **Actual**: `drawCareerChart` builds `yTitle = GLOSSARY[metricKey]?.label || metricKey`. Glossary keys are `xG_chain`, `xG_buildup` — not `xGChain_per90` — so fallback renders raw `xGChain_per90` (14 chars). SVG text is at `x="14" y="(y0+y1)/2"` `font-size="10"` `transform="rotate(-90 14 …)"`. At `viewBox="0 0 1100 260"` with `padL=56`, the text anchor is only 14 px from the left edge; half the string extends to negative x and is clipped by the SVG viewport after scaling to 375 px (`~0.34×`). Identical pattern in `drawTrendChart` (`yLabel = entry.label || key (5-match avg)`) and `drawSeasonLines`, `drawLuckChart`, `drawCareerGoalsVsXg`. No `text-overflow`, no `clamp`, no tick collision handling.
- **Screenshot**: `screenshots/adv-001-axis-label-clip-375.png` (capture career chart + trend chart at 375 px, highlight left edge clipping)
- **Disposition**: ACCEPTED -> DEF-004

## ADV-002: Mock/forecast mislabel — "Understat model" pill may be read as Dixon-Coles; tooltip lost on touch

- **Severity**: MED
- **Steps to Repro**:
  1. Match Deep-Dive → load any fixture (e.g. `28778`) → observe hero banner under `xG: X vs Y` line.
  2. Hover `Understat model — H 48% D 26% A 26%` pill on desktop; repeat on iOS/Android (no hover).
  3. Compare with Predict & Sim tab which advertises "Bivariate Dixon-Coles and Elo match forecasting."
- **Expected**: Forecast source is unmistakably disclosed inline (not tooltip-only). User can distinguish Dixon-Coles (our model) from Understat's opaque pre-match `dates.forecast`. Mobile shows disclosure without hover.
- **Actual**: `forecastPill()` returns `<span … title="Not our Dixon-Coles. Source: Understat forecast.">Understat model — H …</span>`. Disclosure exists only in `title` attribute (desktop hover). On touch there is no hover, so pill reads as the app's own forecast. Hero header says "OFFICIAL MATCH INTELLIGENCE" directly above pill, reinforcing confusion. No inline `(Understat, not Dixon-Coles)` caption. Predict tab trains user to expect Dixon-Coles, increasing misattribution risk.
- **Screenshot**: `screenshots/adv-002-forecast-pill-tooltip.png` (desktop hover vs mobile long-press, vs Predict tab header)
- **Disposition**: ACCEPTED -> DEF-005

## ADV-003: `playerZoneTypeBars` filtered-idx mismatch — wrong xG_share attached to wrong zone/type

- **Severity**: HIGH
- **Steps to Repro**:
  1. Player → `Bukayo Saka` (or any winger with 0 shots from a zone, e.g. low `OutsideBox` 0 but `InsideBox` 21).
  2. Inspect Shot Zones / Shot Types segmented bars under Finishing & Shot Quality Diagnostics.
  3. With DevTools, log `detail.zones` from `/api/v1/analyze/player` response and compare legend `xG share` badges.
- **Expected**: Legend `xG share %` corresponds to the same zone/type as the bar segment and label.
- **Actual**: In `playerZoneTypeBars()`:
  ```js
  const sitItems = items.map(r => [r[labelKey]||r.name||…, Number(r.shots)||0])
  const filtered = sitItems.filter(([,c])=>c>0)
  // later:
  filtered.map(([name,count], idx) => {
    const orig = items[idx] || {} // BUG: idx indexes filtered, not original items
    const share = orig.xG_share != null ? ` · xG share ${pct(orig.xG_share,0)}` : ""
  })
  ```
  If `items = [{InsideBox, shots:0, xG_share:0.0}, {OutsideBox, shots:5, xG_share:0.15}]`, `filtered = [[OutsideBox,5]]`, `idx=0` pulls `items[0].xG_share = 0.0`, so legend shows `OutsideBox: 100% (5) · xG share 0%` — inverted. Total also uses pre-filter total (includes zero), but share mismatch is the visible defect. `barBlock` colours also keyed by filtered idx, so colour ↔ label stays but share does not.
- **Screenshot**: `screenshots/adv-003-zone-type-share-mismatch.png` (zones bar with 0-vs-non-zero console + legend mismatch)
- **Disposition**: ACCEPTED -> DEF-001

## ADV-004: Null/empty `shot_profile_detail` renders nothing — no empty state, silent failure when groups is null

- **Severity**: LOW
- **Steps to Repro**:
  1. Player search for a low-minute player or a player with sparse `groups` payload (e.g., a youth debutant with <90 min in target season) → `/api/v1/analyze/player` returns `shot_profile_detail: null`.
  2. Observe Finishing & Shot Quality → Situations bar appears (from `shots`), but Zones/Types/Role split area is completely absent.
- **Expected**: Explicit empty state ("Zone/type breakdown unavailable for this season — Understat groups missing") so user knows absence is data-gating, not a rendering bug.
- **Actual**: `playerZoneTypeBars(null)` returns `""`. Empty string is concatenated silently. No hint, no icon. User cannot distinguish "0 shots" from "Understat did not return groups". Role split also hidden.
- **Screenshot**: `screenshots/adv-004-null-detail-empty.png` (player with null detail showing only Situations bar, no Zones/Types placeholder)
- **Disposition**: ACCEPTED -> DEF-006

## ADV-005: `top_assisted` is always empty — table implies failure / missing feature

- **Severity**: MED
- **Steps to Repro**:
  1. Player → any forward with shots (e.g. `Mohamed Salah`) → scroll to `Assisted Network`.
  2. Inspect JSON: `assisted_network.top_assisted` is always `[]` (backend comment: `// top_assisted: player assisted others — not derivable from own shots; leave empty`).
  3. Observe UI: left table `Top assisters → you` has rows; right table `You assisted → teammates` shows 3 dash rows with header "You assisted → teammates" and `3 links` badge (count = `assisters.length + assisted.length`).
- **Expected**: Honest note explains asymmetry ("second column intentionally empty: own shots cannot show who you assisted"), or table is hidden when empty. Count badge reflects reality.
- **Actual**: UI renders a two-column card with one populated column and one permanently empty dash column. `honest_note` says only "Aggregated from shots.player_assisted (Understat shot assists, not Opta key passes)." — no mention that `top_assisted` is structurally empty. Badge `N links` conflates both sides, so `3 links` overstates (only 3 assisters, 0 assisted). When `shots` is null, block correctly shows "No assist data" + hint, but with shots present the empty column reads as broken data.
- **Screenshot**: `screenshots/adv-005-assisted-always-empty.png` (Salah assisted network with empty right table + badge)
- **Disposition**: ACCEPTED -> DEF-002

## ADV-006: `assistedNetworkBlock` null path still shows misleading hero count when only one side exists

- **Severity**: LOW
- **Steps to Repro**:
  1. Player with exactly 1 assister (e.g., fringe player) → `top_assisters = [{assister:"X", count:1}]`, `top_assisted=[]`.
  2. Observe card header: `<span>1 links</span>` (assisters.length + assisted.length = 1). Header says "Assisted Network" + "1 links" but table shows 1 row left, 0 right.
- **Expected**: Header counts distinguish direction or hides when one side empty.
- **Actual**: Symmetric header implies bidirectional links exist. Copy "1 links" is grammatically wrong and obscures that all links are inbound.
- **Screenshot**: `screenshots/adv-006-assisted-badge.png`
- **Disposition**: ACCEPTED -> DEF-007

## ADV-007: `upcoming_by_round` round-number collision when `isResult` is empty / postponed fixtures

- **Severity**: MED
- **Steps to Repro**:
  1. Call `POST /api/v1/matches/rounds` with `league_name=EPL season=2024` late August (0–2 played, many `isResult=false`) or with a season where fixtures were postponed (e.g. Covid week).
  2. Inspect `upcoming_by_round[].round` and payload `note`.
  3. Open frontend (future "Upcoming" UI if wired) or log grouping.
- **Expected**: Round numbers map to official gameweeks or are clearly marked as derived / unstable during postponements. No duplicate rounds for different dates.
- **Actual**: Backend increments `upcoming_team_played[home]` per sorted upcoming row (`sort by (date,home)`). If two postponed matches share same home team, the home's nth count still increments, so a rescheduled fixture lands in a later "round" even though it should belong to an earlier gameweek. Two matches with same home count but different dates (due to sorting tie) would collide in same round array although they are weeks apart. `note` says "Round = the home team's nth league match … Forecast from Understat dates.forecast where available." — does not warn that upcoming rounds are home-centric and not league gameweeks. Fallback path (`if not upcoming_rounds and upcoming:`) is unreachable when any played exist, so edge case at season start uses different branching without tests.
- **Screenshot**: `screenshots/adv-007-upcoming-by-round-collision.png` (JSON payload showing rounds 3 & 4 sharing same date, or round gaps)
- **Disposition**: REJECTED - Upcoming rounds are honestly documented as home-centric nth count, not official gameweeks; postponement collisions are inherent limitation surfaced in note. Refine semantics in Phase 3 live board, not Phase 0 blocking.

## ADV-008: Rate-limit / TOS amplification — `analyze_match` fans out to LEAGUES × seasons (up to 30 Understat fetches per request)

- **Severity**: HIGH
- **Steps to Repro**:
  1. Open Network tab → Match Deep-Dive → click 8 fixture cards rapidly.
  2. Observe backend logs / `get_league_data` calls: `for league in LEAGUES (5) for s in seasons_to_try (5)` plus fallback loop (`+5`) = up to 30 fetches per match. No shared cache, no debounce, no abort on navigation away.
  3. Script repro: `for i in {1..20}; do curl -s -X POST http://host/api/v1/analyze/match/28778 & done` → 600 upstream hits in burst.
- **Expected**: Single cached `get_league_data(league, season)` lookup per league/season per TTL, forecast resolved via direct `get_match_data` or indexed lookup; request de-duplicated; rate-limited (e.g. 2 rps) with `429` + `Retry-After`; respects Understat's site (no amplification).
- **Actual**: `AnalyticsService.analyze_match` does sequential nested loops over `LEAGUES` and `seasons_to_try = [DEFAULT_SEASON, DEFAULT_SEASON-1, DEFAULT_SEASON+1, 2025,2024]` with `await self.client.get_league_data(league,s)` each iteration, parsing full league payload to find one `id`. No `asyncio.gather` with semaphore, no `TTLCache`, no `_history_cache` reuse for forecast. Mean latency >2 s per match; burst multiplies. Understat may throttle/block rendering host. App has no `X-RateLimit` headers, no auth, so any visitor can amplify.
- **Screenshot**: `screenshots/adv-008-forecast-loop-waterfall.png` (Network / server log showing 25 sequential GETs to `understat.com/league/...`)
- **Disposition**: ACCEPTED -> DEF-008

## ADV-009: `rostersBlock` empty-vs-null confusion — "Rosters unavailable" shown even when payload is `{h:[],a:[]}` vs `null` indistinguishably

- **Severity**: LOW
- **Steps to Repro**:
  1. Analyze a future fixture (`isResult=false`) or a match where Understat returns `rosters: null` vs `{h:{}, a:{}}`.
  2. Observe Match report → "Match Rosters & Player Ledgers" card.
- **Expected**: Differentiated empty states: "Rosters not yet published (future fixture)" vs "Rosters unavailable (Understat payload missing)" vs populated table.
- **Actual**: Backend normalises `raw_rosters` dict → `{"h": [...], "a": [...]}`, but when both sides empty still produces `{h:[],a:[]}`. `rostersBlock` checks `if (!rosters || (!rosters.h && !rosters.a))` — but `[]` is truthy, so `{h:[],a:[]}` falls through to `if (!hRows.length && !aRows.length) return "unavailable"`. Both null and empty-array cases render identical generic "Rosters unavailable". No distinction for future fixtures where rosters legitimately don't exist yet. Also `_normalize_side` preserves insertion order of `raw_rosters.get("h")` dict values, which is arbitrary (Understat dict keyed by player id), so table row order is non-deterministic across loads.
- **Screenshot**: `screenshots/adv-009-rosters-unavailable-vs-future.png` (future fixture vs played fixture both showing same empty message)
- **Disposition**: ACCEPTED -> DEF-009

## ADV-010: Rotated y-titles accessibility — 10 px `#94a3b8` at `x=14` fails readability + screen-reader invisibility

- **Severity**: MED
- **Steps to Repro**:
  1. Player Career → any metric → enable macOS VoiceOver / Chrome Lighthouse Accessibility audit.
  2. Inspect SVG `<text x="14" y="…" fill="#94a3b8" font-size="10" … transform="rotate(-90 14 …)">xGChain_per90</text>` across `drawCareerChart`, `drawCareerGoalsVsXg`, `drawCareerInvolvementEvolution`, `drawSeasonLines`, `drawTrendChart`, `drawLuckChart`.
  3. Measure contrast: `#94a3b8` (≈ `rgb(148,163,184)`) on `--panel #121824` (≈ `#121824`) — Lighthouse flags `1.8:1` on graph area? Check also on `--bg #0c1017`.
- **Expected**: WCAG AA 4.5:1 for <18 px text, SVG `<title>`/`<desc>` or `aria-labelledby`, `role="img"`, yTitle not clipping axis ticks at any breakpoint.
- **Actual**: 10 px rotated text uses `#94a3b8` which at 10 px is considered "normal text" requiring 4.5:1; computed ratio on dark panel is ~4.1:1 (marginal) and text is only 10 px/7.5 px perceived due to rotation — fails readability at distance. No `aria-label`, no `role`. Tick labels (where present) sit at same left margin, so at 375 px the rotated title overlaps tick numbers (e.g., "10", "20" on Points progression). No `prefers-reduced-motion` or `prefers-contrast` handling.
- **Screenshot**: `screenshots/adv-010-y-title-a11y-rotate.png` (career chart with rotated title overlapping ticks + Lighthouse a11y panel + VoiceOver rotor showing no label)
- **Disposition**: ACCEPTED -> DEF-010

## ADV-011: 500-char title / metric overflow — hero pills & table headers overflow, no truncation

- **Severity**: LOW
- **Steps to Repro**:
  1. Player Career metric: craft a request with `seasons: [2019,2020,2021,2022,2023]` and observe hero pills concatenating via `windowBadge(d)` (`[w.start_date, w.end_date].join(" → ")`) with extremely long date windows, or manually inject via console: `drawCareerChart("careerChart", rows, "a".repeat(500))`.
  2. Observe yTitle rendering of a 500-char string.
- **Expected**: Long strings truncate with `…` / wrap, layout does not horizontal-scroll, no SVG text overflow outside card.
- **Actual**: `yTitle` is inserted verbatim into `<text>…${yTitle}</text>` with no `text-overflow`, `truncate`, or `maxLength`. A 500-char title extends far beyond `viewBox` ( >3000 px SVG text), causing horizontal scroll on the card (`overflow-x:auto` shows blank), and at 375 px pushes the chart off-screen. Hero pills (`hero-pill`) also have no `max-width` / `overflow:hidden`, so a long player/team name can break the top bar layout.
- **Screenshot**: `screenshots/adv-011-long-title-overflow.png` (500-char yTitle extending off SVG, pill overflow at 375 px)
- **Disposition**: REJECTED - api validates metricKey to known enum; 500-char injection is adversarial, not user requirement. Truncation guard can be added opportunistically but not Phase 0 blocker.

## ADV-012: Shot profile season fallback is opaque — shows prior season's zones without labelling which season

- **Severity**: MED
- **Steps to Repro**:
  1. Player → `Cole Palmer` (Chelsea) → request `seasons: [2025]` (or any season where groups payload missing for that year).
  2. Check response `shot_profile_detail` vs `seasons` requested.
  3. Observe UI: `Shot Zones (InsideBox / OutsideBox)` bar appears with no season qualifier.
- **Expected**: Label indicates which season's profile is displayed (e.g. "Shot Zones — 2024 (fallback: 2025 unavailable)") or explicitly hides when requested season missing.
- **Actual**: Backend:
  ```py
  season_for_profile = target_seasons[-1]
  profile = career_engine.shot_profile_for_season(groups, season_for_profile)
  if profile is None and len(target_seasons) > 1:
      for s_yr in reversed(target_seasons[:-1]):
          profile = ...
          if profile is not None: break
  ```
  If 2025 missing, it silently shows 2024 profile under the 2025 hero header (`· 2025` badge). No `profile_season` field is returned, so UI cannot disclose fallback. User assumes zones are for 2025. Same for `role_split`.
- **Screenshot**: `screenshots/adv-012-profile-fallback-opaque.png` (2025 request but zones from 2024, response comparison)
- **Disposition**: ACCEPTED -> DEF-011

## ADV-013: Enrichment is noop but appears as feature — dead `enrichment` field in player report, no UI surface, wasted fetch

- **Severity**: LOW
- **Steps to Repro**:
  1. `POST /api/v1/analyze/player` with any player → inspect JSON: `enrichment: {source:"none", honest_note:"Enrichment not configured (Understat-only in this deploy).", …}`.
  2. Check `app.js`: grep `enrichment` → zero references. Dashboard never renders market value, foot, height, Sofascore rating, strengths/weaknesses.
  3. Check `AnalyticsService.__init__(enrichment=None)` — default is `NoopEnrichmentProvider`, but `app/api.py` lifespan constructs `AnalyticsService(client=client)` with no enrichment injection, so every player request still does `await provider.enrich_player(...)` (a no-op) adding latency for no benefit.
- **Expected**: Either surface enrichment honestly (show "Market value unavailable — Understat-only deploy" badge) or avoid the await entirely when provider is noop, and document that `enrichment` is a future extension point not yet active.
- **Actual**: Every player request pays an extra microtask + `asdict` serialisation for a payload that is never displayed. Frontend has no placeholder, so user cannot tell why strengths/weaknesses are missing; `honest_note` is buried in JSON, never surfaced in the caveats box.
- **Screenshot**: `screenshots/adv-013-enrichment-noop-dead.png` (DevTools Response tab showing enrichment block vs UI absence)
- **Disposition**: REJECTED - enrichment seam ships intentionally as source:none for Phase 4; one async noop (~microseconds) overhead is acceptable and `honest_note` documents Understat-only deploy. Frontend will surface in Phase 4, not Phase 0 defect.

## ADV-014: `matches/rounds` `upcoming_by_round` and client `roundSelect` diverge — UI never shows upcoming even though API ships it

- **Severity**: LOW
- **Steps to Repro**:
  1. `POST /api/v1/matches/rounds` → response contains both `rounds` (played) and `upcoming_by_round` (fixtures with `isResult:false` + `forecast`).
  2. Open Match tab → observe `roundSelect` population: `roundsData.rounds.map(r=> …)` only. `upcoming_by_round` is never rendered, never selectable, never counted in `fixtureCountBadge`.
- **Expected**: Either `roundSelect` includes Upcoming rounds (with muted styling / forecast badge) or API does not send extraneous `upcoming_by_round` that bloats payload and confuses consumers.
- **Actual**: API adds `upcoming_by_round` (~10–15 extra rounds, each with matches) but client ignores it. Badge `n_played` shows only played count, payload size inflated ~2× for no UI benefit. If a consumer uses `rounds` expecting chronological gameweeks, they will miss future weeks; if they use `upcoming_by_round` they will see duplicate round numbers that overlap played rounds (since home-centric counting continues from played base), causing confusion.
- **Screenshot**: `screenshots/adv-014-upcoming-ignored.png` (Rounds API response showing upcoming_by_round vs roundSelect HTML with only played)
- **Disposition**: REJECTED - upcoming_by_round ships intentionally for Phase 3 live board; client wiring is Phase 3 scope. Shipping data before UI is not a Phase 0 defect, and payload ~2× is negligible.

---

### Notes on brute/abuse, empty-state, and input extremes also probed

- Input abuse: requesting `player_name="'" OR 1=1--` or `season=9999` returns 422 as expected; no injection observed. Empty leagues (e.g., `Ligue_1 2014` with few matches) correctly hit `latest_matches: []` empty state with "Fixtures Not Started Yet" CTA.
- Odd sequences: rapid toggle of `leaguePicker` while `loadRounds()` in flight leaves `state.roundsData` from prior league briefly stale until overwrite — no crash but flicker (not filed as separate issue, minor).
- Keyboard-only: `Tab` reaches `season-multi` buttons and `hero-pill` is not focusable (expected for read-only).

**Total findings: 14** · All triaged: 9 ACCEPTED (→ DEF), 5 REJECTED with reason.
