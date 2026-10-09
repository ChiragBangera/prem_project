# Architecture

How Prem Lab keeps its data, turns it into numbers, and gets them onto the screen. The README says what the app does; this says why it is built the way it is, so that a new metric, a new map or a new data source can be added without breaking what is already there.

Five rules shape everything:

1. **Local first.** Everything the app reads is written to one SQLite file and served from there. A page that has loaded once never asks the network again for what it already holds.
2. **Keep the raw data; derive everything else.** The page as the source served it is stored untouched. Every compact form, counter, metric and map is *derived* from it, offline, as often as needed. A new metric or visual never needs a new request.
3. **Declare a number once.** A metric is one declaration (formula, inputs, unit, direction, source, explanation). The table column, the filter, the percentile, the tooltip, the dictionary entry and the lens that uses it are all generated from it.
4. **Unknown is not zero.** A value that cannot be known is blank, and blank is carried honestly through every filter, sort and chart. A link between two sources that is not certain is *not made*.
5. **A failure is routine.** A request can fail, a source can change, a process can be killed. The stored copy keeps being served, the failure is recorded and retried later, and nothing else stops.

## The data flow

```
                                   ┌───────────────────────────────── SQLite (one file) ─────────────────────────────────┐
Understat ──> client ──> repository│ league / team / player / match   (Understat, typed on the way out)                 │
ESPN squad lists ─────────────────>│ roster, dob, fav                  (birthdates, favourite positions)                 │
Wikidata ─────────────────────────>│                                                                                     │
WhoScored ──> fetcher ──> ws_raw ──┼─> ws_silver ──> ws_gold          bronze ─> silver ─> gold (derived, versioned)      │
                                   │ kv: prefs, status, failures, shortlist, markers                                     │
                                   └─────────────────────────────────────────────────────────────────────────────────────┘
                                                      │
        metric registry ─> dataset builders (players, teams) ─> workbench (page-shaped views) ─> FastAPI ─> browser
```

### The store (`app/data/store.py`)

Two tables. `payload(kind, key, fetched_at, source, complete, size, body)` holds one zlib-compressed JSON document per `(kind, key)`; `kv(k, v, updated_at)` holds small values (preferences, run status, failure records, the shortlist, version markers). The store is deliberately dumb: it knows nothing about football. `complete` means "can no longer change" (a finished season, a settled match), which is what lets the repository skip the network for it forever.

| Kind | Key | Holds |
| --- | --- | --- |
| `league` | `EPL:2025` | Understat's league-season: table history, fixtures, the player list |
| `team`, `player` | id | Understat team and player pages |
| `match` | match id | One match's shots and line-ups (scorers, minutes at each position, shot locations) |
| `roster`, `dob`, `fav` | league-season / name | ESPN squad lists with exact birthdates, Wikidata birthdates, favourite positions |
| `ws_raw` | `EPL:2025:1903117` | **Bronze**: the WhoScored match document, exactly as served |
| `ws_silver` | same | **Silver**: compact columnar events, derived from raw |
| `ws_gold` | same | **Gold**: per-player and per-team counters, derived from silver |

## Understat side (`app/data`)

- `understat.py` is the only code that talks to Understat: paced (a few requests a second), retrying, one client per process. `rosters.py` and `wikidata.py` do the same for ESPN squad lists and Wikidata.
- `repository.py` is what the rest of the app asks. It serves fresh hits from memory, fetches misses once (concurrent requests share one upstream call), **falls back to stale data, flagged, when a refresh fails**, never expires what cannot change (finished seasons, settled matches), and refuses the network in offline mode. Freshness windows are in `config.py` (a live league 3 h, a live player page 24 h, an open match 6 h, squad lists 24 h ...).
- `normalize.py` turns raw payloads into the typed models in `models.py`; a payload that does not look right becomes a warning on the model, not an exception three layers up.
- `matchsync.py` fetches every finished match page of a season, resumably. Understat revises a match's numbers for about a day, so a page fetched within 36 hours of kick-off is stored as not final and looked at again later.
- `people.py` is the one place that matches people from another source to Understat players: by the **words of the name and the club**, in a fixed order of passes, each only for people still unmatched, each needing exactly one candidate on both sides. No candidate, or more than one, leaves the person unlinked: a blank is better than another man's birthdate or statistics.

