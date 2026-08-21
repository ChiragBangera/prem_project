# Phase 1 Plan — Scouting v2 (Efficient Scout Loop Inside Discover)

**Branch:** `feat/next-work` · **Depends on:** `docs/SCOUTING_RESEARCH_PLAN.md` + `docs/PHASE0_PLAN.md` (`ad68d82`)
**Goal:** Make scouting *efficient* (≤3 clicks to a defensible shortlist) by staying Understat-native, honoring every data point, evolving the existing **Discover & Scout** tab — not a new tab, no slop.

---

## 1. API Contract (additive, backward compat)

### 1.1 `POST /api/v1/discover/players` — additive query params + response fields

**Query (all optional, existing calls unchanged):**

```jsonc
{
  "league_name": "EPL", "season": 2025, "seasons": [2024,2025], // existing multi-season merge
  "position_group": "F", "positions": ["FW","FWR"], // existing
  "minimum_minutes": 900, "order_by": "npxG", "limit": 20, // existing
  "start_date": null, "end_date": null, "min_age": null, "max_age": null, // existing

  // Phase 1 additions:
  "per90_sort": false,              // false: rank by totals (default, backward compat). true: rank by per90 of order_by.
  "min_npxG_per90": null,           // float threshold, e.g., 0.35
  "min_xA_per90": null,             // e.g., 0.15
  "min_xGChain_per90": null,
  "min_xGBuildup_per90": null,
  "template_player_name": null,     // e.g., "Erling Haaland" — when set, pool ranked by cosine similarity to template (ignores order_by, per90_sort forced true)
  "template_player_id": null
}
```
Validation: `min_*_per90` in [0,5], `per90_sort` bool, `template_*` exclusive (name xor id). Unknown key → 422.

**Response additions (inside each player + top-level meta):**

```jsonc
{
  // ...existing: league_name, season, seasons, date_window, position_group, minimum_minutes, order_by, limit, limitations, players[]
  "per90_sort": false,
  "template": null, // or {"name":"Haaland","id":123,"position_group":"F","honest_note":"Cosine on z-scored per90 vector vs position-filtered pool (same as similar_players)"}
  "age_scatter": [ // for frontend scatter without extra fetch; null until we have birthdates for all filtered before limit
    {"id":123, "name":"Saka", "age":23, "npxG_per90":0.42, "xA_per90":0.28, "team":"Arsenal", "position_group":"F"}
  ],
  "players": [
    {
      // ...existing: id,name,team,position,position_group,favorite_position,age,date_of_birth,team_ppda/team_oppda,minutes,npxG,xA,xGChain,xGBuildup,goals,assists,yellow/red,npg,npxG_per90,xA_per90,goal_involvement_per90,xG_per_shot,conversion,g_minus_xg
      "similarity": null, // 0..1 when template active, else null
      "sparkline": [ // last 5 per-match xG from player_data.matches (most recent first), null if player_data missing
        {"date":"2025-05-10","xG":0.62,"goals":1}, ... up to 5
      ]
    }
  ]
}
```
When `template_player_name` active: ranking is `cosine(z_per90(template), z_per90(candidate))` over `PLAYER_RADAR_METRICS` (same as `similar_players`), filtered by same `position_group`/`minimum_minutes` pool; `players[].similarity` filled, `order_by` ignored but echoed.

`sparkline` derived from `get_player_data.matches` (already cached via `_favorite_position` flow) — no new upstream call in Phase 1 (reuses existing fetch per filtered player? No: to avoid N fetches per discover, we derive sparkline lazily only for `top` players after limit, with per-player `get_player_data` gathered concurrently, max concurrency 8, timeout 2s per player; if unavailable, `sparkline:null`).

### 1.2 `POST /api/v1/analyze/player` — no change (Phase 0 `shot_profile_detail`/`assisted_network`/`enrichment` already present, reused for drill-down)

### 1.3 `GET /api/v1/discover/watchlist` — NOT needed (watchlist is frontend-only `localStorage` in Phase 1, no backend persistence; keeps free-tier stateless)

---

## 2. Per-Data-Point Consideration (every discover/scout field, what it means, how ranked)

