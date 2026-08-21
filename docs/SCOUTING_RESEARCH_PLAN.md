# Scouting, Tactical & Live Intelligence — Research & Integration Plan

**Branch:** `feat/next-work` · **Baseline commit:** `7d04c38` (merge feat/ui-ux-overhaul)  
**Date:** 2026-08-21 · **Author:** Delivery Lead (research pass)  
**Intent:** Understand what the app *is*, what Understat *can* give us, what scouts *actually need*, and chart a logical, staged integration of Transfermarkt / SofaScore / WhoScored without rebuilding the sound core.

> **User directive distilled:** “Learn and understand the app and its workings and its idea which is sound but needs work to be great. Efficient scouting tab + visuals. Tactical archetypes, live gameweek should kind of be there but check it if not lets add it. Logically and planned integration of transfer market, sofascore should be rich on all our visuals and plans. WhoScored — see what we will get from here. Also go through the understat api and see if we are not using its data points effectively and to its maximum potential. Check all the charts in the app and improve it. Mainly in trend charts — like these trends as is but axis needs to be added, do not change the axis but name it.”

---

## 1. What the App Is (Why It’s Sound)

**One-sentence idea:** Turn Understat’s public league/team/player/match JSON into *reproducible analytical answers* (not notebooks) — league lying tables, player radars, team pressing fingerprints, career trajectories, match xG stories, and Dixon-Coles / Elo forecasts — via one shared async `UnderstatData` client → pure `analytics/*` engines → FastAPI → vanilla JS SPA + canvas/SVG charts.

**Architecture sanity-checked:**

```
dashboard (app.js/index.html/styles.css)
   │  POST /api/v1/{analyze,compare,discover,predict,matches/rounds,ask}
   ▼
api.py  →  AnalyticsService →  analytics/{player,team,league,match,career,percentiles}  → JSON
        →  stat_data/understat.py (Utils.get_data → aiohttp → understat.com)
        →  ml/engine.py (Dixon-Coles, Elo, pi-ratings, XGB, Monte-Carlo)
        →  Wikidata SPARQL (birthdates/age, honest CC0)
```

**What’s strong (keep):** Pure engines with honest limitations; position-family percentile radars (not raw totals); multi-season merge logic (`_merge_league_players` sums counts, keeps latest identity, PPDA = latest rate); season-vs-season `position_trend` rebuilding the table per-date; `match_rounds` synthetic gameweek documented honestly; midnight-slate design system.

**What’s holding it back from “great”:**
- No persistent cache — every `/analyze/*` re-fetches live (Render free-tier bottleneck).
- Scouting is filter/rank + single-player deep dive; no *scouting contract* (watchlist, thresholds, vs template, shortlist export).
- Tactical archetypes exist as a 6-pillar radar fingerprint, not as *archetype clustering* (“high-press / control / transition / direct”).
- Live gameweek is synthetic (`home nth match`), not a real gameweek/live tracker.
- External market/value/contract, defensive-action, and rating data missing — precisely what Transfermarkt / SofaScore / WhoScored would add if integrated *as enrichment*, not scrape.
- Chart trends are loved-as-is but axes are unlabeled (see §3).

---

## 2. Understat API — Are We Using It to Its Maximum?

### 2.1 Endpoint inventory (verified 2026-04-03 live capture)

