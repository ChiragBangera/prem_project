# Phase 5 — Tactical Intelligence: Detailed Build Plan

**Branch:** `feat/next-work` · **Baseline:** `7d19015` (174 tests, 8 palettes via `[data-theme][data-mode]` in `src/app/dashboard/styles.css:1`, thin-ready header at `index.html:80`, `app.js:602` pitch)
**Mode:** `build` — this file is the frozen contract. All agents start from here. No code ships without screenshot + `grep` + mock tests.

> **User directive:** dark-first near-black charcoal, information-dense, restrained. One football-green, used sparingly. Numbers as measurement. Pitch as signature. 3-layer hierarchy. Thin vertical nav. Charts answer questions. Free-tier APIs (Sofascore via TacosScore, api-football.com, football-data.org) planned wide/deep to the smallest detail, no slop, multi-agent. Every metric checked off. Plan >9 pages is fine — detail over brevity.

---

## 0. Current Audit — Why "Old Grandpa Website" Is Accurate

`index.html:22` sidebar is 240px wide, 8 flat siblings, all equal weight. `styles.css:502` `.kpi-card` renders 6 equal cards (`minmax(135px,1fr)`) with no delta, no benchmark, no percentile. `app.js:602` `drawPitchLines` draws FIFA grass stripes. `index.html:296` `controls-row` has 9 fields + button in one row at `gap:14px` — at 375 scrollWidth previously 409–423 (fixed to 375 but still visually crowded). `styles.css:1` Midnight Slate (`#07090e/#0c1017`) is *close* to the target `Canvas #0B0D0F` but lacks the semantic green-only rule — every chart today is colored. `app.js` hardcodes `#38bdf8` at draw time, ignoring CSS vars, so Nord/Gruvbox themes re-tint chrome but not charts.

Inspiration gap per image:

| Image | What it does brilliantly | What we lack today |
|---|---|---|
| **1 ELITE PERFORMANCE** | 4 KPI sparklines (Distance 11.2km, Sprint 34.5, Pass 88% 321/365, SOT 7 7/12) → tactical diagram with pressing/movement zones + heat map + donut Possession 61% + bar Shots/Goals vs last 5 + fitness radar 80%/79%/30% | Sprint/physical, donut possession, tactical diagram with zones, fitness radar, bar vs last 5 |
| **2 MyGamePlan Pressure** | Pressure 1.6 gauge + `Matches (5/35)` filter pills + table TOTAL/LEFT/CENTER/RIGHT/AVG TIME + stacked bars per match + pitch scatter ● Pressure/● Shot-Ending/● Goal-Ending + Scattering vs Heat Map toggle + `Statistics Per 90'` switch | Zone-split pressure table, time-block pills, per-match stacked pressures, dual-mode pitch, per-90 toggle |
| **3 xG Shot Quality (UTA)** | Expected 51% vs Actual 57.9% left rail (4 tiers Poor 51%/Average 30%/Good 13%/Great 6%) + top filters Team/xG Category/Result/Buildup/Possession + date slider 3/16/2024—8/29/2024 + pitch dots colored by tier (Poor red, Average orange, Good yellow, Great green 190 shots 15.04 xG 0.08/shot) | Tier-colored shot map, Expected vs Actual bar, top filter row with slider, Include Penalties / Shots For toggles |
| **4 Real Madrid–Levante** | Cross-match header (Real 1:0 4-3-3 vs Levante 4-4-2, crossing 20 vs 22, passing 77% vs 89%, possession 47%/53%, time 45:59+4) + dotted pitch with player chips (ASIO 11 etc.) + line-up/position panels + commentary timeline + fouls/offsides bars | Cross-match header, live minute + split possession bar, formation-aware dotted pitch, lineup panels, timeline |

---

## 1. Visual Philosophy — Tokens

Replace `styles.css:1` `:root` base with the Tactical Intelligence system. Keep the 8-way picker (Midnight/Nord/Gruvbox/Studio × light/dark) as **accent variants** on one base.

**Base (dark, default — rebase of Midnight):**

