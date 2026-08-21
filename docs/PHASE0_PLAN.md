# Phase 0 Plan — Understat Max-Use + Axis Labels (No Rescale)

**Branch:** `feat/next-work` · **Baseline:** `7d04c38` · **Depends on:** `docs/SCOUTING_RESEARCH_PLAN.md`
**Goal:** Prove we honor *every* Understat data point. Surface fields we already fetch but drop, add axis titles to trend charts without changing a single scale, and open the `ExternalEnrichment` seam (`source:"none"`). Zero slop. One integrated scouting evolution inside the existing **Discover & Scout** tab.

---

## 1. API Contract (frozen — frontend & backend start together)

All changes additive, optional keys. Frontend must not break if key absent. No scale constant changes.

### 1.1 `POST /api/v1/analyze/player` — additions

```jsonc
{
  // ...existing: player, per90_breakdown, involvement_profile, shot_selection,
  //             finishing_overperformance, radar, creative_dominance, similar_players,
  //             pressing_output, limitations, shots[], date_window, seasons

  "shot_profile_detail": {               // ← from getPlayerData.groups; null if groups absent
    "situations": [{"name":"OpenPlay","shots":42,"goals":9,"xG":7.80,"xG_share":0.63,"_source":"groups.situation"}],
    "zones":      [{"name":"InsideBox","shots":38,"goals":8,"xG":9.10,"xG_share":0.74,"_source":"groups.shotZones"}],
    "types":      [{"name":"RightFoot","shots":30,"goals":6,"xG":5.20,"xG_share":0.42,"_source":"groups.shotTypes"}],
    "role_split": [{"role":"FW","games":28,"minutes":2280,"_source":"groups.position"}] // starter/sub split
  },
  "assisted_network": {                   // ← from shots[].player_assisted ; null if no shots
    "top_assisters": [{"assister":"De Bruyne","count":3,"assists_xG":1.40}], // who gave you xG
    "top_assisted":  [{"assisted":"Haaland","count":4,"xG":2.10}],           // who you gave xG to
    "honest_note": "Aggregated from shots.player_assisted (Understat shot assists, not Opta key passes)."
  },
  "enrichment": {                         // seam for Transfermarkt/SS/WS; v1 = Noop
    "source":"none",
    "market_value_eur": null, "contract_end": null, "foot": null, "height_cm": null,
    "sofascore_rating": null, "whoscored_rating": null, "strengths":[], "weaknesses":[],
    "honest_note":"Enrichment not configured (Understat-only in this deploy).",
    "fetched_at": null
  }
}
```
`shot_profile_detail` is null when `groups` missing for that league/season. `assisted_network` null when `shots.length==0`.

### 1.2 `POST /api/v1/analyze/match/{id}` — additions

```jsonc
{
  // ...existing: narrative, shot_map{h,a}, xg_timeline, big_chance_inventory, situation_breakdown, limitations
  "rosters": { // ← from getMatchData.rosters ; null if absent
    "h": [{"player_name":"Saka","goals":1,"xG":0.60,"shots":3,"key_passes":2,"team_title":"Arsenal"}],
    "a": [...]
  },
  "forecast": {"w":0.42,"d":0.25,"l":0.33,"source":"understat"} // ← from getLeagueData.dates[].forecast matched by id; null if not in dates
}
```

### 1.3 `POST /api/v1/analyze/team` — additions

```jsonc
{
  // ...existing: style, ppda_home_away, form_momentum, situational_xg_share, position_trend,
  //             half_split, home_away_splits, luck_curve, strength_of_schedule, metric_trends, squad
  "archetype": null, // Phase 2; explicit null in Phase 0 so frontend can show "not yet"
  "metric_trends": {
    // existing: dates, xG_for, xG_against, goals_for, goals_against, npxGD, xPTS, PPDA, window
    "deep_for": [...],     // ← rolling 5-match avg of deep_completions/match (from history.deep)
    "deep_against": [...]  // ← rolling of deep_allowed
  }
}
```
`deep_for/against` length === `dates.length`, window `5`, same rolling formula as existing metrics.