| Endpoint | Contract | Current use | Missing opportunity |
|---|---|---|---|
| `GET /getLeagueData/{league}/{season}` | `teams{history[date,h_a,w/d/l,scored/missed,pts,xG/xGA…npxGD,ppda{att,def},ppda_allowed,deep,deep_allowed,xpts]}`, `players[]` (season totals), `dates[id,h/a,title,datetime,isResult,goals{x},xG{x},forecast{w,d,l}]` | League table, team history/PPDA, league players, `dates`→`match_rounds`, head-to-head | `forecast{w,d,l}` from Understat model never surfaced — free calibration vs our Dixon-Coles; `players` includes `npg`/`npxG` split rarely charted; `deep`/`deep_allowed` per-match not trended |
| `POST /main/getPlayersStats` | `league|team,season,date_start/end` → `players[]` with `id,player_name,team_title,position,games,time,goals,xG,npxG,npg,assists,xA,shots,key_passes,xGChain,xGBuildup,yellow/red` | `get_league_player_stats`, `get_team_player_stats` → all scouting/discovery/squad | Date-windowed correctly; but `xGChain/xGBuildup` never ranked vs *squad* context in discovery cards; no per-90 vs team-share viz |
| `GET /getPlayerData/{id}` | `shots[X,Y,xG,minute,result,situation,shotType,lastAction,player,h_team,a_team,date,season,h_a,player_assisted]`, `matches[per-match log]`, `groups{season,position,situation,shotZones,shotTypes}`, `minMaxPlayerStats`, `player{favorite_position}` | Shots pitch map, career `groups`→`shot_profile_for_season` + `role_split`, `_favorite_position` cache | `shotZones` (OutsideBox/InsideBox/Central…) and `shotTypes` (Header/Foot…) are fetched but only surfaced in career table `shot_profile`; not charted on player profile; `player_assisted` (who assisted) never used — free “chemistry” graph; `matches` log never timeline-charted |
| `GET /getTeamData/{team}/{season}` | `statistics`, `players`, `dates` | Only via `statistics` fallback; league-sourced history preferred (correct — team page lacks PPDA) | Fine as is |
| `GET /getMatchData/{id}` | `rosters{h,a}[player stats per match]`, `shots{h,a}[]` | `get_match_shots` + narrative; `rosters` fetched but not exposed via `team_shot_map` split logic uses `h.title` heuristic | `rosters` per-match individual xG/xA/minutes is gold for *live gameweek* player-of-match + post-match ratings; currently backend discards it after shots |
| `GET /main/getPlayersName/{q}` | `response.players[id,player,team]` | Search resolve + league-first accent folding | Good |
| `POST /main/getPlayerMatches/{id}` | `response{players,matches,lastMatch}` | Rarely; compare uses `getPlayerData().matches` instead | `lastMatch` could power “latest form” sparkline without extra fetch |
| `GET /getStatData` | Home monthly stats by league | Not surfaced | Could feed lightweight “league pace” header without full table fetch |

**Verdict:** We use ~80% of what Understat gives us *honestly*. The 20% left is mostly *not new fetches* — it’s fields we already fetch but drop before rendering (Zones/Types, Assisted, Rosters, Forecast, minute-buckets). Fastest win is chart them.

### 2.2 Concrete under-use to fix (no new endpoint needed)

1. **Player shot Zones & Types → stacked bars on Player Profile** (next to `playerShotMixBars` situations). Same `groups` payload, zero extra call.
2. **`player_assisted` → “who assisted / who was assisted by” table.** Already in every shot.
3. **`rosters` per match → Live Gameweek player cards** (goals, xG, shots, key_passes in that match). Already fetched in `get_match_data`, just not returned by `analyze_match`.
4. **`forecast{w,d,l}` from `dates` → underdog/value flag** vs our Dixon-Coles probs (honest: label as “Understat model”, not ours).
5. **`deep` & `deep_allowed` rolling trend** (we trend `npxGD/xG/PPDA` but not `DC/g`). One line added to `metric_trends`.
6. **`matches` log → mini sparkline on Discover cards** (goals/xG last 5) without extra fetch — `player_data.matches` already cached per `_favorite_position` flow.

---

## 3. All Charts in the App — Audit & Axis Fix

### 3.1 Inventory (11 primary visuals; scales must NOT change)