```
Canvas      #0B0D0F
Surface     #111417
Surface2    #171B1F
Border      #24292E
Border-L    #2E343B
Border-H    #3A414A
Text        #F3F5F7
Muted       #8B939D
Muted-Dim   #6B7280
Accent      #1ed760  (football green, Midnight)
Accent-H    #2ef071
Accent-Dim  rgba(30,215,96,0.12)
Accent-Glow 0 0 18px rgba(30,215,96,0.22)
Positive    #1ed760
Neutral     #38bdf8
Warning     #f59e0b
Negative    #f43f5e
Pitch-Bg    #0B0D0F
Pitch-S1    #111417
Pitch-S2    #171B1F
Shadow-Sm   0 1px 3px rgba(0,0,0,0.5)
Shadow-Card 0 4px 16px rgba(0,0,0,0.6)
```

**Theme accents (only `Accent` family changes; canvas/surface stay):**

* **Midnight** — `#1ed760` (green) / `#38bdf8` neutral
* **Nord** — `#88c0d0` (frost) / `#a3be8c` emerald — `Canvas #2E3440` in nord-dark retains Polar Night, nord-light uses `#ECEFF4`
* **Gruvbox** — `#fabd2f` (yellow) / `#b8bb26` — dark `#282828`, light `#fbf1c7`
* **Studio** — `#fafafa` (dark) / `#18181b` (light) — mono, no hue accent, glow `0 0 0 transparent`

Light variants invert Canvas/Surface/Border/Text per existing `styles.css:1` light rules (already shipped in `7d19015`), but now re-tokenized to the `#0B0D0F` base — not `#07090e`. `html { transition: background-color 0.25s, color 0.25s }` at `styles.css:1467` kept.

Chart colors **never** hardcode `#38bdf8` at `app.js:602` again — they read `getThemeColor('--accent')` / `--neutral` / `--warning` / `--negative` at draw time. Rule: *everything neutral until > benchmark = green, < = red*.

---

## 2. Typography

`styles.css:62` today is system sans. Switch to:

* **UI / headings** — `Geist` (Vercel) or `Inter` — 800/700, tracking `-0.04em` for `Arsenal` 24px at `styles.css:466`
* **Numbers / technical** — `IBM Plex Mono` or `Geist Mono` — `tabular-nums` already at `styles.css:82`

Result:

```
Arsenal
2.14 xG   // 32px/900 mono — measurement

vs

Arsenal
2.14 xG   // sans — marketing
```

Delta `+0.31` set in 11px muted mono beside it, not below.

### 3. Three-Layer Hierarchy — Exhaustive Metric → Visual Map

#### Layer 1 — Decision metrics (biggest type, `styles.css:502` `.metric` + `.metric-delta`)

| Metric | Source | Formula | Visual — biggest treatment | Primitive |
|---|---|---|---|---|
| **xG /90** | Understat `xG/time` (`analytics/player.py:35` `per90`) + Sofascore `expectedGoals` (`event/{id}/statistics` key `expectedGoals`) | `xG*90/min` | `2.14` 32px mono + `+0.31 vs avg` 11px + `89th %` bar | Metric + Delta + Percentile + Benchmark |
| **xGA /90** | Understat `xGA` / Sofascore `expectedGoals` (opposition) | same | Same card, red when `> benchmark` | Metric |
| **xGD /90** | `xG - xGA` per 90 | `+0.82` | `+0.82` hero + `↑ 0.14 vs last season` sparkline | Metric + Trend + Benchmark |
| **PPDA** | Understat `ppda{att,def}` (`stat_data/understat.py:238`) / Sofascore `ballRecovery` context | `att/def` | `8.7` + `↓ 0.4 vs last 10` sparkline | Metric + Trend + Confidence (`n=38`) |
| **Possession %** | Sofascore `ballPossession` + API-Football `fixtures/statistics` Ball Possession | `homeValue` | Donut `61%` center + bar `Aether 61% / Zenith 39%` (Image 1) | Metric + Distribution |
| **Field tilt** | Sofascore `finalThirdEntries` / `touchesInOppBox` | `finalThirdEntries / total` | Single tilt bar, `>60% = green` | Metric + Benchmark |
| **Progressive actions /90** | Sofascore `progressiveBallCarriesCount`, `totalProgression`, `accurateThroughBall` | per90 | `7.8` + `carries 5.4 / passes 2.4` | Metric + Rank |
| **Shot quality** | Understat `xG/shot` (`player.py:110`) + Sofascore `expectedGoalsOnTarget` | `xG / shots` | `0.08` + tier bar Poor→Great | Metric + Distribution |