### 1.4 `POST /api/v1/matches/rounds` — additions (non-breaking)

```jsonc
{
  "league_name":"EPL","season":2025,"n_played":320,
  "rounds":[{"round":1,"matches":[{"match_id":"11652","id":"11652","date":"2025-08-16","home":"Arsenal","away":"Leeds","home_goals":1,"away_goals":0,"home_xg":1.40,"away_xg":0.90}]}],
  "upcoming_by_round":[{"round":12,"matches":[{"match_id":"…","date":"…","home":"…","away":"…","forecast":{"w":0.42,"d":0.25,"l":0.33},"isResult":false}]}],
  "latest_matches":[...],
  "note":"Round = home team's nth league match (Understat has no official label). Forecast from Understat dates.forecast where available."
}
```
`upcoming_by_round` built from `dates.filter(!isResult)` grouped by same `home nth match` rule.

### 1.5 No scale changes — guarded

Every `y(v)` normalization stays byte-identical:
`allMax=Math.max(...vals,0.001)`, `y(v)=y1-(v/allMax)*(y1-y0)`, `rank invert y=y0+((v-1)/(ymax-1))*(y1-y0)`, `PPDA invert (18-PPDA)/11`, `DC/g = deep/12`. CI tests grep for literals.

---

## 2. Per-Data-Point Consideration (every field, what it means, higher_is_better, where it lands)

### 2.1 `getLeagueData` — `teams[].history[]` (one row per match for that team)

| Field | Type | Meaning | Higher? | Current use | Phase 0 action | Honest caveat |
|---|---|---|---|---|---|---|
| `date` | ISO str | Match date | — | history ordering, position_trend rebuild | Keep as primary sort key; used for `deep_for` roll & luck curve | Date is midnight UTC; no kickoff time |
| `h_a` | "h"/"a" | Venue | — | home/away splits, PPDA home/away | Keep; also split `deep_for` by venue in future | Team page history lacks h_a legend; league-sourced only |
| `wins/draws/loses` | int | Result | wins> | points sum, half_split | Keep; no change | 3/1/0 points assumed |
| `scored/missed` | int | Goals for/against | scored> | goals trending, luck `scored - xG` | Keep | Actual goals, not xG |
| `pts` | int | Points that match (0/1/3) | > | position_trend cumulative | Keep | Assumes 3pts/win |
| `xG/xGA` | float | Expected goals for/against that match | xG> lower xGA | `style.xG_per_game`, rolling `xG_for/against`, `npxGD` | Keep; also draw as situational share | Model-derived, drift over seasons |
| `npxG/npxGA/npxGD` | float | Non-penalty (pen=0.76 xG) | > | `npxGD` trend, lie table `npxGD` | Keep | Penalty xG constant assumption |
| `deep/deep_allowed` | int | Non-cross passes within 20yd of goal for/against | deep> lower allowed | `style.deep_completions`, radar Box Threat | **NEW** `deep_for/against` 5-match roll + axis label | No coordinate map, count only |
| `ppda{att,def}` `ppda_allowed{att,def}` | ints | Passes / defensive actions (att/60% zone) | lower PPDA = intense press | `PPDA/OPPDA` style, `ppda_ratio(att/def)` | Keep; also roll PPDA already; add deep alongside | Game-state dependent |
| `xpts` | float | Expected points from chance distributions | > | `metric_trends.xPTS`, luck-ish | Keep | Simulated, not bookmaker |

### 2.2 `getLeagueData` — `players[]` & `POST getPlayersStats` row (identical shape)