| # | Chart | Function | Container | Size | Technique | X axis | Y axis | Axis title today | Fix (name only, no scale change) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Pitch shot map + Gaussian heatmap | `renderPitchHeatmap` | `matchPitch, playerPitch, teamForPitch, teamAgainstPitch` | 700×440 canvas | canvas + offscreen ImageData | X (0→1) → pitch length | Y (0→1) → pitch width | none (pitch lines imply) | Keep; no cartesian axes needed — pitch is self-labeled |
| 2 | Cumulative xG timeline | `drawXgTimeline` | `xgtl` | 1100×260 SVG | path + dots | Minute (0..90+) | cumulative xG (0..max 0.5) | bottom: “Minute →” ✓ has label · left: “xG ↑” vertical ✓ | ✅ Already correct — add tick labels `0,15,30,45,60,75,90` (text only) |
| 3 | Career metric per season | `drawCareerChart` | `careerChart` | 1100×260 SVG | path | Season index (categorical 2019…2025) | metric value (0..max) | y label is series name only, x labels are seasons | Add `xAxisLabel: "Season"` centered, `yAxisLabel: entry.label \|\| metricKey` rotated — keep `x(i),y(v)` math identical |
| 4 | Goals vs xG bars + dashed line | `drawCareerGoalsVsXg` | `careerGoalsVsXgChart` | 540×240 SVG | rect + path dashed | Season (cols) | Goals/xG (0..maxVal) | none | Add `x: Season`, `y: Goals / xG` (reuse maxVal) |
| 5 | xGChain vs xGBuildup /90 | `drawCareerInvolvementEvolution` | `careerInvolvementChart` | 540×240 SVG | 2 paths | Season | /90 value | none | Add `x: Season`, `y: Per 90 value` |
| 6 | Season points progression | `drawSeasonLines` (points) | `seasonPoints` | 1100×240 SVG | path + dashed xPTS | Matchday index | Points (0..ymax) | “Points” top-left, “Matchday →” bottom ✓ | Add explicit yAxisTitle `Points` rotation, keep ymax = max(points,xpts) |
| 7 | Season rank progression | `drawSeasonLines` (rank invert) | `seasonRank` | 1100×240 SVG | path | Matchday | Rank (1..n_teams, inverted y0+…) | “Table Rank (1=Top)” top-left, “Matchday →” ✓ | Add yAxisTitle `Rank (1 = top)` rotated, xTitle `Matchday` — keep invert `y=(v-1)/(ymax-1)` |
| 8 | Luck curve | `drawLuckChart` | `luckChart` | 540×220 SVG | path | Date order (match index) | cumulative G−xG (lo..hi centered on 0) | top-left “Cumulative Goals − xG Overperformance” | Add `x: Match (chronological)`, `y: Cumulative G − xG` rotated |
| 9 | 5-match rolling trend | `drawTrendChart` | `trendChart` | 1100×240 SVG | path, zero line | Date index (rolling window) | metric centered on 0 (−allMax..+allMax) | top: `Rolling 5-Match {label}` only | Add `x: Match date (rolling avg)`, `y: {label} (5-match avg)` — keep `y = y1-((v+allMax)/(2*allMax))*(y1-y0)` |
| 10 | Divergence waterfall | `drawLeagueDivergenceChart` | `leagueDivergenceChart` | 1100 × rows*38+70 SVG | rect bars | xPTS gap (negative left, positive right, midX center) | Teams (ranked by gap) | headers “HARSH ← / FLATTERING →” + center line, no axis units | Add `xAxisLabel: Points gap (PTS − xPTS)` below, `yAxisLabel: Team (sorted by gap)` rotated — bar math unchanged |
| 11 | Tactical quadrant | `drawLeagueTacticalQuadrant` | `leaguePressQuadrant` | ~1100×480 SVG | scatter + crosshairs | PPDA inverted (7→18 left→right but code does `18-ppda`) | DC/g | subtitle explains axes, crosshairs are “league baseline” | Add explicit `xAxisTitle: PPDA (lower = higher press, inverted →)` + `yAxisTitle: Deep completions / game`, keep x = `(18-ppda)/11`, y = `dc/12` |
| 12 | Radars (player + team DNA + compare) | `drawRadar`, `drawTeamTacticalRadar`, `drawCompareRadar` | `playerRadar, teamTacticalRadar` | 320–360 SVG | polygon | angular categories (not cartesian) | radial 0..100% | category labels at spokes only | No cartesian axes — keep as is; optionally add `0/25/50/75/100%` ring labels (not cartesian) |
| 13 | Shot-mix stacked bar | `playerShotMixBars` | under Finishing diagnostics | flex div 9px bar | div widths `count/total` | Share 0..100% | single row | legend only | Keep |

**Required invariant:** `// Axis fix = labels only` — do NOT rescale `allMax`, `maxVal`, `maxMatchdays`, `ppda→(18-ppda)/11`, rank inversion, or rolling `allMax=Math.max(...vals.map(Math.abs))`. Tests will assert scales unchanged by snapshot of `y()`/`x()` math.

**Implementation note for dev:** Each `draw*` gets 2 extra `<text>` nodes: `xAxisTitle` centered at `(x0+x1)/2, h-6` and `yAxisTitle` at `14, (y0+y1)/2` rotated −90°. No new params, no layout change, no `padL` change beyond existing.

---

## 4. How to Scout Efficiently — Domain Research & Tab Vision

### 4.1 What “efficient scouting” means (from real workflows)

A scout’s loop is: **Filter → Rank → Profile → Compare → Shortlist → Track**. Current app does 1–4 well; 5–6 are missing.

Efficient = *fewest clicks to a defensible shortlist*.

**Metrics hierarchy scouts use (mapped to Understat where possible):**

```
Tier 1 (availability): minutes ≥ threshold, age, position/favorite_position, team
Tier 2 (process, not variance): npxG/90, xA/90, xGChain/90, xGBuildup/90, xG/shot, NPxGD context
Tier 3 (style): PPDA team context, deep completions share, shot Zones/Types/Situations
Tier 4 (variance check): G−xG, CI, finishing overperformance — diagnostic, not ranking
Tier 5 (market): value, contract end, minutes trend — NOT in Understat (see §7)
```

**Gaps in current Discover tab:**
- No per-90 *vs absolute* toggle (scouts rank by /90 but sanity-check totals).
- No “template player” search (find similar *to* Haaland, not just similar *within* cluster).
- No thresholds (e.g., `min npxG/90 0.35 AND min xA/90 0.15`).
- No watchlist/shortlist persistence + CSV export (scouts need to hand a list to a DoF, not screenshots).
- Cards show team PPDA as full-season, not date-windowed — honestly labeled but confusing.
- No *age curve* viz on the grid (scouts scan age vs output).

