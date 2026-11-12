# Roadmap: what is done, what is left, what is new

Written 2026-11-11 so the work can be picked up from a cold start. It records the owner's requests in his own terms, what the data can and
cannot support, and the order to do things in. Update it as items land; delete an item when it is merged.

## 1. Where things stand

Four passes of redesign sit **uncommitted in the working tree on `main`** (about 40 files). Nothing has been committed because the owner has
not asked. When he does: small conventional commits, one concern each, PR merged with `--rebase`.

Done and verified by eye (light, dark, phone) on a copy of the real database:

- **Match centre** (`/match/{id}`): scoreboard, tabs Overview / Shots / Passing / Defending / Line-ups / Players, period picker, momentum,
  numbers by half, leaders, goal mouth, pass network, formation pitch. Backend `GET /api/match/{id}/centre`
  (`src/app/analytics/match_centre.py`); browser derives everything from raw rows (`js/lib/matchcentre.js`, tested).
- **Unplayed match**: "The season so far, side by side".
- **Shared pitch and heat map** redrawn; heat is a banded canvas surface, resolution 10 px per cell, higher floor for a season of events.
- **Finding cards** draw their numbers (value against reference, score out of 100, latest against previous); a shared caveat is said once.
- **Briefing** rebuilt (findings beside a table snapshot, results four to a row).
- **Team overview**: full measure names in "How they play", five fixtures.
- **Compare**: radar for players; team style chart grouped with full names; dot plot has a phone layout.
- **Player**: percentile pizza (label collisions fixed).
- **Teams explorer**: no repeated league line. **Guide**: match-centre entries.

Checks (JS re-run 2026-11-12 after F and E: 100 JS tests pass; Python untouched since): 482 pytest, 91 JS tests, ruff and mypy pass. Earlier note: 85 JS tests pass (`node --expose-internals --test tests/js/`). 473 pytest passed after pass 2; **not re-run since** (later passes
touched only JS, CSS, docs). `tools/e2e.mjs` has new checks but has **never been run** against this work (no Playwright locally; CI runs it).

### Loose ends from the passes above

- [x] `docs/features.md`: pass 4 added (2026-11-11).
- [x] `uv run pytest`, `ruff`, `mypy` re-run 2026-11-11: all pass.
- [x] `tools/e2e.mjs` run locally 2026-11-12 with real Playwright (installed in a scratch folder, not the project; the browser is the
  Chrome for Testing already in the Playwright cache, passed with `--chromium`). First run 82 of 86: four checks were out of date
  (desk pages keep their title in the rail; the shot board lists many takers in a menu, not chips; with event data the match page
  shows "The match in numbers" instead of "How the game was played"; one tooltip wait was too short) and were brought in line.