| Field | Meaning | Higher? | Per90? | Where it lands | Phase 0 action |
|---|---|---|---|---|---|
| `id` | Understat player id | — | — | join key for `_merge_league_players`, `search_players` fallback | Keep |
| `player_name` | Display name | — | — | Discover cards, profile hero | Accent-fold `_normalize_name` before match |
| `team_title` | Current team in that season | — | — | group for `creative_dominance`, squad filter | On multi-season merge, latest season's `team_title` wins (documented) |
| `position` | Listed role (FW/MC/DC…) | — | — | `percentiles.position_group`, radar peer filter | Map `FW/ST→F, DMC/DM/AM/MC→M, DC/DL/DR→D` via `group_from_favorite` |
| `games/time` | Appearances / minutes | minutes filter | denominator for all per90 | `minimum_minutes` filter, per90 normalization | Threshold 900 default; keep `util.filter_by_minutes` |
| `goals/npg` | All goals / non-pen goals | > | per90 | KPI, `g_minus_xg`, squad `G−xG` | Keep CI binomial SE `shots*mean_pi*(1-mean_pi)` |
| `xG/npxG/npg` | Model vs non-pen vs count | > | per90 | KPI `npxG/90`, finishing delta | Honest `no post-shot xG` caveat |
| `assists/xA` | Assists / expected assists | > | per90 | `xA/90`, creative dominance share | Show share, not rank, for creativity |
| `shots/key_passes` | Volume / chance creation | > | per90 | `shots/90`, `key_passes/90`, conversion | Keep |
| `xGChain/xGBuildup` | Total involvement / buildup pre-shot | > | per90 | Involvement profile, discover `order_by` | Buildup share = `Buildup/Chain` (pure creator vs finisher) |
| `yellow/red` | Discipline | lower | — | Squad table, discover not ranked | Show, don't rank |
| `npxG/xA per90` | Derived | > | — | Discover `order_by` + cards | Keep ranking by `npxG` default |

### 2.3 `getPlayerData` — `shots[]`

| Field | Meaning | Higher/better? | Phase 0 use | Caveat |
|---|---|---|---|---|
| `X,Y` 0–1 | End location (where shot taken) | — | Pitch map `renderPitchHeatmap`; heatmap Gaussian r `36+xG*26` | End, not release; no pressure annotation |
| `xG` | Chance quality | — | Radius `4+sqrt(xG)*20`, heatmap alpha `0.35+xG`, finishing delta | Model-derived |
| `result` Goal/SavedShot/MissedShots/BlockedShot/ShotOnPost | Outcome | Goal best | Color (amber/blue/red/grey), `big_chance_inventory` threshold 0.20 | Goal mixes finishing/GK error |
| `situation` OpenPlay/FromCorner/SetPiece/DirectFreekick/Penalty | Context | — | Situations stacked bar + `playerShotMixBars`; share calc `_share_rows` | Set-piece share opponent-dependent |
| `shotType` Head/Foot/... | Body part | — | **NEW** Types bar alongside situations | Small samples |
| `lastAction` BallRecovery/Dispossessed/BlockedPass/Rebound/... | Pre-shot regain | — | `pressing_output` regain_xG_share | Press OUTPUT, not activity |
| `minute` 0–90+ | When | — | `shot_minute_buckets` 15' buckets + xG timeline minute axis | Added time collapsed |
| `player_assisted` | Who assisted | — | **NEW** `assisted_network` top assister/assisted | Not Opta key pass; shot-level only |
| `h_team/a_team/h_a/date/season` | Context join | — | Date-window filter, home/away split | Filter by `selectedSeasons` |

### 2.4 `getPlayerData` — `groups` (per-season aggregates)