Layer 1 lives in hero strip `index.html:90` `view-*`. Today `kpi-row` at `styles.css:504` renders 6 equal cards. Phase 5 makes it 4 max/row with `+Δ vs avg` and `percentile` subline.

#### Layer 2 — Explanatory (charts answering *why*)

Each title is a **question**, not a noun:

| Question | Data | Visual primitive | Component |
|---|---|---|---|
| *Are we creating better chances?* | `xG/match` rolling 5 (`team.py:376` `metric_trends`) | Area chart `Aug Sep Oct Nov` vs `Last 5` sparkline | Line + Area + Trend |
| *Where are shots from?* | Understat `shots X,Y,xG` + Sofascore `totalShotsInsideBox/OutsideBox`, tier `xG/SHOT` | Minimal pitch with dots colored Poor #f87171 / Average #fb923c / Good #facc15 / Great #a3be8c + Expected vs Actual rail `51% vs 57.9%` (Image 3) | Shot map + Pitch + Distribution |
| *Are we controlling territory?* | `finalThirdEntries`, `touchesInOppBox`, Understat `deep` | Territory bar + half-pitch zone heatmap | Heatmap + Zone |
| *How do we progress?* | `accurateLongBalls`, `accurateCross`, `keyPass`, `totalBallCarriesDistance`, `totalProgression` | Passing network on minimal pitch (nodes = avg positions from `lineups` `player{position}`, edges = `passEndCoordinates`) | Passing network + Scatter |
| *Who carries us forward?* | `progressiveBallCarriesCount`, `bestBallCarryProgression`, `wonContest` | Bar per player + arc | Bar + Rank |
| *Are we pressing effectively?* | Sofascore Pressure `TOTAL/LEFT/CENTER/RIGHT/AVG TIME` (Image 2) + `ballRecovery/interceptionWon/totalTackle` + `pressure map` | Table + stacked bars per match + pitch scatter `● Pressure / ● Shot-Ending / ● Goal-Ending` | Pressure map + Distribution |
| *Are we sustaining possession?* | `possessionLostCtrl`, `accurateOppositionHalfPasses`, `finalThirdPhaseStatistic` | Possession chains histogram + `Possession: 61%` donut | Donut + Possession chain |
| *Where are chances created?* | `keyPass`, `bigChanceCreated/Missed`, `accurateThroughBall` | Flow vs last 5 bar (Image 1) | Bar + Line |
| *Are we defending?* | `totalClearance/outfielderBlock/errorLeadToAShot`, `wonTacklePercent`, `saves/goodHighClaim/goalsPrevented` | Defensive actions by zone + `goalsPrevented` gauge | Heatmap + Metric |

Layer 2 sits under collapsible `Team → Performance → Possession → Chance Creation → Defence` tabs inside `view-team`, not as top-level nav.

#### Layer 3 — Raw (collapsed by default)

Tables, filters, individual events, `totalPass/accuratePass/touches/minutesPlayed/rating` — `styles.css:771` `table` with `overflow-x:auto` drawer. Filters stay `index.html:296` `controls-row` (Phase 4 added `row-gap` + top border) — now visually grouped with `FROM/TO` range styling, not Excel.

### 4. Navigation — Thin Vertical Command Sidebar

Replace `index.html:22` 8-item list:

```
◉ HOME          → /
▣ MATCHES       → #match (Recent / Gameweek Board at app.js:777 + live at 40f8a4c)
◈ TEAMS         → #team (Overview / Performance / Possession / Chance / Defence)
◎ PLAYERS       → #player (Profile / Scouting — #discover merged)
⌁ TACTICS       → #team?tab=pressing (SHOTS / POSSESSION / PRESSING as children)
▤ MODELS        → #predict (Dixon-Coles/Elo at app.js:3143 — fixed in 9916917)
⚙ DATA         → #info (glossary + source badges)
```