## Event data (`app/events`)

WhoScored's match document is about a megabyte of nested JSON: every pass, tackle, touch and shot with a position, qualifiers, and the line-ups. It is kept whole and everything else is derived.

### Bronze: `raw.py`

The document, compressed (about 100 KB), keyed `LEAGUE:SEASON:GAMEID`, written once. A document is stored only if it looks like a real finished match (events, both teams); anything else is rejected, never half-stored. `import_soccerdata_cache` adopts pages the download tool already wrote, and `reclaim` deletes that tool's duplicates once the store has them.

### Silver: `silver.py` and `schema.py`

One match becomes `info` (kick-off, score, venue ...), `teams` (managers, formations), `players` (line-up position, rating, when he came on and went off) and `ev`: the events as **parallel arrays**, one entry per event in every array. Coordinates are WhoScored's 0-100 in the acting team's attacking direction, stored as integer tenths; the 96 flag qualifiers (`KeyPass`, `Cross`, `Longball`, `BigChance` ...) are two 53-bit words so a test for "is a key pass" is one bit-and; value qualifiers (`Length`, `PassEndX` ...) have their own arrays; related events are resolved to array positions. Silver is a pure function of the raw document and `SILVER_VERSION`.

### Gold: `counters.py`

Per-player and per-team **counters**, which are sums, never rates: a season is the sum of its matches, and every metric (per 90, share, ratio) is a function of summed counters. Every counter is declared in `COUNTERS` with its definition (the dictionary and the tests read that table). Conventions that matter: only the two playing halves count; minutes are scaled so a full match is 90 whatever the stoppage time; "open-play passes" leave out throw-ins, goal kicks, corners and keeper throws, and crosses count on their own.

### Versions and rebuilds: `store.py`

Silver and gold carry the version of the code that made them (`SILVER_VERSION`, `GOLD_VERSION`). **To change a definition, change the code and bump the version.** On the next start (and on the next updater cycle) the store notices (`pending_rebuild`) and rebuilds the changed layer from the layer below, offline (`ensure_current`). Reading a match whose silver or gold is missing or older also rebuilds it on demand. `prem rebuild` does it by hand. A marker in `kv` records the versions every stored match was last brought to, so "nothing changed" costs one key read; the first match ever stored sets it, so a store is never mistaken for out of date just because it grew.

### Season roll-ups and the version token

`EventStore.season(league, season)` adds a season's gold up per player and team, memoised until a match is added. `EventStore.version(league, season)` (match count, newest fetch, silver and gold versions) is the token everything built on events carries; when it changes, so do the datasets that depend on it, and no other cache needs to be told.

### Linking to Understat: `link.py`

WhoScored and Understat use different ids and spell names differently. **Players** are linked with `people.py` (name words + club; the weight is minutes played, so a clash for one Understat player goes to the one who played more). **Matches** are linked by both clubs, a date within a day and the same final score, then, for matches names cannot place, by date and score alone, only when exactly one fixture fits. **Clubs** are named by voting across all matches. Players left unlinked with real minutes are listed (with the candidates considered) on the Data page. Event data is therefore always attached to the right Understat player or left off; it never changes a role score or percentile that exists without it.

### Pitch maps: `maps.py`

Selection and counting, no models. From silver matches it returns small plain structures the browser draws: 24 x 16 grids for touches and defensive actions, capped lists of pass and carry lines (`prog`, `key`, `box`, `f3`, `long`, `cross`, `through`), points for take-ons, defensive actions and keeper actions, and a pass network. Display coordinates are 0-1000 with the attacking direction left to right and the left wing at the top, so a map is a straight plot. Lists are deterministically thinned so a payload stays small. Things that are inferred say so: a pass network's receiver is the next team-mate to touch the ball (the data has none), and carries are estimated from the gaps between a player's touches.