### 4.2 Proposed Scouting Tab v2 (visuals-rich, no external data yet)

```
[Filters: Season(s)×5 | Positions×8 | Min mins 900 | Rank by npxG/xA/Chain/Buildup/goals/assists/age ± thresholds | Age min/max | Date window]
   → Grid (20/50/100) with columns: Rank | Player (→ profile) | Age · Pos | Team (PPDA) | Mins | npxG /90 · xA /90 | Chain/90 · Buildup/90 | xG/shot | G−xG | Sparkline (last-5 xG)
   → Actions per row: ★ Watchlist | ⇄ Compare basket | ↗ Profile
   → Footer: Export CSV (id,name,team,age,pos,minutes,per90s,g-xg) + Save watchlist to localStorage

Detail on click expands inline: Zones stacked bar, Types bar, Assisted-by network (top 3 assisters via player_assisted), Involvement share.
```

**Charts to add/reuse:**
- Age vs npxG/90 scatter (scouting quadrant: young + productive = priority).
- Reuse `drawRadar` overlay for watchlist compare (up to 4) — already exists in Compare tab.

### 4.3 Success criteria for “efficient”

- From landing on Discover to shortlist of 10: ≤ 3 interactions (filter → sort → ★).
- Every ranking column is sortable; every badge links to full Player Profile.
- Honest caveat: “Per-player pressing not in Understat; team PPDA is context only.”

---

## 5. Tactical Archetypes — From Fingerprint to Clustering

**Current:** Team Tactical DNA is a 6-pillar normalized radar (Attack xG/g, Defense inverted xGA/g, NPxGD, Press PPDA inverted, Press Resist OPPDA, Box Threat DC/g). It’s a *fingerprint*, not a *type*.

**Needed:** Clustering into *archetypes* so a user can answer “what kind of team is Brighton?”

**Research-backed archetypes (7, k-means on league-standardized features):**

| # | Archetype | Signature (standardized) | Example tell |
|---|---|---|---|
| 1 | **Control & Territory** | High DC/g + low xGA/g + low PPDA | Man City, Arsenal |
| 2 | **High Press & Transition** | Low PPDA + high npxGD + mid DC | Liverpool |
| 3 | **Direct & Aerial** | High xG/g but low xGChain/90 share? Actually team proxy: High PPDA (low press) + high Deep Allowed, low buildup | Burnley-style |
| 4 | **Set-Piece Heavy** | High SetPiece xG share (via situational_xg_share) | (varies seasonal) |
| 5 | **Low Block & Counter** | Low DC/g + low PPDA allowed? High OPPDA resistance + low xG/g but ok xGA | |
| 6 | **Expansive / Chaos** | High xG/g *and* high xGA/g | |
| 7 | **Balanced Mid** | Near 0 z across pillars | |

**Implementation (honest, deterministic, no ML infra):**
- Precompute per-team z-scores vs league mean/std on 5 features already in `style_profile`: `xG_per_game, xGA_per_game, npxGD, PPDA, deep_completions/matches`.
- Hardcode archetype centroids from historical labeling (or simple rule-based thresholds first — e.g., PPDA <10 & DC/g >10 → Control). Ship rules v1; log cluster assignment for future k-means training when we have historic seasons cached.
- UI: badge on Team Analytics hero + “Archetype peers” grid (teams sharing archetype) + small explainer `Tactical archetype: Control · Similar: Arsenal, Man City (z-dist 0.3)`.

**Lives in:** `analytics/team.py` new `tactical_archetype(style, league_mean, league_std) → {archetype, confidence, peers}`; frontend reuses radar + adds badge.

---

## 6. Live Gameweek — Does It Exist? What to Add?

**Today:** `POST /api/v1/matches/rounds` → `AnalyticsService.match_rounds()` groups *played* matches by `home nth match` (honestly documented: “Round = home team’s nth league match; postponements shift”). Recent fixtures grid auto-loads 18 latest; Deep Dive is post-match only. No live tracker, no “GW5” label, no upcoming with odds/xG forecast, no in-match timeline.

**Needed:** Two modes — **Post-match Gameweek browser** (what we have, polish it) + **Live/Matchweek Live tracker** (new).

**Live design (minimal, honest):**
- Reuse `dates` with `isResult=false` (fixtures) → add `upcoming_by_round` alongside `by_round`. Each fixture shows `forecast{w,d,l}` from Understat (we already have it but drop it) as “model-implied win%”.
- New endpoint: `POST /api/v1/matches/live` returns `{league, season, round_current, fixtures: [id, date, home, away, isResult, goals, xG, forecast], live_note: "No in-play polling — Understat updates post-match; live is kickoff-aware fixture board."}`. Honest: we cannot poll live xG in-play from Understat; we *can* be the best fixture board with xG context pre/post.