| Group | Shape | Use before | Phase 0 use | Why it matters |
|---|---|---|---|---|
| `groups.situation[season]` | {situation,shots,goals,xG} | Career table `shot_profile` | **NEW** Player Profile situations bar (shares) | Style fingerprint (penalty-box vs set-piece) |
| `groups.shotZones[season]` | {shotZones,shots,goals,xG} | Same table only | **NEW** Zones bar (OutsideBox/InsideBox/Central) | Selective vs volume shooter |
| `groups.shotTypes[season]` | {shotTypes,shots,goals,xG} | Same table only | **NEW** Types bar (Header/Foot) | Aerial threat flag |
| `groups.position[season]` | {position, games, time} | `role_split` | `role_split` starter/sub minutes | Minutes load context for per90 |
| `groups.season` list `[{season}]` | Seasons present | Fallback discover active season | Keep; also `season_trends` | Handles `Not in league` rows |

### 2.5 `getMatchData` — `shots{h,a}` + `rosters{h,a}` + timeline

| Field | Meaning | Phase 0 use | Note |
|---|---|---|---|
| `shots.h/a[].*` same as player shots | Chance ledger per side | `situation_breakdown` per side, `calibration`, `xg_timeline` | Cumulative path blue(H)/green(A) |
| `rosters.h/a[id: {player, goals,xG,shots}]` | Per-match player ledger | **NEW** `rosters` table in Match Deep-Dive | Already fetched, discarded; now surfaced |
| `forecast` on `dates[]` (not match endpoint, joined) | Understat win/draw/loss prob | **NEW** `forecast` pill `"Understat model: H 42% D 25% A 33% — not our Dixon-Coles"` | Label source honestly; compare vs our probs later |

---

## 3. Task Specs per Developer

### Backend-dev — `phase0-backend` (BE-001)

**What to build:** Additive wiring only; noBreaking.
- `src/app/analytics/enrichment.py` new file: `@dataclass ExternalEnrichment(source="none", ...)` + `class NoopEnrichmentProvider` implementing `enrich_player`/`enrich_team_squad` → `source="none"`. Inject into `AnalyticsService(client,enrichment=None)`. If `None`, JSON omits `enrichment` with `source:"none"` note.
- `analytics_service.py:analyze_player` — after `player_report`, build `shot_profile_detail` via `career_engine.shot_profile_for_season` helpers on `player_data.groups` already fetched; build `assisted_network` by aggregating `shots.player_assisted` (top 5 each way). Attach `enrichment` via provider (noop in Phase 0). Do not change existing `radar/percentiles/similar` math.
- `analytics_service.py:analyze_match` — return `rosters` straight from `get_match_data().rosters`; lookup `forecast` by `match_id` in `get_league_data(league, season)` dates for that match’s league/season (need league hint — infer from `rosters` team names or fallback to first league that contains id; store `forecast` as `{w,d,l,source:"understat"}` or null).
- `analytics/team.py:metric_trends` — add `deep_for` / `deep_against` same 5-window rolling as `xG_for` (using `history.deep` / `deep_allowed`).
- `analytics_service.py:match_rounds` — additionally group `!isResult` rows into `upcoming_by_round` (same `home nth match` grouping) and attach `forecast` per match.id if present.
- Preserve multi-season merge rules: counts sum, `team_title`/`position` latest wins, PPDA latest rate.

**Unit tests to add (must pass before report done):**
- `tests/test_phase0_understat_maxuse.py` (new):
  - `test_shot_profile_detail_zones_types_shares_sum_one` — mock `get_player_data` groups with 2 zones + 2 types → `shot_profile_detail.zones[0].xG_share` sums ≈1.0, forwarded `shotZones` source.
  - `test_assisted_network_top_assister` — shots with `player_assisted="De Bruyne"` ×3 → `assisted_network.top_assisters[0].count==3`.
  - `test_match_rosters_and_forecast` — mock `get_match_data` rosters 2+2 + `get_league_data` dates with `forecast{w:0.42...}` for that id → `rosters.h` length 2, `forecast.w==0.42`.
  - `test_metric_trends_deep_rolling_length` — 6 history rows → `deep_for.length==6`, window 5 avg.
  - `test_enrichment_noop` — `analyze_player(...).enrichment.source=="none"`.
  - `test_match_rounds_upcoming_grouped` — dates with 3 upcoming, 2 played → `upcoming_by_round.length>0`, `rounds` unchanged count.