## Metrics (`app/metrics`)

`registry.py` defines three shapes that cover almost everything, each with a constructor: **rate** (a counter per 90 minutes or per game), **ratio** (one counter over another) and **plain**, built with `counter` (a quantity as it is, or any expression of the frame). Metrics are computed for everyone at once over a `Frame` of named numpy arrays, where a missing array reads as NaN (unknown), never zero. `player.py` and `team.py` hold the declarations (about 110 and 100); a declaration carries its key, labels, group, unit, direction (`hib`: higher is better, lower is better, or neither), source and what it needs (`base` totals, `shots` match pages, `events`), formula, and the plain-language `what`, `read` and `caveat`.

- **Ranking.** Rates and ratios are *shrunk* before ranking (empirical Bayes: a value from few minutes or attempts is pulled toward the pool average in proportion to how little stands behind it), so a ten-minute cameo cannot top a leaderboard. The number shown is always the raw value; only the percentile uses the shrunk one.
- **Pools.** A player is ranked against others in his own role group who have played enough (the threshold scales with how far through the season it is). Event metrics have their own, smaller pool: players who have event data. A team is ranked against the other teams of its own league and season.
- **Lenses** (`lenses.py`) are saved questions that are nothing but filter rules over metric values or percentiles, each with a plain explanation. **Views** (`views.py`) are the column presets. **Tags** (`tags.py`) are the profile labels: declared rules on role percentiles, with a "why" generated for each player who earns one.
- **The catalog and the dictionary** (`catalog.py`, `dictionary.py`) are generated from the declarations: what the browser is told (metrics, groups, presets, lenses, tags, roles, positions) and what the Dictionary page prints. They cannot drift from the code because they *are* the code.

## The workbench (`app/workbench`)

`Workbench` (`core.py`) is the running app: it owns the store, the repository, the event store, the enrichment and update machinery and a memo of expensive results, and it starts and stops them. It holds no page logic itself. That lives in small parts, each a subclass of `Part` (`part.py`) that reaches the shared runtime through `wb`:

- **Shared logic**, one module each: `seasons.py` (which league season a request means: `auto` is the newest with enough rounds played; the scope block every page starts with), `ages.py` (dates of birth in order of trust, and how well the sources agree), `links.py` (WhoScored's matches, clubs and players lined up with Understat's), `datasets.py` (the player and team datasets of some league seasons), `shortlist.py`, `diagnostics.py` (the connection check behind `prem doctor`) and `memo.py`.
- **One module per page** in `pages/`: briefing, league, scout (the Scout and Teams explorers), player, team, compare, matches, search, dictionary and data. A page method takes what a route parsed and returns the payload the browser draws.

`api.py` is a thin layer over these: a route parses its query, calls one page method (`wb.team.page(...)`) and returns the result; failures are `AppError`s, answered in one format. Everything the pages need is on `wb`, so a page can be tested without a server.