- [x] Scout map view (2026-11-12): the dots named are the ones furthest from the middle of the map (not the table's first rows); a
  name never covers another dot (`placeLabels` takes the dots as obstacles); dots beyond the edge are left out and counted in the
  note instead of piling on the border.
- [x] Match pass network (2026-11-12): a name must be nearer its own dot than anyone else's, else it moves out on a short leader line
  (`placeNames` in `js/charts/pitchmaps.js`).
- [x] Compare players on a phone: reviewed 2026-11-12 on two real players at 390 px. Nothing overflows; the cards, the shape chart,
  both dot plots and the totals read in one column.
- [x] Briefing table on a phone scrolls sideways to reach Form (2026-11-12: Form is dropped under 560 px).

## 2. What the owner asked for (2026-11-11)

In his words, condensed:

1. Filters on every page are "not nice"; the tables and metrics are "trash" and a new user "might not understand anything there".
   Pages named: Scout, Teams, League, Matches, the match page, Compare.
2. Pass strings: the sequence, where it broke, **who broke it and who lost it**. All passes of a move with **order number and player name**,
   and whether it went out, led to a shot, a shot on target or a goal. Possibly a new tab on the match page, "if you can do it correctly and reliably".
3. Work on the **light theme**.
4. Distance covered, high-intensity runs: do we have them?
5. **Stat padding**, shown visually: driving runs and passing that look busy but create nothing. "In any stat or metric."
6. Page composition: cards and charts should not look "slapped together like Frankenstein"; every page "has a story".
7. xG on shot maps, per shot, with who took it; consistent at match, player and team level. Anything shown at one level should be there at
   the others where it makes sense.
8. Check the data layer and the update UI.

Standing rules that still apply: blank rather than wrong (no estimated xG, no made-up numbers); finish everything and verify visually;
never leave a server running; commit only when asked.

## 3. What the data can support

Sources: Understat (xG, shots, players, teams) and WhoScored event streams (Opta-style: ~1,500 on-ball events a match with position, outcome,
qualifiers). `src/app/events/schema.py` is the vocabulary.

| Ask | Verdict | Basis |
| --- | --- | --- |
| Distance covered, sprints, high-intensity runs | **Not available.** These need tracking data (player positions 25 times a second). Neither source has it. Do not approximate. Say so once in the Guide and the Dictionary. | Event data records only on-ball actions. |
| Carries ("driving runs") | Available as an **estimate**: ball moved 3 m+ between two events of the same team within ten seconds (`counters.carries`). Already labelled an estimate. | `src/app/events/counters.py:138` |
| Pass strings with order and names | Available. Events are ordered (`em`, period, event index) with player and team. Receiver is **not** in the data: it is inferred (next team-mate touch within 8 s), already done in `match_centre.py`. | `silver.Match`, `match_centre.build_centre` |
| How a move ended | Available: shot (and result), ball out, foul, offside, or lost to an opponent's tackle, interception, recovery, clearance, blocked pass. Opta also flags `LeadingToAttempt` / `LeadingToGoal`. | `schema.FLAGS`, `DEFENSIVE_EVENTS` |
| Who lost it / who broke it | Available: last player on the move, and the opponent whose event ended it. For an unforced loss (bad pass out of play) there is a loser and no breaker: show it that way. | same |
| xG per shot | Available where Understat has the shot and it matches a WhoScored shot (`attach_xg`: side, minute ±1, nearest spot). Unmatched shots stay blank. | `match_centre.attach_xg` |
| xG of a possession | Sum of the matched shots' xG in that move. Blank if a shot is unmatched. | derived |

Possession sequences already exist as **team totals** only (`counters._sequences`: count, passes, 10+ pass moves, reached final third / box,
ended in a shot, direct attacks). The per-sequence rows are computed and thrown away. Workstream A keeps them.

## 4. Workstreams

Order matters: A and B change the data layer, and C–F draw on them. G and H are independent and can go any time.

### A. Possessions: pass strings, where they broke, who (new)

**Status 2026-11-11: the match level is done** (uncommitted). `src/app/events/possessions.py` builds the moves (break rule in its
docstring and in `docs/data.md`), `build_centre` sends them as `possessions` (`CENTRE_VERSION` 2), the Match page has a **Moves** tab
(`js/ui/matchmoves.js`, `js/charts/movepitch.js`, helpers and tests in `js/lib/matchcentre.js`). Checked against the raw events of
Arsenal v Coventry by hand and swept over 237 stored matches (every shot lands in exactly one move; ~264 moves a match; 6 ms each).
Two departures from the plan below: the counters' `_sequences` was **not** replaced (its simpler rule gives different totals, and changing
it means re-deriving every stored match: do it with the "other levels" step), and the tab is `?view=moves`, named "Moves".
**Other levels done 2026-11-12** (uncommitted): `src/app/events/movestats.py` sums the same moves on request (no new stored counters:
a match's moves build in ~6 ms, and the map payload is remembered). Team → Style & maps: "How their moves end" (ends as one bar; by
where and by how the move began with the share that came to a shot; a heat map of where the ball is lost; who lost it most; who took
it off the opponents most). Player → Maps: "Moves he was part of" (where he lost it and how; where he took it). `js/ui/moves.js`,
`tests/test_movestats.py` (hand-counted), two e2e checks. The totals match the stored `mv_*` counters on a real player.
**Still open:** the hand check against a second match on WhoScored's own page; `counters._sequences` still uses its older rule.

**Backend**
- Lift the sequence builder out of `counters._sequences` into one function that returns rows, used by both the counters (totals unchanged:
  prove it with the endpoint-recording method in the memory note) and the match centre.
- One possession row: team, period, start/end clock, ordered steps `[event index, player, kind (pass / carry / take-on / touch), x, y, ex, ey, ok]`,
  how it started (recovery, set piece type, kick-off, throw-in), how it ended (`goal`, `shot_on`, `shot_off`, `shot_blocked`, `out`, `foul_won`,
  `offside`, `lost`), **lost_by** (player), **broken_by** (opponent player and action), shot index and xG if any, reached final third / box.