**Future live polling (staged, not v1):** If later we add SofaScore polling, swap source; contract stays same.

**Visual:** Add tab segment on Match view: `Recent Fixtures | Gameweek Board (Rounds 1..38)` — rounds as pills, fixture cards show `FT · xG 1.4–0.9` or `Upcoming · Understat forecast: H 42% D 25% A 33%`. Click → same Deep Dive.

---

## 7. Planned Integration of Transfermarkt / SofaScore / WhoScored — What We Actually Get

### 7.1 Principle: **Logical & Planned, Not Scraped-Yesterday**

Understat remains the *source of truth* for xG process. External sources are **enrichment adapters**, not replacements — optional, cached, with graceful degradation if absent. No unauthenticated scrape in request path; adapters run as *batch enrichment* with explicit consent + rate limits. We design the seam now, ship Understat-native first, then plug adapters.

### 7.2 What each source uniquely offers (and what Understat lacks)

| Source | What it adds that Understat does NOT have | Visual / plan enrichment | Technical reality |
|---|---|---|---|
| **Transfermarkt (TM)** | Market value (EUR, history), contract expiry, agent, foot, height/weight, injury history, transfer history/fees, loan status, national team, youth club | **Squad table:** €Value column, sparkline value trend, “contract expires | Market value is enrichment; TM has no official API, TOS prohibits scraping. Legal path: manual CSV import / TM-provided export, or licensed feed. Adapter interface is `market_value(player_name,team_hint)→{value_eur, contract_end, foot}` with `source: "transfermarkt:{date\|manual}"` and stale-cache fallback. | Highest scout value, lowest automation. Ship as *import* first. |
| **SofaScore (SS)** | Live player ratings (6-10), heatmaps (pass/xT zones), duel%/aerials, tackles/interceptions, SofaScore team form streaks, live lineups & events | **Lead to:** pass networks, duel maps, **pressing activity** (true pressures vs our `lastAction` output proxy), live tracker | SS has an undocumented JSON API used by their web app (reverse-engineered). Stable but unofficial; rate-limited. Feasible as *optional* `LiveClient` with circuit breaker. Adds pressure counts, duels, ratings that Understat never will. |
| **WhoScored (WS)** | WhoScored rating (0-10), detailed defensive stats (tackles, interceptions, clearances, blocks), dribbles, dispossessed, key passes split, strengths/weaknesses tags, style tags | **Scouting cards:** “Dribbler / Aerial threat / Weak: Discipline” tags; **Team style:** long ball %, possession %, crosses. Enriches radar with *duel* and *dribble* axes if available. | WS is Cloudflare-protected, TOS strict. Best as *post-match enrichment* via licensed Opta feed that WS wraps. Adapter is provider-agnostic: `enrichment_provider: "whoscored|opta|manual"` |
| **Overlap** | All three give age/DOB (we use Wikidata). All give injuries. TM+SS+WS give lineup/formation. | Single enrichment layer can serve all UIs without N clients in request path. | Normalize to one `ExternalEnrichment` schema. |

### 7.3 What it makes *richer* (concrete, by view)

- **Player Profile:** TM value pill + contract badge next to age; SS rating trend sparkline + heatmap thumbnail (or “not yet enriched” gentle empty state); WS strengths/weaknesses tags under radar.
- **Team Analytics — Squad:** Add columns Value, Contract, WS rating (if enriched); age curve already there via Wikidata. Color value vs xG to flag “undervalued xG”.
- **Discover / Scout:** New `order_by: market_value, whoscored_rating, sofascore_rating` (only when enrichment present; else disabled with tooltip). Filter `contract ≤ 1 year` = expiring-targets view scouts love.
- **Match Deep Dive:** SS live events timeline (if available) alongside our xG timeline; WS defensive actions table (tackles/ints) alongside big chances.

### 7.4 Seam design (so we can ship Understat-native now, add enrichment later)

```python
# analytics/enrichment.py (new, pure)
@dataclass
class ExternalEnrichment:
    source: str          # "transfermarkt|sofascore|whoscored|manual|none"
    fetched_at: str|None
    market_value_eur: int|None
    contract_end: str|None  # YYYY-MM-DD
    foot: str|None
    height_cm: int|None
    sofascore_rating: float|None
    whoscored_rating: float|None
    strengths: list[str]
    weaknesses: list[str]
    honest_note: str     # e.g., "Market value from TM import 2026-08-15; not refreshed live."

class EnrichmentProvider(Protocol):
    async def enrich_player(self, player_name, team_hint) -> ExternalEnrichment: ...
    async def enrich_team_squad(self, team_name, season) -> dict[str, ExternalEnrichment]: ...

class NoopEnrichmentProvider:  # v1 ships with this
    async def enrich_player(...): return ExternalEnrichment(source="none", ...)
```

