# Phase 2 Plan — Tactical Archetypes (Fingerprint → Label)

**Branch:** `feat/next-work` · **Depends on:** Phase 0 (`ad68d82`), Phase 1 (`74e8b32`), frontend fixes (`9916917`)
**Goal:** Answer "what kind of team is Brighton?" in one glance. Turn the existing 6-pillar tactical DNA radar into a **labeled archetype** with peers — deterministic, honest, zero new Understat fetches (every feature already exists in `style_profile`).

---

## 1. API Contract (additive)

### 1.1 `POST /api/v1/analyze/team` — `archetype` becomes real (was explicit `null` stub since Phase 0)

```jsonc
{
  // ...existing style, metric_trends.deep_for/against, squad...
  "archetype": {
    "label": "Control & Territory",
    "description": "Dominant territory and box penetration with defensive control.",
    "confidence": 0.75,                    // fraction of rule conditions strongly satisfied, 0..1
    "features": {                           // z vs league mean/std for THIS season's table
      "xg_per_game":  {"value": 1.94, "z": +1.62},
      "xga_per_game": {"value": 0.87, "z": -0.71},
      "npxgd":        {"value": 24.3, "z": +1.55},
      "ppda":         {"value": 9.6,  "z": -0.44},
      "oppda":        {"value": 13.9, "z": -0.20},
      "dc_per_game":  {"value": 11.2, "z": +1.38}
    },
    "peers": [                              // same-label teams, nearest first (euclidean in z-space)
      {"team": "Man City", "label": "Control & Territory", "distance": 0.42},
      {"team": "Liverpool", "label": "Control & Territory", "distance": 0.97}
    ],
    "honest_note": "Rule-based heuristic on this season's league-table z-scores — not a learned cluster. Set-piece reliance is not detectable from table metrics alone."
  }
}
```

### 1.2 `POST /api/v1/analyze/league` — additions

```jsonc
{
  // ...existing table, is_lying, variance, pace...
  "archetypes": {
    "by_team": {"Arsenal": "Control & Territory", "Brighton": "Expansive / Chaos", "...": "..."},
    "counts": {"Control & Territory": 3, "Balanced Mid": 9, "...": 0},
    "honest_note": "Same as above."
  }
}
```

Backward compat: keys additive; `archetype:null` never returns again for valid teams (frontend must still null-guard).

---

## 2. Per-Data-Point Consideration (features → rules)

All features come from the **same season's league table row** (`style_profile`) — no new fetches, no shots needed:

| Feature | Source col | Meaning | z direction | Used by rules |
|---|---|---|---|---|
| `xg_per_game` | xG/M | Attack volume | high good | Chaos (+), Direct (≥ −0.3) |
| `xga_per_game` | xGA/M | Defensive concession | low good | Chaos (+0.8), Control (≤ −0.3), LowBlock (≤ −0.3) |
| `npxgd` | NPxGD | Non-penalty process | high good | HighPress (≥ +0.2) |
| `ppda` | PPDA | Passes allowed per defensive action — **lower = intense press** | low = press | Control (≤ +0.5), HighPress (≤ −0.7), LowBlock (≥ +0.5), Direct (≥ 0) |
| `oppda` | OPPDA | Opponent pressing vs us — higher = we resist press | context only | reported, not ruled (v1 honesty) |
| `dc_per_game` | DC/M | Deep completions — box penetration | high good | Control (≥ +0.7), Direct (≤ −0.5) |

**Rules (ordered, first match wins):**

1. **Expansive / Chaos** — `xg_z ≥ +0.8 AND xga_z ≥ +0.8` (trades at both ends).
2. **Control & Territory** — `dc_z ≥ +0.7 AND xga_z ≤ −0.3 AND ppda_z ≤ +0.5`.
3. **High Press & Transition** — `ppda_z ≤ −0.7 AND npxgd_z ≥ +0.2`.
4. **Low Block & Counter** — `ppda_z ≥ +0.5 AND xga_z ≤ −0.3`.
5. **Direct & Vertical** — `dc_z ≤ −0.5 AND ppda_z ≥ 0 AND xg_z ≥ −0.3` (little deep buildup, still productive).
6. **Balanced Mid** — fallback.

**Confidence:** matched-rule conditions satisfied beyond threshold by ≥0.3 z-margin, divided by condition count (0..1). Honest: not a probability.

**Explicitly NOT claimable from table metrics (surfaced in honest_note):** set-piece reliance (needs situation split), build-up shape (needs event data), transition speed (needs possession chains). This is where SofaScore/WhoScored enrichment would later upgrade labels — seam already exists.

---

## 3. Task Specs

### Backend-dev — BE-003
- New pure module `src/app/analytics/tactical.py`: `league_feature_stats(table_rows) -> {feature: {mean,std}}`, `team_z(style, stats) -> dict`, `classify(z) -> {label, description, confidence}`, `archetype_report(style_row, table_rows) -> full payload incl. peers`. No I/O.
- Wire: `AnalyticsService.analyze_team` — after `report = team_engine.team_report(...)`, compute `report["archetype"] = tactical.archetype_report(team_row, full_table_rows)` (needs the FULL league table rows it already fetches — keep first table, not merged multi-season; if multiple seasons, use latest season's table and say so in note). Remove `"archetype": None` stub from `team_report` if present there.
- Wire: `AnalyticsService.analyze_league` — compute `report["archetypes"] = {"by_team","counts","honest_note"}` from same table.
- Guard: teams with M=0 (empty season) → z=0, classify Balanced Mid, note "insufficient matches".
- Tests `tests/test_phase2_archetypes.py`:
  - `test_control_team_classified` — synthetic 20-row table, one City-like row → Control & Territory.
  - `test_chaos_team_classified` — high xg+xga row → Expansive / Chaos.
  - `test_low_block_classified` — high ppda, low xga → Low Block & Counter.
  - `test_balanced_fallback` — average row → Balanced Mid.
  - `test_peers_sorted_by_distance` — peers ascending distance, same label.
  - `test_confidence_bounds` — 0..1 inclusive.
  - `test_analyze_team_includes_archetype` + `test_analyze_league_includes_map` (mocked client, like phase0 tests).
- Existing 155 stay green.

### Frontend-dev — FE-003
- Team hero: archetype badge pill after league pill — `🧬 Control & Territory · 75%` with `title=description + honest_note`; null-guard stays.
- Team "Team Tactical DNA" card header: append small archetype chip; under radar add "Archetype peers" chips (top 3, click → loads that team via runTeam pattern).
- League view: new compact card after the table — "Tactical Archetypes" with counts per label and team chips grouped by label (chip click → team tab). Reuse `.view-pill-btn` styling.
- Glossary: no change required (labels self-describing); keep tooltips honest.
- Verify with live app: Arsenal/EPL 2025 renders badge + peers; league shows counts. Screenshots `p2-team-badge.png`, `p2-league-archetypes.png`.

---

## 4. QA gates
- 155 + ~8 new tests green; live recheck Arsenal + league; adversary pass over rule edge cases (M=0, single-team league, all-identical rows std=0 → z=0 guard).