- Add to the centre payload as `possessions`; bump `CENTRE_VERSION`.
- Decide the break rule once and document it in `docs/data.md`: an opponent touch ends a move, **except** a deflection that leaves the ball
  with the same side (Opta `BallTouch`, an unsuccessful tackle). Test against two real matches by hand before trusting it.

**Browser: new match tab "Possessions"** (`?view=moves`)
- Left: a filterable list of moves. Filters as plain chips: team, half, ended in (goal / shot / lost / out), 5+ passes, reached the box.
  Sorted by clock; each row shows clock, team, passes, players involved, how it ended, xG.
- Right: the selected move on a pitch, each pass **numbered in order** with the passer's name, carries dashed, the end marked
  (shot glyph, or a cross where it was lost with **"lost by X, won by Y (tackle)"**). Step through with arrow keys.
- Under it: the move as a numbered text list (1. Raya → Saliba, 2. Saliba → Rice …), which is also the accessible version.
- Summary cards above: longest move, moves that reached the box, moves ending in shots, **who lost the ball most** and **who broke up most**
  (per player, with where on the pitch).

**Other levels (ask 7: same thing at every cut)**
- Team page → Style & maps: "How their moves end" (share ending in shot / lost / out, by start zone), top move-enders.
- Player page → Maps: "Moves he was part of" and "where he lost it".
- These need the possession rows aggregated into the gold counters (per player: `seq_involved`, `seq_shot_involved`, `seq_lost`,
  `seq_broken`). That bumps the counters version and re-derives stored matches: check how long that takes on the real database first.

Done when: a move in the list matches the events of that minute on WhoScored for two matches checked by hand; unit tests cover the break
rule, a set-piece start, an unforced loss and a move ending in a goal.

### B. Empty volume: singling out stat padding (new)

**Status 2026-11-11: built at every level except Team → Players** (uncommitted). What exists:
- Rule (`events/possessions.py`: `led_to_shot`, `action_outcomes`; written up in `docs/data.md`): an action "came to a shot" when its move
  ended in one, or won a corner, free kick or penalty that was the side's next move and ended in one. One link only.
- Counters, gold version 2 (`prog_shot`, `carry_prog_shot`, `takeons_won_shot`, `crosses_shot`, `f3_entry`, `f3_entry_shot`, `mv_in`,
  `mv_shot_in`, `mv_lost`, `mv_broken`). The rebuild took 36 s for 643 matches on a copy of the real database; it runs once on the next
  start. These also cover workstream A's "other levels" counters (moves a player was in, lost, broke up).
- Measures: player group "What came of it" (13 measures, e.g. `progact_shot_pct`, `carryprog_shot_pct`, `takeon_shot_pct`, `movelost90`) and
  `progpass_share` under Passing; four team measures; a column set "What came of it"; lenses "Busy, little end product" and "Progress that counts".
- Scout and Teams map: "Start from a question" presets; a trend line **per role** (`fitLine`, `offTheLine` in `js/lib/stats.js`) with the
  players furthest below and above their own role's line named. One line for all roles was tried first and only said "defenders are defenders".
- Player → Profile: card "What his actions led to" (`OutcomeBars` in `js/charts/bars.js`). Match → Players → By half: "Busy, and what came of it".
- Guide entries for this and for workstream H (no tracking data); the Dictionary's WhoScored limits say the same.
- Checked: hand count in `tests/test_possessions.py`; values on 2025/26 EPL read sensibly (Salah, Saka, Doku top; holding midfielders low);
  dark, light and phone screenshots; the two new e2e checks' selectors exercised by hand on the demo world.

**Done 2026-11-12:** the split bar in tables: every "came to a shot" column of a desk table (Scout, Team → Players) draws it under
the number (`SPLIT_OF`, `SplitBar` in `js/ui/explore/Sheet.js`; length against the 95th percentile of the regulars listed); the Team
page and Player → Maps views (see A).
**Also done 2026-11-12:** the xG of the shots moves came to, joined from Understat match by match (`match_centre.shot_xg`,
`mapdata.xg_reader`): the Team and Player moves cards say what those shots were worth and for how many it is known; each shot is
counted once. Checked on Arsenal 2026/27: 11.84 xG over 78 shots, against Understat's own 11.85 over the same 78.
**Still open:** that xG split by kind of action (progressive pass, carry, take-on), and "lost within the next N actions" as a
second outcome.

The idea, stated honestly: **volume against what came of it**. Not a judgement of a player, a description of his actions.

- For each progressive carry, progressive pass, take-on, cross and final-third entry, record whether the same possession went on to a shot
  (and its xG), to the box, or was lost within the next N actions. This falls out of workstream A for free.