- `AnalyticsService` takes `enrichment: EnrichmentProvider | None`; if `None`, JSON omits `enrichment` field (frontend shows “enrichment not configured” hint, no breakage).
- Batch job `scripts/enrich_tm_import.py` reads `data/transfermarkt/manual.csv` → SQLite `cache/enrichment.db` → provider reads cache. No live TM scrape in v1.
- SS/WS live polling (if ever) is a *separate* `LiveData` service, not mixed into Understat path; respected via `FOOTBALL_LIVE_PROVIDER=none|sofascore`.

**Honest TOS note to surface in UI:** “Market values from Transfermarkt import (manual, {date}); not affiliated. Ratings from {source} where shown.” Never imply live TM scraping.

---

## 8. Phased Roadmap (Ship in Order — Each Phase Shippable)

| Phase | Name | Backend | Frontend | Charts | QA gate |
|---|---|---|---|---|---|
| **0** | **Axis labels + Understat max-use (no new data)** | Wire unused fields through: `groups.Zones/Types`, `rosters`, `forecast`, `deep` trend, `player_assisted` | Add axis titles to 8 trend charts (see §3.1); add Zones/Types stacked bars, Assisted table, Deep/g trend line, Forecast pills | No scale change; snapshots must pass | Visual diff + unit tests assert labels present, scales same |
| **1** | **Scouting v2** | Extend `discover_players` with per-90 toggle + thresholds + template search (cosine vs template vector) + `age_scatter` data in response | New Discover v2 grid, watchlist localStorage + CSV export, age vs npxG scatter, per-row sparklines | Scatter: x=age, y=npxG/90 (1100×320, axes labeled) | E2E: filter→rank→watchlist→export |
| **2** | **Tactical Archetypes** | `tactical_archetype()` rules + league z-scores; include in `analyze_team` & `analyze_league` (archetype per team) | Badge on Team hero + archetype peers grid; League archetype legend with filter pills | No new chart, reuses radar | Unit test archetype for known teams (Man City → Control) |
| **3** | **Live Gameweek board** | `match_rounds` → also return `upcoming_by_round` + `forecast`; new `POST /matches/live` | Round pills + `Recent | Gameweek 1..38` toggle on Match view | — | E2E: select round 1 fixture → Deep Dive |
| **4** | **External enrichment (TM manual first)** | `EnrichmentProvider` seam + `enrichment.db` SQLite + `scripts/enrich_tm_import.py` + wire `market_value_eur/contract_end` into `analyze_player` & `discover` & `team squad` | Value pill + contract badge + enriched sort options (disabled when `source=none` with tooltip) | Value sparkline if history present | E2E with fixture `manual.csv`; graceful when file absent |
| **5** | **SS/WS live (optional, gated)** | `LiveData` provider (SofaScore polling, feature-flagged) → enrich `analyze_match` rosters with ratings/duels | Live rating column on Match Deep Dive rosters | Duel win% bars | Flag OFF by default; adversary review for rate-limit abuse |

**You are here →** End of research pass; ready to start **Phase 0**.

---

## 9. API Contract — Fixed Before Code (Phase 0 + Seams for 1–4)

All existing routes unchanged (backward compat). Scale of charts unchanged.

### 9.1 Phase 0 — Enrich existing payloads (additive, optional fields)