- Existing `uv run python -m unittest discover -s tests -v` must stay green.

**Serves:** User: "every data point considered" (all 5 max-use fields + whole endpoint field tables above), planned Transfermarkt/SS/WS seam.

### Frontend-dev — `phase0-frontend` (FE-001)

**What to build:** Labels only for scales — zero `y()`/`x()` math change.
- In `src/app/dashboard/app.js` add two `<text>` nodes per trend SVG **without touching normalization constants**:
  - `drawCareerChart` → xTitle `"Season"` at `(x0+x1)/2, h-6`, yTitle `entry.label || metricKey` rotated at `14, (y0+y1)/2`.
  - `drawCareerGoalsVsXg` → `"Season"` / `"Goals / xG"`.
  - `drawCareerInvolvementEvolution` → `"Season"` / `"Per 90"`.
  - `drawSeasonLines` (points) → keep `ymax=max(...points,xpts)` — add yTitle `"Points"`; (rank) keep `y0+((v-1)/(ymax-1))*(y1-y0)` — add `"Rank (1 = top)"`.
  - `drawLuckChart` → `"Match (chronological)"` / `"Cumulative G − xG"`.
  - `drawTrendChart` → `"Match date (5-match rolling avg)"` / `"${label} (5-match avg)"`.
  - `drawLeagueDivergenceChart` → `"Points gap (PTS − xPTS)"` / `"Team (sorted by gap)"`.
  - `drawLeagueTacticalQuadrant` → `"PPDA (lower = higher press, inverted →)"` / `"Deep completions / game"`.
- Player Profile: beside `playerShotMixBars` (situations), render **Zones** and **Types** stacked bars reusing same `colors[]` + `sitItems` logic but sourcing `d.shot_profile_detail.zones/types`. Table + legend.
- Player Profile: **Assisted network** two-column table (Top assisters → you, You assisted → teammates) from `d.assisted_network`.
- Match Deep-Dive: **Rosters** H/A table under xG timeline (goals/xG/shots/key_passes if roster carries them). **Forecast** pill in hero: `Understat model — H 42% D 25% A 33%` only if `d.forecast` present, muted style + tooltip "Not our Dixon-Coles".
- Team Analytics: add `"Deep completions for"` / `"Deep completions against"` to `#trendMetric` select + handle in `drawTrendChart`.

**Unit/visual tests:** Frontend asserts snapshots contain `>Season<`, `>Goals / xG<`, `>Matchday<`, `>Cumulative G − xG<` and that `grep "y1 - (v / allMax)" app.js` unchanged (guard). Manual screenshots at 375px & 1440px show labels not overlapping curves.

**Serves:** User: "trend charts i like these trends as is but axis needs to be added here do not change the axis but name it." + richer visuals for every data point.

---

## 4. Integration into Existing Scouting (not a new tab)

Discover & Scout *is* scouting. Phase 0 does **not** create a new tab. Zones/Types bars and assisted network appear *inside* Player Profile which Discover cards already link to (`Analyze Profile →`). This keeps the scout loop `Filter → Rank → ★ → Profile → Compare → Shortlist` in one evolution. Watchlist/age scatter are Phase 1, not Phase 0 — to stay bulletproof we ship Phase 0's max-use first and re-verify.

---

## 5. QA & Adversary gates (Phase 0 exit criteria)

- `uv run python -m unittest discover -s tests -v` green + new `test_phase0_*` 6/6.
- Screenshots: Player, Team, League, Career (Zones/Types visible), Match (Rosters+Forecast visible) at mobile/desktop — no overlap.
- Axis labels present, scales identical (adversary hostile pass: narrow viewport overlap, forecast mislabel, empty `groups` fallback).
- Only `docs/*.md` written by lead; devs own code per task specs.