`aside.sidebar` at `styles.css:106` `width:240px` → `64px` icon-only with tooltip on hover, expands to `240px` on hover/focus. Respects `prefers-reduced-motion`. Keeps density, restores `sidebar-footer` theme picker on mobile (currently hidden at `max-width:900px`).

### 5. Pitch — First-Class Primitive

Replace `app.js:602` FIFA-green stripes with `Pitch` component spec:

```js
<Pitch width=800 height=520 mode="shot|pass|carry|pressure|formation"
       shots={X,Y,xG,tier} passes={playerCoordinates,passEndCoordinates}
       heatmap={boolean} network={boolean} zones={Zone[]} players={PlayerPos[]} />
```

Thin `1px #24292E` lines, no grass, dot `● 6px`, heat `alpha 0.35+xG*26` (existing at `app.js:712` kept, remapped to theme). Both Sofascore grids (§1.3) normalized to internal `100×100 pitch_x/y` at ingest — never project in render. Reused for shot tier map, pressure scatter, build-up, passing network, formation dots (`lineups: 4-2-3-1` chip), heatmaps, zones.

### 6. Sofascore Catalog → Implementation Checklist

**Team statistics** (`GET /api/v1/event/{id}/statistics`, 3 periods):

*Match overview* — `ballPossession, expectedGoals, bigChanceCreated, goalkeeperSaves, cornerKicks, fouls, passes, totalTackle, freeKicks, yellowCards, redCards`
*Shots* — `totalShotsOnGoal, shotsOnGoal, hitWoodwork, shotsOffGoal, blockedScoringAttempt, totalShotsInsideBox/OutsideBox`
*Attack* — `bigChanceScored, accurateThroughBall, touchesInOppBox, fouledFinalThird, offsides`
*Passes* — `accuratePasses, throwIns, finalThirdEntries, finalThirdPhaseStatistic (ratio), accurateLongBalls, accurateCross`
*Duels* — `duelWonPercent, dispossessed, groundDuelsPercentage, aerialDuelsPercentage, dribblesPercentage`
*Defending* — `wonTacklePercent, totalTackle, interceptionWon, ballRecovery, totalClearance, errorsLeadToShot/Goal`
*Goalkeeping* — `goalkeeperSaves, goalsPrevented (xG prevented, proprietary), diveSaves, highClaims, punches, goalKicks`

**Lineups** (`GET /api/v1/event/{id}/lineups`):

`confirmed, formation (4-2-3-1), missingPlayers, player{id,name,position,height,dateOfBirthTimestamp,proposedMarketValueRaw,country}, shirtNumber/substitute/captain, statistics{ totalPass/accuratePass/totalLongBalls/accurateLongBalls/totalCross/accurateCross/keyPass/goalAssists/expectedAssists, totalShots/shotOffTarget/onTargetScoringAttempt/blockedScoringAttempt/goals/bigChanceCreated/bigChanceMissed/expectedGoals/expectedGoalsOnTarget, totalContest/wonContest/dispossessed/unsuccessfulTouch, duelWon/duelLost/aerialWon/aerialLost/challengeLost, totalTackle/wonTackle/totalClearance/outfielderBlock/interceptionWon/ballRecovery/errorLead*, fouls/wasFouled/totalOffside, saves/goodHighClaim/goalsPrevented, topSpeed/kilometersCovered/numberOfSprints/totalBallCarriesDistance/ballCarriesCount/totalProgression/progressiveBallCarriesCount, touches/minutesPlayed/possessionLostCtrl, rating/ratingVersions }` — all ✅KEEP per reference; `name/homeValue/renderType/compareCode` are ❌DROP.

**Rating breakdown** (`GET /api/v1/event/{id}/player/{pid}/rating-breakdown`): four buckets `passes, dribbles, defensive{ball-recovery,tackle}, ball-carries` with `playerCoordinates, passEndCoordinates, isHome, outcome(missing=false), keypass`.

**Shotmap** (`.../shotmap`): System B `playerCoordinates, goalMouthCoordinates{ x:0, y, z height }, outcome, situation, shotType` — tier-colored map + Expected vs Actual rail.