```jsonc
// POST /api/v1/analyze/player  (additions)
{
  // ...existing player, per90_breakdown, radar, etc...
  "shot_profile_detail": {               // from groups.situation/zones/types, null if absent
    "situations": [{ "name": "OpenPlay", "shots": 42, "goals": 9, "xG": 7.8, "xG_share": 0.63 }],
    "zones":      [{ "name": "Inside Box", ... }],
    "types":      [{ "name": "RightFoot", ... }]
  },
  "assisted_network": {                  // from shots[].player_assisted, null if none
    "top_assisters": [{ "assister": "De Bruyne", "assists_xG": 1.4, "count": 3 }],
    "top_assisted":  [{ "assisted": "Haaland", "xG": 2.1, "count": 4 }]
  },
  "enrichment": {                        // Phase 4 seam, null in Phase 0-3
    "source": "none",
    "market_value_eur": null,
    "contract_end": null,
    "sofascore_rating": null,
    "whoscored_rating": null,
    "honest_note": "Enrichment not configured (Understat-only in this deploy)."
  }
}

// POST /api/v1/analyze/match/{id}  (additions)
{
  // ...existing narrative, shot_map, xg_timeline, big_chance_inventory, situation_breakdown...
  "rosters": {                           // from get_match_data.rosters, null if absent
    "h": [{ "player_name": "Saka", "goals": 1, "xG": 0.6, "shots": 3, "key_passes": 2 }],
    "a": [...]
  },
  "forecast": { "w": 0.42, "d": 0.25, "l": 0.33, "source": "understat" } // from dates.forecast, null if match not in league dates
}

// POST /api/v1/analyze/team  (additions)
{
  // ...existing style, ppda_home_away, form_momentum, position_trend, metric_trends ...
  "archetype": {                         // Phase 2, null until then
    "label": "Control & Territory",
    "confidence": 0.78,
    "peers": ["Arsenal", "Man City"],
    "honest_note": "Rule-based on z-scores vs league; not a learned cluster in v1."
  },
  "metric_trends": {
    // existing: dates, xG_for, xG_against, goals_for, goals_against, npxGD, xPTS, PPDA, window
    "deep_for":    [...],                // new in Phase 0 (DC/g 5-match roll)
    "deep_against":[...]                 // ODC/g
  }
}

// POST /api/v1/matches/rounds  (additions, non-breaking)
{
  "league_name": "EPL", "season": 2025, "n_played": 320,
  "rounds":            [{ "round": 1, "matches": [...] }], // existing: played matches by synthetic round
  "upcoming_by_round": [{ "round": 12, "matches": [{ "match_id": "...", "date": "...", "home": "...", "away": "...", "forecast": { "w":0.42,"d":0.25,"l":0.33 }, "isResult": false }]}],
  "latest_matches": [...],
  "note": "Round = home team's nth league match (Understat has no official label). Forecast from Understat dates.forecast where available."
}

// NEW in Phase 3 — feature-flagged
// POST /api/v1/matches/live  { league_name, season }
{
  "league_name": "EPL", "season": 2025, "round_current": 12, "fixtures": [...], "note": "Live is kickoff-aware fixture board; Understat updates post-match."
}
```

**Pact:** Frontend may read new keys if present, must not break if absent. Backend never removes existing keys; axis scales never change — tests will fail the build if `y()` normalization constants change.

### 9.2 Query compatibility

- `POST /main/getPlayersStats` already supports `date_start/date_end` — scouting thresholds/date windows reuse it.
- `discover_players` Phase 1 additions are additive query params: `per90_sort: bool`, `min_npxG_per90, min_xA_per90, template_player_name` — old calls without them behave identically.

---

## 10. Task Specs per Developer (Phase 0 — Dispatchable Now)

### Backend-dev — “Understat Max-Use + Arcade Seams”

**What to build:**
- In `analytics_service.py:analyze_player` — attach `shot_profile_detail` (Zones/Types) via `career_engine.shot_profile_for_season`’s `_share_rows` helpers already; wire `assisted_network` by aggregating `shots[].player_assisted`; add `enrichment: {source:"none"}` stub so contract is stable.
- In `analytics_service.py:analyze_match` — return `rosters` (already fetched via `get_match_data`) + `forecast` by looking up `get_league_data` dates for this `match_id`.
- In `analytics/team.py:metric_trends` — add `deep_for` / `deep_against` 5-match rolls via `deep`/`deep_allowed`.
- Add `analytics/enrichment.py` with `ExternalEnrichment` dataclass + `NoopEnrichmentProvider` (no I/O).
- In `match_rounds` — also build `upcoming_by_round` from `isResult==false` rows + attach `forecast` per match.

**Unit tests to add (TDD):**
- `test_player_shot_zones_types_wired` — mock `get_player_data` groups with 2 zones + 2 types → `shot_profile_detail.zones/types` length 2, shares sum ≈1.0.
- `test_match_rosters_and_forecast_returned` — mock `get_match_data` rosters + league dates with forecast → `rosters.h` present, `forecast.w` ~0.42.
- `test_metric_trends_deep_rolls` — `metric_trends("deep_for").length == dates.length`, window 5.
- `test_enrichment_noop_source_none` — `analyze_player(...).enrichment.source == "none"` when no provider injected.

**Serves:** User asks “are we using data points to max” (all 4), plus seams for Transfermarkt/SS/WS without live scrape.

### Frontend-dev — “Axis Titles (No Rescale) + Zones/Types/Assisted/Rosters”