| Field (Understat `players[]` or derived) | Type | Meaning | Higher? | Per90 threshold? | Rank behavior | Phase 1 handling |
|---|---|---|---|---|---|---|
| `minutes (time)` | int | Availability | — | denominator | filter `≥ minimum_minutes` (default 900) | Keep; also used to compute per90 for thresholds |
| `age` (Wikidata) | int | Age curve | — | — | `order_by age_asc/desc`, `min/max_age` filter | Keep; also x-axis of `age_scatter` |
| `position, favorite_position → position_group (F/M/D/GK), positions[]` | enum | Role | — | — | pool `filter_by_families` then `filter_by_minutes`; `positions` exact match on `favorite_position` upper | Keep; template similarity also filtered by same group |
| `npxG` | float | Non-pen xG totals | > | `npxG_per90 = npxG*90/minutes` (rounded 3) | `order_by npxG` totals (default) or `per90_sort:true` → rank by `npxG_per90` | Add `min_npxG_per90` threshold (scouts: ≥0.35 for striker) |
| `xA` | float | Expected assists | > | `xA_per90` | same | Add `min_xA_per90` (≥0.15 for creator) |
| `xGChain / xGBuildup` | float | Possession involvement / deep buildup | > | `*_per90` | same | Add thresholds; also tooltip `buildup_share = Buildup/Chain` |
| `goals / assists` | int | Variance-affected output | > | per90 for sparkline tooltip only | `order_by goals/assists` totals or per90_sort | Keep; but add caveat: rank by process preferred |
| `npxG_per90, xA_per90, goal_involvement_per90 (=npxG_per90+xA_per90)` | derived | Process per 90 | > | — | primary process ranking when `per90_sort:true` | Show both totals + per90 in card; sort uses selected metric |
| `xG_per_shot, conversion` | ratio | Selectivity vs variance | > (xG/shot) | — | displayed, not ranked in Phase 1 (Phase 0 plan keeps `g_minus_xg` diagnostic not rank) | Keep display, add threshold later if needed |
| `team_ppda / team_oppda` | float | Press context (team full-season, not windowed) | lower PPDA = intense | — | displayed as pill, not ranked | Keep honest note "full-season team value (not date-windowed)" |
| `similarity` (new, derived) | float 0..1 | Cosine on z-scored per90 vector vs template | > | — | when `template_*` set, rank by similarity desc | Same vector as `similar_players` (PLAYER_RADAR_METRICS), standardized vs pool |
| `sparkline[5]` (new, from `player_data.matches`) | list | Last-5 xG form | — | — | not ranked, displayed as inline mini-bars under card | Fetch per top player via `get_player_data` concurrent, max 8, timeout 2s; null if missing |
| `age_scatter` (new, aggregate) | list | Age vs npxG/90 | — | — | not ranked, scatter viz | Built from filtered pool before limit (birthdates already fetched for age filter); enables "young + productive" quadrant scan |

**Threshold semantics (bulletproof):** `min_npxG_per90` etc. are applied *after* `minimum_minutes` and `position_group` filtering but *before* ranking, on per90 derived values (`_per90_value`). If `minutes==0` → per90 0. Threshold `null` means no filter (backward compat).

---

## 3. Frontend — Discover v2 Evolution (inside existing `view-discover`)

Keep `src/app/dashboard/index.html` `#view-discover` section — do not create `view-scout-v2`. Evolve controls row:

```
Existing: [Season(s)×5] [Positions×8] [Min Minutes] [Rank By] [Limit] [Age Min/Max] [From/To] [Discover Button]
Add:      [Per90 toggle ☑ Totals / Per 90]  [Thresholds: npxG/90 ≥ __ , xA/90 ≥ __ ]  [Template player ___ (typeahead, uses existing /main/getPlayersName via client-side search)]  [Watchlist count pill]
Cards:    existing card + per90 pill when per90_sort, similarity badge when template, sparkline mini-bars, ★ Watchlist toggle
Footer:   [Age vs npxG/90 scatter chart 1100×320, axes labeled] + [Export CSV] [Clear watchlist]
```

Behavior:

- `per90_sort` false (default) → `order_by` ranks by totals (current behavior, no migration).
- `per90_sort` true → re-sort same pool by `*_per90` of the selected `order_by` (e.g., `npxG` → `npxG_per90`). Cards show both `npxG 7.2 (0.42/90)`.
- `template_player_name` non-empty → disables `Rank By` select (muted, tooltip "Ranking by similarity to template, not by npxG"), ranks by `similarity` desc, shows `% match` badge per card (same copy as Similar Players).
- `sparkline`: under each card, 5 vertical bars (height ∝ xG, gold if goal>0), tooltip `date — xG goals`. If `sparkline:null`, show muted `Sparkline unavailable — player_data missing`.
- `age_scatter`: uses `d.age_scatter` (already ranked pool), axes: x `Age (years)` 15→35, y `npxG/90` 0→max, dots colored by `position_group`, `data-tip` = `Name — age y — npxG/90`. Empty when age missing.
- Watchlist: `localStorage` key `prem_watchlist_v1` = `[{id,name,team,position,age,npxG_per90,xA_per90,similarity,added_at}]`. Toggle ★ on card; header pill shows count; `Export CSV` triggers download `watchlist.csv` with header `id,name,team,position,age,minutes,npxG,xA,npxG_per90,xA_per90,similarity`. No backend.

Accessibility: all new controls have `<label>`, thresholds `type=number step=0.01 min=0 max=5`, scatter `role=img aria-label`.

---

## 4. Task Specs per Developer

### Backend-dev — `phase1-backend` (BE-002)