**Heatmap** (`.../heatmap`): System A 0–100 grid, decimal `73.5,94.6`.

**Standings/fixtures** for federation fallback.

### 7. Free-Tier Federation — No Surprises at the Limit

| Provider | Free limit | Endpoints we use | Cache | Env gate |
|---|---|---|---|---|
| **Sofascore** | undocumented, bot-monitored | `event/{id}/statistics, lineups, player/{pid}/rating-breakdown, shotmap, heatmap` | `cache/sofa.db` TTL 6h (event) | `SOFASCORE_ENABLED` |
| **api-football.com/v3** | 100/day | `fixtures?league=39&season=2025`, `standings`, `teams`, `players?team=`, `fixtures/statistics`, `predictions` | `cache/api-football.db` standings 24h, fixtures 6h, nightly prefetch top-5 | `API_FOOTBALL_KEY` |
| **football-data.org/v4** | 10/min | `/areas`, `/competitions/{id}/standings`, `/competitions/{id}/matches?dateFrom=&dateTo=`, `/teams/{id}` | `cache/api.db` (already TacosScore) | `FOOTBALL_DATA_TOKEN` |
| **Understat** | site — best effort | `getLeagueData, getTeamData, getPlayerData, getMatchData, getPlayersStats, heatmap` | `cache/understat.db` (future) | always |
| **Transfermarkt** | manual CSV only | `data/transfermarkt/manual.csv` | `cache/enrichment.db` (Phase 4) | — |

All providers implement `FootballProvider` protocol as in `enrichment.py:23`. Factory returns Noop when env absent — never crashes. Sofascore 1 req/s + jitter + 429 backoff; api-football reads `x-ratelimit-requests-remaining`; football-data token bucket.

### 8. File Map — Smallest Details Checked Off

* `styles.css:1` — rebase tokens to `#0B0D0F` system + 7 theme siblings; add `.metric/.metric-delta/.benchmark`, `html transition`, re-tokenize `.player-hero-card` gradient (was `#131c2c` → `var(--panel)` for light).
* `index.html:11` — add Geist + IBM Plex Mono links; `index.html:22` — 64px rail + tooltip; `index.html:80` — header `MATCHLAB — EPL 25/26 — ⚙ ⌘K`; `index.html:90` — nested team sub-tabs.
* `app.js:602` — `drawPitchMinimal` + `getThemeColor('--accent')` so charts re-tint; `command-palette.js` (new) indexing `planner.py`.
* Image 1: `xG/90 + +0.31 vs avg` delta + `LAST 10` sparkline + donut + tactical diagram zones + bar vs last 5 + fitness radar.
* Image 2: table TOTAL/LEFT/CENTER/RIGHT/AVG TIME + stacked bars per match + pitch scatter legend.
* Image 3: left rail `Expected | Actual` 51% vs 57.9% ×4 tiers + top filters Team/xG Category/Result/Buildup/Possession + slider `3/16/2024—8/29/2024`.
* Image 4: cross-match header + dotted pitch with `ASIO 11` chips + lineup panels + commentary timeline.
* `api.py:100` lifespan — add Sofascore + federated clients behind env gates; new `GET /api/v1/sofascore/event/{id}/lineups` mocked from sample `15186861` before live.
* `docs/PHASE5_PLAN.md:*` — metric matrix Understat × Sofascore × API-Football × football-data.org.

### 9. Dispatch — Multi-Agent, Parallel Where Safe

* **backend-dev + frontend-dev parallel** (contract frozen on this file): backend lands Sofascore client + federated cache + `tactical.py` retention; frontend lands tokens + rail + pitch + metric primitives.
* **qa** captures 4 inspirations at `1440` + `375` against live data; runs `uv run python -m unittest discover -s tests -v` (174 → ~195 with 3 mock + live tests).
* **adversary** hostile pass over filter explosion (`Matches Considered 5/35`), stale cache, missing `team_hint` disambiguation, light-mode contrast.

No file claims `done` via `echo`. Every visual is screenshot-verified, every scale `y1 - (v / allMax)` grepped, every provider mocked before merging.