**What to build:**
- In `app.js` — add axis titles to **8 trend charts** (careerChart, careerGoalsVsXg, careerInvolvement, seasonPoints, seasonRank, luckChart, trendChart, league quadrilateral/divergence). Two `<text>` nodes per chart; do **not** change `x(i)`, `y(v)`, `allMax`, `maxVal`, `maxMatchdays`, rank inversion, or `padL` beyond existing.
- In Player Profile render — next to `playerShotMixBars` (situations), add **Zones** and **Types** stacked bars (reuse `playerShotMixBars` colors/logic).
- Assisted network table: “Top assisters (gave you xG)” / “Top assisted (you created for)”.
- Match Deep Dive — **Rosters** two-column table (H/A) under xG timeline; **Forecast** pill in hero if `forecast` present.
- Depth trend line in Team Analytics rolling selector: add `deep_for/deep_against` to `#trendMetric` options.

**Unit/visual tests:** Snapshot SVG string contains `>Season<`, `>Goals / xG<`, `>Matchday<` etc.; assert no change to `y1 - (v / allMax) *` literal via grep in test; Playwright screenshot of each chart before/after (labels appear, curves identical).

**Serves:** “axis needs to be added, do not change the axis but name it” + “check all charts and improve” + richer visuals without new fetches.

### QA (after both report done)

- Run `uv run python -m unittest discover -s tests -v` + frontend screenshot matrix (match / player / team / league / career — all charts).
- E2E: `discover → profile → career` path still works; `match rounds → deep dive` shows new rosters/forecast; axis titles visible at 375px & 1440px.
- Open `DEFECTS.md` for any adversary finding.

### Adversary

- Short hostile pass over axis labels (overlap at narrow viewport?), rosters PII (none), forecast misattribution (must label “Understat model, not ours”).

---

## 11. What We Get from WhoScored (Dedicated Answer)

WhoScored sits on **Opta event data** and publishes what Understat deliberately does not:

| WhoScored field | Understat equivalent? | Why it matters to scouting |
|---|---|---|
| **WhoScored rating 0–10 per match** (form-weighted) | No — we have percentile radars, not single-number match ratings | Scouts’ “form” card at a glance; complements xG |
| **Tackles / Interceptions / Clearances / Blocks / Duels won% / Aerials won%** | No — Understat has no defensive event data, only shots | Adds the defensive half of a scouting report (especially D/M) |
| **Dribbles attempted/completed, Dispossessed, Key passes split (cross vs through ball)** | `key_passes` total only in Understat | Separates “progressive carrier” from “chance creator” |
| **Strengths/Weaknesses tags** (“Aerial duels · Strong”, “Discipline · Weak”) | No | Pre-read for a manager; cheap coaching insight |
| **Team style metrics** (% long balls, % possession, crosses/game) | Approximated via PPDA/DC but not direct | Archetype labeling becomes data-driven, not heuristic |

**What we will NOT get (or shouldn’t pretend to):** Event coordinates/pitch maps at WS fidelity without a licensed Opta feed; live in-play xG polling (Understat + SS are post-match authoritative anyway).

**Planned use:** Same `ExternalEnrichment` seam — WS fields are *optional columns/tags*, never a gate on Understat-native features. Ship Player Profile tags first; team style enrichments later.

---

## 12. Decisions & Non-Goals for Now

- **We will NOT scrape Transfermarkt/SofaScore/WhoScored live in the request path in Phase 0–4.** TM enrichment is a manual CSV import; SS/WS are behind a feature flag with circuit breaker if ever polled. This keeps us TOS-honest and Render-free-tier safe.
- **We will NOT change chart scales.** Every `y(v)` normalization stays byte-identical; only labels added. Guarded by tests.
- **We will NOT replace Wikidata age via TM** — Wikidata remains age truth (CC0), TM enriches value/contract only.
- **We will NOT rank by G−xG** — finishing variance stays diagnostic, not a ranking.

---

## 13. Risks & Honest Caveats to Keep Surfacing

- **Understat is unofficial** — breaks if they change `getLeagueData` shape; our `AUDIT.md` captures this, `with_headers` handling already cushions it.
- **Market values are perishable** — TM import must be dated; stale values are worse than no values. Show `fetched_at`.
- **SS/WS unofficial APIs drift** — feature flag + `Noop` fallback guarantees the app works with `source=none`.
- **Squad PPDA caveat stays:** per-player press counts don’t exist; team PPDA is full-season context. Don’t hide it to make scouting look richer.

---

## 14. Next Action (for Delivery Lead)

1. Freeze this doc at `docs/SCOUTING_RESEARCH_PLAN.md` on `feat/next-work`.
2. Dispatch **Phase 0** in parallel (backend-dev + frontend-dev) — specs above, API contract §9.1 is fixed before code.
3. After both report done + QA screenshots, triage adversary findings, then walk Phase 1 scouting v2 (template search + watchlist + age scatter) as next dispatched phase.

*All code paths stay honest, Understat-native first, external as enrichment — the idea stays sound, the execution becomes great.*