- New per-90 measures: `carry_prog_to_shot`, `carry_prog_empty` (and the same for passes, take-ons, crosses), plus a rate
  "share that led to a shot". Dictionary entries for each, with the caveat that a carry can help without a shot following.
- **The visual** (one reusable chart, `VolumeOutcome`): a scatter of volume per 90 (x) against outcome per 90 (y) with the role's trend line;
  players far **below** the line at high volume are labelled. Plus, in tables, a split bar per player: the solid part led somewhere,
  the hatched part did not.
- Where: Scout (a lens "Busy, little end product" and the map preset), Player → Profile (a card "What his actions led to"),
  Team → Players, match → Players.
- Apply the same split to passing: completed passes that were backwards or sideways under no pressure inflate pass accuracy. Show
  pass accuracy beside **progressive** pass share so the first is never read alone.

Done when: the lens and the chart agree with a hand count on one player-match, and small samples are faded like everywhere else.

### C. Filters and tables a new user can read (ask 1)

**Scout rebuilt 2026-11-11**, uncommitted. The owner rejected the first mock-up (question chips and a filter written as a sentence) and
approved a three-part desk, asking for uniform column headings (short name, full name on hover). Built: `js/ui/explore/Rail.js` (filter rail
with histograms, rule cards, ready-made searches, kept searches), `Sheet.js` (fixed-width columns, heading menu, shaded cells, scroll memory),
`Peek.js` (player beside the list), `css/desk.css`, `pages/scout.js`. The explorer model, the URL and `lib/filters.js` are unchanged, so old
links work.

**Every other table moved onto the desk 2026-11-11** (later session), uncommitted:
- **Teams** (`pages/teams.js`): full desk; the rail shows usual formation, rules, team ready-made searches, kept searches; a Form column;
  a row opens `TeamPeek` (place, points against xPts, form, manager, ranks on results/chances and on style in grey).
- **Team → Players** (`pages/team-players.js`): an `inset` desk inside the team page (rail kind `squad`: no club, no kept searches).
- **Deep analytics** (`ui/matchdeep.js`): an `inset` desk whose state lives in the component (`useLocalQuery` in `explore/model.js`; the
  match page already uses `view` and `tab`). Rail kind `match`: side chips (clubs filter), match minutes (opens on 30+, shown as a pill),
  "Started / Came on" (`part` now reads `row.started` when there is no minutes share), rules. Best and weakest cells are ringed (`marks`).
- **Shortlist** (`pages/shortlist.js`): the sheet without a rail (`desk norail fit`), "Your note" as a column, peek, compare tray
  (`explore/Tray.js`). Players with no minutes this season stay as blank rows with their note.
- **League** (`pages/league.js`): the sheet without a rail; the three views are tabs; headings borrow the team catalog's definitions
  (`FROM_CATALOG`) plus four of its own; ranks within the league from `rankShares` (`lib/stats.js`); luck columns are bars scaled to the
  largest gap; places are a stripe down the first column. Row click still opens the team page (no peek: the league endpoint's numbers
  follow the venue/window filters, the team dataset's do not).
- **Matches** (`pages/matches.js`): not a table, so no desk; a Team picker shows one club's season (next three, results, the rest) and
  works with "Results that lied". `teamRecord` in `lib/matchfmt.js`.
- `Sheet` takes column objects as well as measure keys (`{ key, label, title, width, render, sort }`; a measure key with `render` keeps its
  menu), a `colWidth`, `marks`, `lead.rowClass`; `HeadMenu` hides filtering where the model has no `setFilters`.
- Removed: `FilterBar.js`, `LensBar.js`, `RuleEditor.js`, `Results.js` (its helpers moved to `model.js`), `charts/distribution.js`, and
  their CSS. `DataTable` stays for the small tables on other pages (match log, splits, data page ...).
- Checked by eye on a copy of the real database (light, dark, 390 px phone: no sideways scroll). `tools/e2e.mjs` updated for every moved
  page (and new checks: formation filter, team peek, squad desk, deep analytics on the desk, a team's season on Matches). The script
  itself still runs in CI only; its new and changed steps, and the accessibility audit on the moved routes, were walked in page JS over
  DevTools on the demo world: 16 of 16 passed.
- Fixed on the way: `.fade-in` (base.css) used `animation-fill-mode: both`, which kept a transform in effect, so the compare tray (and any
  `position: fixed` child) was placed at the foot of the page content instead of the window. Now `backwards`.

Still open under C: the owner's verdict on the moved pages; the small `DataTable`s elsewhere (about twenty: Briefing table, team Matches, player
match log ...) now carry the desk's heading (white, the sorted column underlined in the accent) from one rule in `components.css`; they
stay `DataTable`s, since the desk's Sheet is built for a catalog of measures. The "Direction" list below is superseded where it says question presets and a sentence.

Audit first, with the owner's complaint in mind, then change. Files: `js/ui/explore/*` (FilterBar, LensBar, RuleEditor, ColumnPicker,
Results, model), `js/ui/table.js`, `js/ui/cells.js`.