**The memo.** An expensive result (a dataset, a team's maps, the match summaries) goes through `await wb.memo(key, version, compute)`. The value stored under `key` is returned if it was built for this exact `version`; otherwise it is computed once, in a worker thread, even when several requests ask at the same moment. A version is a tuple of tokens that change when any input does. The whole memo is dropped when the date changes, because some views read it.

## From dataset to screen

`analytics/players.py` and `analytics/teams.py` gather the inputs (Understat's season table, the stored match pages, linked event totals), run the registry, rank, and return **every row** of the chosen league-seasons. The workbench (below) composes page-shaped views and memoises them against version tokens (league data, event versions, match-page epoch, squad-list version), so a result is rebuilt only when something it depends on changed.

**One player, match by match.** `analytics/player_trend.py` computes every metric of the registry for each match of one player's season (`m`), as it stood after each match (`c`, the season to date) and over his last five appearances (`r`). It does so with the same code as the season dataset: each match is a row of counters in the shape `analytics/players.py` adds up (`raw_frame` turns any list of such rows into the frame the registry runs over), so there is no second set of formulas and the last point of `c` is, by construction, the profile number (a test checks this for every metric and every role). A match comes from the stored Understat match page (his roster line and his shots) and, where it exists, from the stored event data of that match; a match with no page is unknown and is left out of every line (`_sum` adds up only what exists), never counted as zero. Opponent strength is the opponent's place in the season table by expected points (top, middle and bottom third), and the same formulas are run over the pooled matches against each third and at home and away. `/api/player/{id}/trend` serves it, memoised against the league data, the event version and the match-page epoch. `SEASON_LONG` in the registry lists the metrics that mean nothing for one match (an age, appearances); the catalog says so as `per_match`, and the profile table shows a trend link only on the others.

`/api/players` and `/api/teams` return every row compactly as `{identity..., v: [values], p: [percentiles]}` with both arrays aligned to one `keys` list: about 800 KB for a league-season, once. **Filtering, sorting, Top N and the map all happen in the browser** on that payload (`web/js/lib/filters.js`, pure and unit tested), so they respond instantly and a new column never needs a request.

The browser state is the URL: `q` (search), `r` role, `pos`, `tag`, `club`, `form`, `min`, `age`, `unk`, `part`, `f` (metric rules like `npxg90>=p80;pass_acc>=0.8`), `lens`, `sort`, `dir`, `top`, `view`, `cols` (a preset or `x:a,b,c`), the map's `mx my mc ms`, `cmp`, and the scope `lg` and `ss`. A view is a link.

**One match, every player.** `analytics/match_players.py` runs the same arithmetic as the trend for the players of one match: each is a row built by `player_trend._match_row` (his Understat line and shots, plus his event counters where the match has event data), and `raw_frame` and the registry run over all of them at once, so a number is what Scout would show for a season of just that match (a test checks this against the trend). Metrics in `SEASON_LONG` are left out, and so is a metric nobody has a value for. A percentile exists only for rates and ratios, against the *season* values of players of the same role in the Scout pool, and not for anyone under 30 minutes: one match's total is not on the scale of a season's. `/api/match/{id}/players` serves it, fetched only when the Deep analytics tab is opened and memoised like the trend. Filtering, sorting and the best-and-weakest marks happen in the browser (`lib/matchplayers.js`).

**Caching on the wire.** An ETag middleware gives every cacheable GET a validator and answers `304` when the browser already holds that body (live endpoints such as `/api/data`, `/api/search` and `/api/shortlist` are never cached). In the browser `lib/api.js` keeps answers in memory and `lib/cache.js` in IndexedDB (stale-while-revalidate: a revisit shows the stored copy at once and refreshes quietly behind it; it works without IndexedDB too, for example in a private window).

## Keeping it current: `sync/autosync.py`

While the app runs, the updater sleeps until the **next due moment** and then runs a cycle. `data/matchclock.py` turns the fixture list (kickoffs in UTC) into those moments: a league table is due shortly after a match's full time (kickoff + 112 minutes), then every 20 minutes until Understat lists the result (2 hours after six hours, never after two days), every 6 hours while a recent match's xG settles, and twice a day otherwise. The same rule is the repository's freshness policy for league data, so page views and the updater agree. `AutoSync.next_wake()` takes the earliest of every tracked season's due moment, a settled match page, a league in its back-off window and the event fetcher's next run (90 seconds while there is a backlog, at most `auto_longest_sleep`, six hours) and says why, which the Data page shows. A cycle:

1. **League seasons**: for every league and every tracked season (this one plus as many previous ones as the preferences say) ask the repository, which decides by its freshness policy whether to touch the network.
2. **Match pages**: fetch only finished matches whose page is missing or not final, within a time budget (five minutes) so a big backlog is worked off over several cycles.
3. **Squad lists** (exact birthdates), through the background enrichment.
4. **Event data**, if enabled and possible (the optional dependency and a browser are present). First the **matchday reads**: every fixture of the event leagues past its full time (and not yet read as finished, up to four hours after kickoff) is read now, by `events sync --targets`, which finds each Understat fixture in WhoScored's match list by kickoff and clubs, reads the page from the site (never soccerdata's cache) and notes what it found under the fixture (`events:matchday:*`); a page still in play is read again ten minutes later. A **followed** match is also read in the half-time break (kickoff + 47 to 62 minutes): a favourite team's (`workbench/favourites.py`, kept in the settings table like the shortlist) or one opened while it is being played (`/api/match/{id}/live?follow=1` records it under `autosync:followed` until four hours after kickoff). Half-time reads go first. Their daily allowance (`budget:matchday:*`) is worked out from the day's fixtures (two per match, ten to spare). Then **catching up**, held while a matchday read is due within fifteen minutes (a run in progress is asked to stop at its next match when one falls due): start the event fetcher as a **separate process** for the first league-season with finished matches still missing, a few dozen matches per run. A separate process keeps a browser crash or a blocked page away from the app; the store is the only thing the two share.
5. **Housekeeping**: adopt pages the download cache holds that the store lacks, rebuild derived layers made by older code.

**Failures.** A failure for a league-season is recorded (`autosync:fail:*`: count, error, time, next try) and retried with a delay that doubles from 5 minutes up to 6 hours, while everything else carries on. A status of "running" that has not been touched for ten minutes reads as **stalled** (the process died); what it had stored stays and the next run skips it. The fetcher stops by itself when the site starts refusing requests.

**Preferences** (`autosync:prefs`): on/off, how many previous seasons to keep complete, whether event data is on, for which leagues and how many seasons. Everything the updater did, what failed and when it will look again is shown on the Data page, with an *Update now* button, and summarised by the pill in the top bar (`/api/meta`).

## The demo world (`app/data/demo`, `app/sync/demofeed.py`)

`prem serve --demo` needs no network: a deterministic world of real club names and fictional players, simulated shot by shot (`sim.py`, `world.py`) and served through `DemoProvider`, which has the same interface as the Understat client. Because the demo has no WhoScored either, `data/demo/events.py` writes a WhoScored-shaped document for each simulated match (passes, defending, duels, set pieces, the simulation's own shots, cards and substitutions, line-ups with ratings, formations), and `DemoEventFeed` stores match pages and these documents in the background, current seasons first, exactly the way the real fetcher would. They go through the **real** parser, counters, linking and maps, so the demo exercises the whole pipeline; nothing in it is real football. The demo has a version (`WORLD_VERSION`): a stored copy made by an older world is cleared on start (your shortlist stays).

## Edge cases and how they are handled

| Situation | Handling |
| --- | --- |
| A request fails or times out | The stored copy is served, flagged stale; the failure is recorded and retried with a growing delay; other work continues |
| A match page is read too soon after the whistle | Stored as not final; looked at again after 36 hours (or the open-match window) |
| The event fetcher is killed mid-run | Status turns "stalled" after ten minutes; matches already stored remain; the next run skips them |
| The app is stopped (Ctrl+C) in the middle of a job | Requests under way get five seconds, the event fetcher is asked to stop like Ctrl+C and killed if it has not after five more; whatever still runs fifteen seconds after the request (a long job in a worker thread, which cannot be interrupted) is abandoned. Every write is transactional and every job resumes, so nothing is lost |
| The source refuses requests | The fetcher stops by itself and records why; nothing else is affected |
| A raw page is unusable | Rejected, never half-stored; counted as "unusable" in the import report |
| A definition changes | Bump the version; derived layers rebuild offline from the layer below; stale layers are also rebuilt on demand when read |
| Two players share a name, or spell it differently | Linked only by name words **and** club with exactly one candidate on each side; otherwise left unlinked and listed |
| A WhoScored match cannot be linked to a fixture | Placed by date and score only when exactly one fixture fits; else listed as unlinked |
| Event data covers only part of a season | Event metrics are per match with data; percentiles use only players with event data; Scout and Teams say how many are covered and the default sort uses the all-data score only when nearly everyone has one |
| A season-long figure needs match pages that are not all stored yet | Blank, never a partial number |
| A player moved clubs mid-season | Seasons and teams are merged for the player; event minutes are credited to the club he played them for |
| A role cannot be known | Taken from minutes at each position, else Understat's favourite position, else inferred from his profile; the source of the role is recorded and shown |
| Goalkeepers | No outfield percentiles or tags; their own metrics and tags |
| Own goals | Count for the other side's score and in the scorers list; they are not shots and never a player's goals |
| Age is unknown, or matched by name alone | Blank; shown with a `?`; never used by filters, similarity or highlights |
| Kick-off times | Kept in UTC and shown in the viewer's time zone |
| Offline mode | The network is never touched; background fetching is a no-op |
| IndexedDB is unavailable | The app works without the browser-side cache |
| The first match is stored in an empty store | The derived-version marker is set at once, so the next start does not rebuild what is already current |

## Adding things

- **A metric.** Add one declaration (`rate`, `ratio` or `counter`) to `metrics/player.py` or `metrics/team.py`, with its group, formula and the `what`, `read` and `caveat` text. If it needs a number the gold layer does not count yet, add the counter to `COUNTERS` in `events/counters.py` and bump `GOLD_VERSION`. Optionally add it to a column preset in `metrics/views.py`. It then appears in the table columns, the metric filter, the map axes, the dictionary and (for players) the player page's metric list. The registry tests check that the declaration is complete and that every input it names exists.
- **A lens.** One `Lens(...)` in `metrics/lenses.py`: rules on metric values or percentiles, and a plain explanation. A test checks that every rule names a real metric.
- **A profile tag.** One `Tag(...)` in `metrics/tags.py`: the role, the rules, the metric that ranks it among a player's tags, and the evidence shown in its "why". It appears in the Profile filter and the dictionary.
- **A pitch-map layer.** Collect it in `events/maps.py` (silver in, small plain structure out), then add a tab in `web/js/ui/maplab.js` and a drawing in `web/js/charts/pitchmaps.js`. Maps read silver, so no new request is ever needed.
- **A page.** A module in `workbench/pages/` with a class that extends `Part`, created in `workbench/core.py`, a thin route in `api.py`, and a page in `web/js/pages`. Logic that several pages need goes next to the core (`seasons.py`, `ages.py`, `links.py`, `datasets.py`), not in a page.
- **A new event qualifier.** Add it to `events/schema.py`, bump `SILVER_VERSION`; the store rebuilds silver from the stored raw pages.

## Tests

`uv run pytest` runs the backend (no test touches the network); `npm test` runs the browser helpers and a static check of every module.

| Area | Files |
| --- | --- |
| Data layer: store, repository, clients, normalizers, rosters, people | `test_data_layer`, `test_clients`, `test_rosters`, `test_people`, `test_match_book` |
| Event pipeline: raw, silver, gold, store and rebuilds, fetching, linking, maps | `test_events_store`, `test_events_counters`, `test_events_fetch`, `test_events_dataset`, `test_events_api`, `test_events_cli`, `test_maps` |
| Metrics: registry consistency, arithmetic, tags, lenses, views, dictionary | `test_metrics_registry`, `test_tags` |
| Datasets and analytics: players, teams, insights, diagnostics | `test_players_analytics`, `test_teams_dataset`, `test_analytics_core`, `test_insights`, `test_diagnostics` |
| Updater, stopping the app, and the demo world | `test_autosync`, `test_cli_stop`, `test_workbench_today`, `test_demo_world`, `test_demo_events` |
| HTTP API end to end on the demo world | `test_api`, `test_birthdates_api` |
| Browser helpers: filters, formatting, charts, router, match cards; every module's imports and names | `tests/js/*.test.mjs` |
| The real UI in headless Chromium (demo world) | `npm run e2e` (`tools/e2e.mjs`) |
