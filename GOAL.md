# 🎯 Core Football Analytics Hub — Project Goal & Roadmap

## 1. Vision & Core Objective
Transform this repository into the **definitive, personal football analytics platform** for day-to-day scouting, team performance diagnosis, match preparation/forecasting, historical trend analysis, and natural-language football intelligence.

---

## 2. Current Foundation & Architecture

```
                       ┌──────────────────────────────────────────────┐
                       │           Frontend & Consumers               │
                       │  • Interactive Dashboard (/dashboard)        │
                       │  • REST API (/api/v1/*, FastAPI)             │
                       │  • CLI & Shell (`prem-analytics`)            │
                       └──────────────────────┬───────────────────────┘
                                              │
                       ┌──────────────────────▼───────────────────────┐
                       │       Application Orchestration Layer         │
                       │  • AnalyticsService (player/team/league/match)│
                       │  • PredictionService (match/season/calibrate)│
                       │  • FootballQuestionAnswerer (NLP Engine)     │
                       └───────┬──────────────┬───────────────┬───────┘
                               │              │               │
        ┌──────────────────────▼──┐ ┌─────────▼────────┐ ┌────▼─────────────────┐
        │     Analytics Engines   │ │     ML Engine    │ │  Question Answering  │
        │ • Radar & Percentiles   │ │ • Dixon-Coles    │ │ • Planner (Entities) │
        │ • Similar Players       │ │ • Elo Ratings    │ │ • Fetcher (Data)     │
        │ • xPTS & Lying Tables   │ │ • Pi Ratings     │ │ • Answer Builders    │
        │ • Form & Trajectories   │ │ • XGBoost Hybrid │ │   (Tables/Teams/etc) │
        └──────────────────────┬──┘ └─────────┬────────┘ └────┬─────────────────┘
                               │              │               │
                       ┌───────▼──────────────▼───────────────▼───────┐
                       │              Data Providers                  │
                       │  • UnderstatData (Async scraper / client)    │
                       │  • Wikidata SPARQL (Ages & Player Bio Data)  │
                       └──────────────────────────────────────────────┘
```

---

## 3. Current Feature Inventory

1. **Player Analytics & Scouting**:
   - Radar charts (pizza profiles) categorized by position family (FW, M, D, GK).
   - Percentile pool rankings against league peers.
   - Finishing efficiency (Goals vs xG, shot distribution by zone/situation).
   - Player discovery with multi-season, position, age, and metric filtering.
   - Similar player clustering using normalized metric distance.
   - Career trajectories across multi-season spans.
   - Multi-player comparison (up to 12 players) with overlaid radars and shot profiles.

2. **Team & League Analytics**:
   - Expected Points (xPTS) and "lying table" luck/variance diagnosis.
   - Pressing intensity metrics (PPDA / OPPDA) and deep completions (DC / ODC).
   - Season-over-season matchweek progression and rank trajectories.
   - Form and momentum rolling windows.
   - Head-to-head comparison and style profiling.

3. **Match & Tactical Intelligence**:
   - Single match deep dive: cumulative xG timeline, shot maps, big chance inventory.

4. **Predictive & Machine Learning Modeling**:
   - **Dixon-Coles Bivariate Poisson**: scoreline probabilities with low-score dependency ($\rho$) and time decay.
   - **Elo & $\pi$-Ratings**: dynamically adjusted team strength ratings.
   - **XGBoost Hybrids**: goals-poisson, xG regression, and multiclass W/D/L boosters.
   - Rest-of-season Monte Carlo simulations.
   - Walk-forward backtesting and calibration scoring (Brier score, RPS, log-loss).

5. **Natural Language Analytics Engine**:
   - Asks questions like *"Compare Arsenal vs Liverpool in 2025"*, *"Who is the best finisher in EPL 2025"*, or *"How did Man United perform under Amorim"*.
   - Structured plan, evidence retrieval, and analytical copy generation.

---

## 4. Observations & Things Highlighted for Future Phases

| Area | Current State | Potential Future Enhancement |
| --- | --- | --- |
| **Data Caching & Persistence** | Live async HTTP calls on every request with small in-memory dicts. | Persistent local cache (SQLite / DuckDB / Parquet) for historic seasons to make analysis instantaneous and offline-capable. |
| **Data Coverage & Ingestion** | Top 5 European Leagues (Understat). | Expand data ingestion pipelines (FBref, Transfermarkt for market values/contracts, FotMob, custom event feeds). |
| **Visualizations & Reports** | Canvas/SVG client-side custom rendered charts. | Pitch heatmaps, pass network maps, shot cluster density plots, exportable PNG/PDF scouting reports. |
| **Live Match Tracking** | Post-match analysis. | Live game dashboard / gameweek live tracker with real-time xG momentum. |
| **Tactical Profiling** | PPDA, deep completions, build-up xG. | Cluster-based tactical archetypes (e.g. direct counter-attacking vs possession vs high-press). |
| **Coaching Timelines** | Curated dictionary in `coach_eras.py`. | Automated manager stint lookup or dynamic manager tracking. |

---

## 5. Ongoing Log & Progress
- **2026-08-20**: Comprehensive codebase deep-dive completed. All 137 test suites passing. Project goal formalized.