**What to build (additive, noBreaking):**
- `src/app/analytics_service.py:discover_players` — add params `per90_sort: bool=false`, `min_npxG_per90, min_xA_per90, min_xGChain_per90, min_xGBuildup_per90: float|None`, `template_player_name/id: str|int|None`. Validate ranges. After `minimum_minutes` + `position_group`/`positions` + `min/max_age` filtering, apply `min_*_per90` via `_per90_value(p, key) >= threshold`. Then ranking:
  - if `template_*` set: resolve template player via `_find_player_in_league` then `search_players` fallback (same as analyze_player), compute z-scored per90 vector vs same filtered pool (reuse `similar_players` vector logic but compute for discovery pool), rank by cosine desc, fill `similarity` per player (round 3), ignore `order_by/per90_sort`.
  - elif `per90_sort`: rank by `_per90_value(p, order_by_key)` where `order_by_key` maps `npxG→npxG`, `xA→xA`, `xGChain→xGChain`, `xGBuildup→xGBuildup`, `goals→goals`, `assists→assists` (per90 of same key).
  - else: existing totals ranking (keep).
- After `top = filtered[:limit]`, build `age_scatter` from `filtered` (pre-limit) where `age` known, mapping `age, npxG_per90, xA_per90, team, position_group`.
- Build `sparkline` per `top` player: `asyncio.gather` up to 8 `client.get_player_data(id)` with 2s timeout per player (asyncio.wait_for), parse `matches` last 5 (most recent date desc), map `{date, xG, goals}` (xG from matches rows if present else 0). If fails, `sparkline:null`. Do not N+1 fetch beyond top 8 (if limit 100, only first 8 get sparkline, rest null — documented limitation).
- Return new keys: `per90_sort, template, age_scatter, players[].similarity, players[].sparkline` additive.

**Unit tests to add (must pass before report done, keep 145 existing green):**
- `tests/test_phase1_scouting.py` (new):
  - `test_per90_sort_ranks_by_per90_not_totals` — two players: A minutes 1800 npxG 6 (0.30/90), B 900 npxG 4 (0.40/90) → with `per90_sort=false` A before B, `per90_sort=true` B before A.
  - `test_min_npxG_per90_threshold_filters` — min 0.35 removes A (0.30) keeps B (0.40).
  - `test_template_ranks_by_similarity` — template Haaland, pool 3 players → returned `similarity` desc, `order_by` ignored.
  - `test_age_scatter_excludes_missing_age` — missing birthdate excluded, scatter length == filtered with age.
  - `test_sparkline_null_on_missing_player_data` — mock `get_player_data` raises → sparkline null but no crash, discover still returns.
  - `test_backward_compat_existing_call_unchanged` — old call without new params returns same ordering as before (per90_sort false, no threshold).
- Keep multi-season merge rules and existing limitations honest notes.

**Serves:** User: every discover data point considered (thresholds on per90, template similarity on same vector, sparkline from matches, age scatter from age) + bulletproof (validate, not N+1, timeout, graceful null).

### Frontend-dev — `phase1-frontend` (FE-002)

**What to build (inside `#view-discover` only, no new view):**
- Evolve controls: add `per90_tgl` checkbox, `thresh_npxG`, `thresh_xA` number inputs (0..5 step 0.01), `templatePlayer` text input + datalist (optional typeahead via `GET /main/getPlayersName`? Use existing search if available else plain text submit). Add watchlist count pill next to Discover button.
- Wire `discoverGo` to send new params: `per90_sort, min_npxG_per90, min_xA_per90, template_player_name` alongside existing filters. Keep existing `populateSeasonSelects` etc. untouched.
- Render: cards show `npxG 7.2 · 0.42/90` when per90_sort, `similarity 87% match` badge when template, sparkline mini-bars under card (`<div style="display:flex;gap:2px;height:18px">` bars, gold border if goal>0), `age_scatter` chart via new `drawAgeScatter("discoverAgeScatter", d.age_scatter)` (1100×320, x Age 15–35, y npxG/90 0–max, axes labeled "Age (years)" / "npxG /90", dots `F→#38bdf8 M→#10b981 D→#f59e0b`).
- Watchlist: `localStorage prem_watchlist_v1` read on load, toggle per card ★, header pill count, `Export CSV` button → create `Blob` with header + rows, `URL.createObjectURL`, `a[download]`, click. `Clear watchlist` clears storage + pill.
- Null-safe: sparkline null → muted text, age_scatter empty → "Age data unavailable for scatter — add min age filter?".
- Keep all Phase 0 axis titles / zones / types / forecast — do not regress. Scale of new scatter must be: `x = x0 + (age-15)/(35-15)*(x1-x0)`, `y = y1 - (npxG_per90 / maxPer90)*(y1-y0)` (maxPer90 ≥0.1). No backend scale change — tested by snapshot.

**Serves:** "Efficient scouting" loop Filter→Rank→Profile→Shortlist→Track in 3 clicks, richer visuals without external data, per-data-point honoring + bulletproof empty states.

---

## 5. QA & Adversary gates (Phase 1 exit)

- `uv run python -m unittest discover -s tests -v` green + 6 new phase1 tests.
- Screenshots: Discover with thresholds+template+sparkline+scatter at 375/1440 (no clip, scatter axes labeled).
- Only `docs/*.md` by lead; devs own code per specs.

