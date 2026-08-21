# Phase 3 Plan — Live Gameweek Board

**Branch:** `feat/next-work` · **Depends on:** Phase 0 `upcoming_by_round` (shipped in `ad68d82`)
**Goal:** A kickoff-aware gameweek board on the Match tab — every round 1..N browsable, upcoming fixtures showing Understat's model forecast, played fixtures one click from Deep Dive. Honest: Understat has no kickoff times or in-play data; "live" means *season-state aware*, not in-play polling.

---

## 1. API Contract (additive)

### 1.1 New `POST /api/v1/matches/live`  `{league_name, season}`

```jsonc
{
  "league_name": "EPL",
  "season": 2025,
  "season_status": "complete",          // "pre-season" (0 played) | "in-progress" | "complete" (no upcoming)
  "round_current": 12,                  // smallest round containing any unplayed fixture; latest played round when season complete
  "n_played": 320,
  "n_upcoming": 60,
  "rounds": [
    {
      "round": 1,
      "complete": true,                 // all matches played
      "matches": [{
        "match_id": "11652", "id": "11652", "date": "2025-08-16",
        "home": "Arsenal", "away": "Leeds",
        "isResult": true, "home_goals": 1, "away_goals": 0, "home_xg": 1.4, "away_xg": 0.9
        // , "forecast": {"w":0.42,"d":0.25,"l":0.33}   // only on unplayed fixtures where Understat provides it
      }]
    }
  ],
  "note": "Live = season-state board. Understat updates post-match; no kickoff times or in-play xG exist in this source. Round = home team's nth league match (postponements can shift). Forecast = Understat model, not our Dixon-Coles."
}
```

Implementation reuses `match_rounds` internals (one `get_league_data` fetch): merge played `rounds` + `upcoming_by_round` into a single sorted list with per-fixture `isResult`; derive `season_status` and `round_current`.

## 2. Frontend — Match view toggle (FE-004)

- Segmented pills above fixture feed: **Recent Results** (default, current behavior untouched) | **Gameweek Board**.
- Board mode: fetch `/api/v1/matches/live`, cache in `state.liveData` keyed by league+season. Render:
  - Round pill strip (1..N): complete rounds filled accent, `round_current` ring-highlighted, future rounds muted.
  - Selected round → fixture cards grid:
    - Played → existing `.fixture-card` style (FT score + xG badge) → click = Deep Dive.
    - Upcoming → date card with muted forecast pill `H 42% D 25% A 33% · Understat model`, not clickable, tooltip "Not yet played — forecasts in Predict & Sim".
- Season/league switch resets cache like `loadRounds`.

## 3. Tasks
- BE-004: `AnalyticsService.match_live(league_name, season)` + route `POST /api/v1/matches/live`. Tests `tests/test_phase3_live.py`: `test_matches_live_shape_mixed_rounds`, `test_matches_live_pre_season`, `test_matches_live_complete_season`.
- FE-004: toggle + board rendering as above; verify via playwright at 1440+375 (`p3-board-*.png`), Recent Results unchanged.