Known problems seen in screenshots:
- Scout opens on three rows of ~20 lens chips with counts, before any result. A newcomer does not know what a lens is.
- Column headings are abbreviations (`npxG/90`, `G-xG`, `xGChain`) with meaning only on hover.
- Cells show a number and a thin percentile underline; nothing says the underline is a percentile.
- 122 metrics, no starting point by question.
- League has three table views and two more controls in one header row.

Direction:
- **Start from a question, not a control**: a first row of 5–6 plain presets ("Who creates most?", "Best finishers", "Young and
  playing", "Ball winners") that set sort, columns and filter together and say so in one line that can be undone. Lenses move behind
  "More ways to narrow".
- **Filters as a sentence**: "Showing *midfielders* aged *under 23* with *900+ minutes*, sorted by *xA per 90*", each italic part clickable.
  One place, same wording on Scout, Teams, Team → Players.
- **Headings in words** where width allows, abbreviation otherwise, and a one-line legend above the table for the percentile bar.
- **One table component behaviour everywhere**: sticky first column, same density, same sort affordance, same empty state.
  League, Briefing, Team → Matches, Shortlist currently differ slightly.
- Matches: filter by team and by "results that lied" in the same sentence pattern.
- Test with the `design:design-critique` and `design-skills:ux-writing` skills before building.

Done when: a first-time user can get from opening Scout to "the best young creators" without reading a tooltip. e2e checks updated.

### D. Shots and xG at every level (ask 7)

**Done 2026-11-11**, uncommitted. One shot board (`js/ui/shotboard.js`, pure helpers in `js/lib/shots.js`, drawing in `ShotPitch` in
`js/charts/pitch.js`) replaces the three different shot maps: Match → Shots, Player → Finishing and shots, Team → Chances → Every shot.
The same look everywhere, the map-lab shots layer included: size = xG, solid with a dark rim = goal, half filled = saved, faint = off target
or blocked, dashed outline = no xG for this shot (never counted as zero; totals say how many shots have none). Beside the map, the shots in
a list ("In order" / "Best chance first"); hovering a row rings its circle and the other way round; picking one opens its detail (taker,
minute, result, xG in words, body part, situation, assist, what it came from, links to the player and the match). Filters: side, situation,
result, and taker (chips in a match, a menu for a team's season). `/api/team/shots` rows gained player id, assist and last action, plus a
`games` map (date, opponent, home) so a team's shot can name its match.

Parity (✓ present, – not applicable, ✗ missing):

| Feature | Match | Player | Team | League |
| --- | --- | --- | --- | --- |
| Shot map, list and one shot's detail | ✓ | ✓ | ✓ | – (about 10,000 shots a season; the league view is team totals) |
| xG of each shot with its taker, body part, situation, assist | ✓ | ✓ | ✓ | – |
| Filter by taker | ✓ | – | ✓ (own players) | – |
| Filter by situation and by result | ✓ | ✓ | ✓ | – |
| A shot with no xG marked, never estimated | ✓ | – (Understat shots only) | – | – |
| Link from a shot to its match / its taker | taker | match | both | – |
| Where the shot went in the goal | ✓ (event data) | ✗ | ✗ | – |
| xG over time | ✓ race, by period | ✓ Match trend | ✓ Overview, History | ✓ table trend, race |
| Goals against xG (finishing luck) | ✓ findings | ✓ distribution | ✓ findings, Chances | ✓ table columns |
| Breakdown by situation, body part, zone | by filter (totals follow) | ✓ table | ✓ Chances | ✓ Chances "versus the league" |

Done 2026-11-12: the goal-mouth view for a season (`maps.goal_mouth` in the map payload, `js/ui/goalmouth.js`): Player → Finishing
("Where his shots went in the goal") and Team → Chances (the team's shots and the shots it faced). No xG there: it is event data.

### E. Page composition: every page tells one story (ask 6)

**Status 2026-11-12: first step done** (uncommitted). `.grid.fill` (pages.css) makes the cards of a row end on one line, the shorter one
centring its content. Team overview: "Every match" and "What is next" share a height; the Managers table shows only with two or more stints
(Splits then takes the full row); the rolling chart waits for four points of the five-match average (eight matches) instead of two.
Player profile: the pizza and the role bars are one balanced row; **Role** moved to the end of the tab as a two-column reference card
(`.role-facts`). League and Scout were looked at under the new theme and left as they are (rebuilt under C).
**Second step 2026-11-12** (uncommitted), after looking at every Team tab, every Player tab, Compare (players and teams) and Briefing on
a phone:
- Player: the findings moved from above the tabs into the **Profile** tab (as a team's sit in Overview); the other tabs now start ~330 px
  higher. **Finishing**: "How unusual is his finishing?" and "Shot quality" are one card (`.finish-lead`: chart left, verdict and the shot
  facts right). **Seasons**: the four small charts label seasons `21/22` when there are five or more (the full labels ran into each other).
  **Match trend**: "What stands out" and "Who he played" end on one line (`.grid.fill.start`).
- Compare: players of different roles got two notices saying the same thing; only the warning stays. Teams: the last row ends on one line.
- Briefing on a phone: three findings instead of six before the table (`useMedia`), and the table drops Form and narrows the gap bar under
  560 px, so it no longer scrolls sideways (measured: 356 of 356 px). This closes that loose end in section 1.
- Team tabs (Players, Style & maps, Chances, Matches, History) were reviewed and left as they are.
**Still open:** replacing the remaining `grid cols-2` / `cols-wide-narrow` with one rhythm; Data (under G). Compare players on a phone was reviewed (see loose ends).

For each page write one sentence, "this page answers …", then order the cards to answer it: headline finding → the evidence chart →
breakdowns → reference tables. Remove or merge cards that do not serve the sentence. Pages in order of need: Team overview, Player profile
(card heights leave holes beside the pizza), Scout, League, Data. Keep one grid rhythm (the `mrow` 7/5 and equal halves) instead of the mix
of `grid cols-2`, `cols-wide-narrow`, `mrow`.

### F. Light theme (ask 3)

**The owner agreed with it on 2026-11-12.**

**Done 2026-11-12** (uncommitted), `css/tokens.css` light block only (dark untouched apart from the shared notice rule): ground `#e8ecf1`,
cards `#ffffff`, `--surface-2/3` and both line tokens a step darker, `--ink-2/3` darker, pitch `#afd1b5` / `#a3c8aa` with white lines,
cards carry `--shadow-sm`, `.notice.warn` is a white strip with an amber inset edge (both themes). Contrast computed: every text token is
4.5:1 or better on `--bg`, `--surface`, `--surface-2`, `--surface-3` (`--accent-strong` darkened to `#2265b9` for that). Known and accepted:
team-colour marks on the pitch are below 3:1 against any green (orange 1.9:1); they carry rims and labels. Re-shot in light: Briefing, League,
Scout, Team overview (desktop and phone), Player, Match overview / Shots / Passing / Moves, Data; dark spot-checked on Team.
**Series colours checked 2026-11-12** against the light surfaces (contrast ratio computed for `--c1` to `--c8` on white and on
`--surface-2`; a mark needs 3:1): orange, teal, amber and pink fell short (3.2, 2.8, 2.2, 2.7 on white) and were darkened just enough
(`#ea612b`, `#189d6e`, `#bd8000`, `#e35d8f`: 3.4 on white, 3.05 on `--surface-2`). The dark theme already passed (3.7 to 5.9). The theme switch already existed (`ThemeToggle` in `js/app.js`, an icon in the top bar cycling system, light, dark); it now carries its name (Auto / Light / Dark) beside the icon.

Seen in screenshots: page ground and cards are nearly the same pale grey, borders are faint, so cards do not separate; the pitch green is
washed out; the amber data notice is the loudest thing on every page. To do in `css/tokens.css`: stronger ground/surface step, one clear
border token, a deeper pitch, quieter notices, and check text contrast (WCAG AA) with the `design:accessibility-review` skill. Run the dataviz
palette validator on the series colours against the new light surface. Re-shoot every page after.

### G. Data layer and the update UI (ask 8)

**Status 2026-11-12: the defects found on the owner's running app are fixed** (uncommitted). What was found, on real data:
- **Understat has been down since about 11 October** (every address answers a page that only says "We will come back soon"), so no league
  table or match page has arrived for a month. Nothing in the app said so: the Data page reported "0 problems" and the top-bar pill was green.
- **The updater woke every minute** while that lasted: a refresh that failed served the stored table as "stale" without counting a failure,
  so the due moment stayed in the past. Each cycle asked every league and every missing match page again (6,497 requests in 4.5 hours)
  and spent the day's 300-page limit on failures. Every page view also re-asked (about 130 requests for one open Briefing).
- **The event fetcher has failed since the Mac moved to macOS 27**: SeleniumBase's `uc_driver` in the project's `.venv` is an x86_64
  binary and Rosetta is not installed. The Data page only said "the fetcher exited with status 1".
Fixes: `sync/autosync.py` (`_refresh_failed`: a failed refresh is a failure with the usual back-off, its match pages wait, and once the
source says it is down the other leagues are not asked in that cycle; `last_error`: the fetcher's closing log lines become the failure's
text); `data/understat.py` (the maintenance page is named for what it is); `data/repository.py` (`REFRESH_HOLD`: a failed refresh is not
asked for again for four minutes, the stored copy is served with the reason). Tests in `test_autosync.py` and `test_data_layer.py`
(485 pytest pass). Checked by one real cycle on a copy of the database with updates on: 5 requests instead of 134, next try 15 minutes
away instead of 60 seconds.
Data page (`js/pages/data.js`, `data-tools.js`, `data-events.js`): opens on **three questions** (`StatusHead`: is it up to date, what is it
doing, what needs you); the top-bar pill turns amber when live tables are more than two days old; a reason shared by several leagues is said
once; "How the data layer works" is folded; Player ages scrolls inside its card (it was 4,200 of the page's 9,100 px; the page is now
5,600); Fetch plan no longer scrolls sideways.
**Still open:** the owner has to restart the app for the fixes to run; the rest moved to section I (Rosetta is no longer needed, and
"Update now" is done).

- Read `src/app/sync/*`, `src/app/jobs.py`, `src/app/events/fetch.py`, `ledger.py` and `js/pages/data*.js` end to end; list defects before
  changing anything.
- Known from the screenshots: the Data page is ~8,900 px tall; "Fetch plan" cuts columns off; the real database was last updated
  2026-10-11 and the page says "Finished 30 days ago" without saying what to do about it.
- Direction: a status header that answers three questions (is it current, what is it doing, what needs me), with the long tables
  collapsed below. Make "Update now" state what it will fetch and roughly how long.
- Verify a real update cycle on the **copy** of the database, never the live one, and never with `uv --python`.

### I. Backend data layer: WhoScored was not loading (asked 2026-11-12)

The owner: "check backend data layer and stuff please because WhoScored data was not loading". He also agreed with the light theme (F is
settled) and asked for "Update now" to be closed.

**Done 2026-11-12** (uncommitted):
- **Why it was not loading.** SeleniumBase's undetected mode uses an Intel `uc_driver` on Apple silicon on purpose (macOS will not run an
  Apple-silicon program whose bytes were edited after signing), and that needs Rosetta, which this Mac (macOS 27) does not have.
  `src/app/events/nativedriver.py` now prepares an Apple-silicon driver on such a Mac: it copies the arm64 ChromeDriver SeleniumBase keeps,
  makes SeleniumBase's own edit, and signs it again ad hoc; the Intel one is kept beside it as `uc_driver.intel`. Called from
  `fetch.make_reader`. Nothing runs on other computers. Checked for real: one match fetched by hand into a copy of the database, then the
  updater started the fetcher by itself and stored a full run of 20 (58 to 78 of 100 Premier League matches).
- **Event data no longer waits for Understat's table.** The catch-up counted only matches Understat lists as played (59) while WhoScored
  had 100: `AutoSync._finished` also counts fixtures that kicked off over four hours ago (used by `_backfill` and `plan`).
- **Update now** (`AutoSync.run_now`, `POST /api/data/auto/run`): tries again at once whatever is waiting out a failure, and the Data page
  lists what the press will do and about how long it takes (`updatePreview` in `js/pages/data.js`).
- Tests: `tests/test_nativedriver.py`, three more in `test_autosync.py`. 491 pytest, 100 JS tests, ruff, mypy pass.

**Second pass (2026-11-12, later):**
- **A browser update.** `prepare` now looks for an Apple-silicon ChromeDriver of the *browser's* version in both of SeleniumBase's
  folders, downloads one when neither has it, and replaces a `uc_driver` of the old version (before, an old Apple-silicon driver in
  place made it give up). Simulated in `tests/test_nativedriver.py`; not yet seen after a real browser update.
- **The driver problem is said up front.** `AutoSync.events_capability` asks `nativedriver.problem` (kept for 15 minutes) and answers
  "not available" with the reason and the Rosetta command; `make_reader` stops with the same message instead of going on to fail.
- **A browser error page saved as the match list** (found on the running app, 10:31 that day: the network dropped, Chrome's "Your
  connection was interrupted" page was saved as January's matches, the fetcher died with a traceback and every later read of the
  list from the cache would have died on the same file). `fetch.read_list` throws such files away (`drop_bad_lists`), reads again
  once, and otherwise stops with a plain sentence; `sync_season` writes the reason into the run status, where the Data page reads it.
  Proved on the copy with the real bad file against the real site.
- **A wall of failures is not charged to the matches** (`ledger.forgive`): five in a row is the connection or the site, so those
  matches are tried again next run instead of drifting to "waiting for a person" after three outages.
- **Finished matches Understat has not published** (19 in the Premier League while Understat is down). They were stored by the
  catch-up fetch, had no matchday note, and the Matches page showed them as "finished, result arrives shortly" with no score, and
  the match page refused them. `MatchesPage.stored_games` finds the stored WhoScored match of such a fixture (same clubs, home with
  home, within a day, only one fit) and the existing matchday path does the rest: the card shows the real score, scorers, shots
  and possession with "No xG yet: Understat has not published this match"; the match page opens with every event tab and no xG;
  round and team summaries count them and leave xG out rather than adding zeros. `link_fixtures` no longer lets its nameless pass
  (date and score alone) claim a match whose clubs are plainly two other clubs.
- `fetch.py`, `ledger.py`, `raw.py`, `store.py` read end to end: the three faults above are what it found.
- 498 pytest, ruff, mypy pass.

**Still open:**
1. A full cycle with Understat back (still down on 2026-11-12): league tables, the 37 match pages still missing, xG joined onto the
   newer event matches, and the 19 "from WhoScored" cards turning into normal ones.
2. The first event run after a real Brave or Chrome update.
3. Settled (owner, 2026-11-12): the league table, team form and player totals stay Understat's and stop where Understat stops; only
   the Matches page and the match page know the newer results. Do not mix WhoScored results into the table.

Settled: event data is on for the Premier League and Serie A only; La Liga, Bundesliga and Ligue 1 are off on purpose (owner,
2026-11-12). Do not switch them on or raise it again.

### H. Not possible: say it plainly

**Done 2026-11-11** (Guide card, Dictionary source limits, `docs/data.md`).

Add to the Guide and the Dictionary: distance covered, sprints and high-intensity runs are not in the app because no free source
publishes tracking data; carries are the nearest thing and are an estimate.

## 5. Suggested order

1. Loose ends in section 1 (small; gets the tree to a known-good state). Offer to commit.
2. **A** backend + Possessions tab (the owner's most concrete ask).
3. **B** empty volume (reuses A).
4. **D** shots parity.
5. **C** filters and tables (largest design change; do the audit and show the owner a mock-up of the "sentence" filter before building).
6. **F** light theme, then **E** composition (both are re-shoots of every page; do them together).
7. **G** data layer and update UI.
8. **H** alongside whichever of the above touches the Guide.

## 6. How to work on this

- Real data safely: `sqlite3 .prem-data/prem.sqlite ".backup <scratch>/real/prem.sqlite"`, then
  `uv run prem serve --offline --data-dir <scratch>/real --port 8766 --no-open` through a temporary `.claude/launch.json` (delete it after).
  Demo data: `--demo` on 8765. Useful ids: EPL match 31230 (Arsenal v Leeds), in-play read Serie A 31618, unplayed 31239, player 7603.
- Full-size screenshots: `chrome-headless-shell` from `~/Library/Caches/ms-playwright/chromium_headless_shell-*/`, started with
  `--remote-debugging-port`, **outside the command sandbox**, driven over DevTools (set viewport, colour scheme, capture a clip). The full
  Chrome for Testing build would not load pages on 2026-11-11. The in-app browser pane is too narrow for desktop review.
- After editing JS, reload: the browser caches modules. `tools/check-modules.mjs` needs each export as its own `export const`.
- Stop every server and the headless browser before ending a turn.
