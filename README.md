# Prem Lab

A personal football analytics workbench for the five big European leagues, built on [Understat](https://understat.com) (shots and expected goals) and, optionally, WhoScored (every pass, duel and touch). It runs on your own computer, keeps everything it reads in a local database, updates itself while it is open, and is designed to answer questions rather than show dashboards: *who is really better than their results, who is worth scouting, what does this team actually do with the ball.*

Unofficial. Not affiliated with or endorsed by Understat or WhoScored.

| Briefing | Scout |
| --- | --- |
| ![Briefing](docs/screens/briefing.jpg) | ![Scout](docs/screens/scout.jpg) |
| **Matches** | **Team: style and maps** |
| ![Matches](docs/screens/matches.jpg) | ![Team maps](docs/screens/team-maps.jpg) |
| **Player** | **Data dictionary** |
| ![Player](docs/screens/player.jpg) | ![Dictionary](docs/screens/dictionary.jpg) |

*The screenshots use the built-in demo world (synthetic players, results and events), not real data.*

## What it is for

Every page opens with findings, then the evidence.

- **Briefing**: what stands out right now: teams above or below what their chances deserve, players riding luck, the title race, the latest results with who scored and how the chances split, the next fixtures with each side's position, form and chance difference, the biggest movers, and your shortlist.
- **League**: standings read three ways (results, expected, style), attack against defence, and the table race matchweek by matchweek.
- **Matches**: every match of a matchweek as a compact card: big score, scorers and minutes, possession and shots, the chances behind the result, and a flag on the ones that went against them. Open one for the full report: the deserved result, xG race, shot map, head to head, the best chances, and (with event data) how each side played: possession, passing, shape.
- **Scout**: find players by what they do (below).
- **Teams**: the same explorer for teams: every team measure, ranked within its own league and season.
- **Team page**: **Overview** (every match as chances against results, what is next, how they play), **Players** (the squad, with per-player metrics), **Style & maps** (a style profile and pitch maps), **Chances** (where chances come from and where they are allowed, one chart with toggles), **Matches** (match by match, and whether having the ball helps) and **History** (seasons side by side).
- **Player page**: Profile against role peers (every metric is searchable), pitch **Maps**, a **Match log**, **Finishing and shots** (an exact "how unusual is his finishing" distribution and a shot map), **Seasons** and statistically **Similar players**.
- **Compare**: players (a percentile dot plot with the differences spelled out) or two teams (numbers, style, trend, meetings).
- **Shortlist**: players you track, live numbers and your own notes.
- **Dictionary**: every raw field and every derived number: what it is, its formula, where it comes from, what it needs, how to read it, and what a typical value looks like. Plus every event type and qualifier, every profile tag and lens in words.
- **Guide** and **Data**: where to find things, and what is stored, what the updater did, what failed, and how complete each layer is.

Press `/` or `Ctrl`/`⌘` + `K` anywhere to search players, teams and pages. The address bar carries the page's state (filters, sort, columns, scope), so any view can be bookmarked or sent to someone.

### Scout and Teams: nothing is pre-selected

Both pages list **everyone** until you narrow them down, and every control is yours:

- **Filters add up**, each one independent. For players: role, exact position, club, minutes, age, playing time and **Profile** (the tags below). For teams: formation. For both, a **metric filter**: "keep those whose value, or percentile, is above or below a limit" on any of the ~110 player (or ~100 team) metrics. Each active filter shows as a chip you can remove.
- **Lenses are quick filters, explained.** "Goal threats", "Ball winners", "Unlucky finishers", "Young and good", "Ever-present" (19 for players), "High press", "Possession-dominant", "Set-piece reliant" (13 for teams) ... A lens is nothing but a set of filter rules; point at one and the page lists exactly which rules it applies and which metrics it looks at. A lens never changes your sort, columns or other filters.
- **Profile tags** describe how a player plays: Poacher, Complete forward, Chance creator, Playmaker, Ball-playing defender, Aerial dominator, Sweeper-keeper ... 27 in all. Each is a short rule on role percentiles that you can read in the Dictionary, and each tag shown on a player says why he earned it.
- **The table is yours too.** Columns come in groups (shooting, creating, passing, defending ...). Pick a ready-made set (Overview, Attacking, Creating, Passing, Carrying, Defending, Duels, Goalkeeping, Set pieces, Discipline) or choose any of the metrics as a column. Click any heading to sort; blanks always sort last, never as zero.
- **Top N** (10, 20, 50, 100 or your own number) applies to the table **and** the map, so "the ten best ball-winners among defenders under 23" is two clicks.
- **The map** plots any metric against any other, coloured by role (players) or league, sized by minutes, with outliers fenced so one cameo cannot flatten the picture.
- A short **read of the ranking** (who leads, how far ahead, how the top group differs from the rest) sits above the table, and a note appears when a rate is led by players with very few minutes.
- Percentiles always compare a player **only with his own role** (a team only with its own league and season), shrunk toward the average in proportion to how little football stands behind them.
- Tick up to four players to compare, export what you see as CSV, or copy a link to exactly this view.

### Pitch maps (event data)

With event data stored, every player and team has maps drawn from the real positions of every touch: **Touches** (heat), **Passes** (progressive, key passes, into the box, long balls, crosses, through balls), **Pass network** (average positions and the strongest links), **Defending** (tackles, interceptions, recoveries, clearances, aerials), **Carries**, **Take-ons**, **Shots** and **Goalkeeper** actions, filterable by home/away and by match. All maps attack left to right with the left wing at the top. Where no events are stored a map says so rather than drawing nothing.

### Ideas the numbers are built on

1. Results are noisy; the quality of chances is steadier. Expected points replay every shot of every match.
2. Small samples are treated cautiously: peers need enough minutes, and rates are pulled toward the role average in proportion to how little football stands behind them.
3. Everyone is compared with their own role, so a percentile means the same thing on every page.
4. Luck is measured, not guessed: a player's goals are placed in the exact distribution of goals his shots could have produced.
5. **Unknown is not zero.** A number that cannot be known (no event data for that match, no known age) is blank, and every filter, sort and chart treats blank as blank.

## Run it

Requires Python 3.11+. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
uv run prem doctor          # can this machine reach and read Understat?
uv run prem sync --leagues EPL --seasons 2025,2026
uv run prem serve           # http://127.0.0.1:8000, opens a browser
```

Just want to look around first? `uv run prem serve --demo` serves a synthetic world that needs no network. It fills in its own match pages and event data in the background (current seasons first: the Premier League's is there within seconds, everything within a few minutes), so every feature, including the pitch maps, can be tried.

On a Mac, `tools/prem-lab.command` starts the app with a double-click: it opens your browser when the app is ready, and Ctrl+C (or closing its window) stops the app, within a few seconds even if the updater is in the middle of something. If the app is already running somewhere else (another window, or in the background) the launcher just opens it and offers to stop it: Ctrl+C only reaches what runs in the window it is pressed in, so press S there instead. Put a link to it on the Desktop with `ln -s "$PWD/tools/prem-lab.command" ~/Desktop/"Prem Lab.command"`. It uses port 8010 (`PREM_PORT=8011` changes that) and `PREM_DEMO=1` makes it start the demo world. The launcher wears the Prem Lab icon (`tools/icon/`); macOS keeps a file's icon beside it rather than in it, so Git does not carry it: after a fresh clone, or a pull that replaces the launcher, run `tools/set-icon.sh` to put it back.

| Command | What it does |
| --- | --- |
| `prem serve` | Run the app. `--demo`, `--offline`, `--port`, `--data-dir`, `--today`, `--no-open`, `--reload` |
| `prem sync` | Fetch league seasons, and their club squad lists (exact birthdates), into the local store (`--leagues EPL,La_liga`, `--seasons 2025,2026`, `--force`) |
| `prem doctor` | Walk the real data path once and report which step fails |
| `prem status` | Show what is stored and how old it is |
| `prem events sync` | Fetch event data from WhoScored (see below). `--league`, `--seasons`, `--limit`, `--pause`, `--browser`, `--visible` |
| `prem events status` | Show how many event matches are stored per league season |
| `prem events import` | Adopt event pages the download cache already holds (offline), then derive from them |
| `prem events reclaim --yes` | Delete the download cache's duplicate event pages (the store keeps every match) |
| `prem rebuild` | Bring every derived event layer up to date with the current definitions, from the stored pages, with no network |
| `prem clear --yes` | Delete stored league, match and player data (your shortlist stays; event data stays unless you add `--events`) |

The server writes what it does and any error, with its traceback, to `<data dir>/logs/server.log` (rotated; the event fetcher keeps its own logs in the same folder), so a problem seen in the browser can be traced even when the server was started in the background.

### Configuration

| Variable | Meaning |
| --- | --- |
| `PREM_DATA_DIR` | Where the local store lives (default `<repo>/.prem-data`, or `~/.prem-lab` when installed) |
| `PREM_DEMO=1` | Serve the synthetic demo world |
| `PREM_DEMO_EVENTS=0` | In the demo world, skip the synthetic event data (default: generated in the background) |
| `PREM_OFFLINE=1` | Never touch the network; serve what is stored |
| `PREM_AUTO=0` | Do not update data in the background (default: on, except in demo and offline modes) |
| `PREM_AUTO_EVENTS=0/1` | Whether the background updater may also run the event fetcher (default: on once event data has been used and its dependencies are installed) |
| `PREM_TODAY=YYYY-MM-DD` | Pretend today is this date (demo and testing) |

## Your data stays up to date by itself

While the app is open, a background **cycle** runs every 15 minutes (every 90 seconds while there is a backlog). It looks for league seasons whose data may have changed and for **newly finished matches**, and fetches only those:

- A **finished season** is never fetched again. A **live season** refreshes around matchdays. A **match page** is fetched once, after Understat has settled its numbers, and kept for good.
- Work is paced and bounded: a few requests a second, with retries, and a time budget per cycle so a big backlog is worked off over several cycles instead of one long burst.
- **A failed request never stops anything else.** The stored copy keeps being served (flagged as stale), the failure is recorded with its reason, and it is retried later with a growing delay (5 minutes, doubling, up to 6 hours).
- Everything is **resumable and idempotent**: closing the app mid-cycle loses nothing, and the next cycle carries on from what the store holds.
- The **Data** page shows what is on your computer (per league season: matches played, match pages, event matches, squad lists, when it was updated), what the last cycle did, what is failing and when it will be retried, and has the controls: pause updating, how many previous seasons to keep complete, which leagues and seasons to fetch event data for, and an **Update now** button. The top bar carries a small status pill.

Once a page has loaded it is served from the local database; nothing is requested twice. In the browser, answers are also kept (in IndexedDB) and revalidated with ETags, so reopening a page is instant and the data refreshes quietly behind it.

### Event data (optional): passes, duels, tackles, carries and maps

Understat only records shots. An optional second source, WhoScored (read through the [`soccerdata`](https://soccerdata.readthedocs.io) package), supplies every event on the pitch, which adds passing, carrying, defending and duel metrics, possession, pressing, and the maps above. Nothing else in the app depends on it.

```bash
uv run --extra events prem events sync --league EPL --seasons 2025     # or switch it on from the Data page and let the updater do it
uv run prem events status
```

- **Slow, once.** A match takes about 15 seconds, so a full league season is roughly two hours. Every match is stored in the local database as soon as it is read and never fetched again. Stop it any time (Ctrl+C) and run the same command to carry on; later runs only fetch matches played since. From the Data page the updater does the same in a separate process, a few dozen matches at a time.
- **The raw page is kept**, exactly as served (about 100 KB compressed), and everything else is derived from it offline: the compact event arrays, the counters, every metric and map. Improving a definition or adding a metric or a map never needs a new request; `prem rebuild` (or the next start) re-derives from what is stored. See [docs/architecture.md](docs/architecture.md).
- **Needs a browser.** Chrome, Chromium, Brave or Edge must be installed (found automatically; `--browser PATH` overrides). Add `--visible` if the site blocks the hidden window.
- **Safe by design.** WhoScored players and matches are matched to Understat's by name, club, date and score and **left out rather than guessed**; the Data page lists who could not be matched. Existing role scores and percentiles are never changed by event data: the all-data score is a separate column.
- **Personal use only.** It reads a public website, which that site's terms may not allow, so it only runs when you start it and keeps what it reads on your own computer. Do not publish the data.

### Ages

Understat has no birthdates, so ages come from two places, in this order:

1. **Club squad lists (ESPN's public JSON feed).** Each club's squad for a season lists its players with their exact date of birth, goalkeepers included. A player is matched to Understat by the *words of his name and his club*, never by a looser guess (spelling variants such as "Vitalii" / "Vitaliy" are handled, and "Gabriel" on Understat is matched to "Gabriel dos Santos Magalhães" only when he is the one unmatched candidate at that club). In a check against WhoScored's own ages for the Premier League, all 466 players that could be compared agreed. It is about 20 requests for a league and season, made in the background the first time you open Scout (or by `prem sync`), stored for good for finished seasons, and refreshed daily for the current one. A birthdate belongs to the player, not the season, so every stored list is used in every view: someone who has since moved on is found on the list of the club he went to. If the feed has almost nothing for a season (it has one player per club for Serie A 2023, for example) the Data page marks that season as sparse, asks again after a week, and ages there come from the other lists and from Wikidata.
2. **Wikidata, for the players a squad list leaves out** (a few per cent: club-name aliases, rarely a first name written differently). Wikidata has many retired namesakes, so the app is deliberately strict: it only trusts a match that is a plausible footballing age on the date in question, prefers a club the player is at *now* (a club someone left years ago does not count), and refuses to guess for single-word names. Where it cannot be sure the age stays blank, and an age matched by name alone is shown with a `?` but never decides anything: the age filter, similar-player searches and the young-talent highlights treat it as unknown.

The Scout age filter hides players with no sure age (the Age menu says how many, and can show them). The Data page shows, per league and season, how many players the squad lists matched, who is still unknown, and any player where Wikidata, sure of the club, disagrees. Both feeds are public but undocumented and used for personal use only; if one is unreachable, ages simply stay as they were.

If an age is wrong or missing, correct it yourself in `<data dir>/birthdates.json` (read at start-up). Use `"Name"` or, to tell two players of the same name apart, `"Name|Club"`:

```json
{ "Sávio": "2004-04-10", "Pablo Ibáñez|Alaves": "1998-08-03" }
```

### Managers

Understat has no manager data. To split a team's season by manager, add your own stints to `<data dir>/managers.json` (same shape as [`src/app/data/managers.json`](src/app/data/managers.json)); they are merged in and appear on the Team page.

### Docker

```bash
docker build -t prem-lab .
docker run --rm -p 8000:8000 -v prem-data:/data prem-lab
```

The image serves the app on port 8000 and keeps the store in the `/data` volume. (Event fetching needs a browser, so it is not available in the image.)

## How it is built

```
Understat ─┐                                   ┌─ bronze: the raw page, exactly as served ──┐
ESPN       ├─> clients (paced, retrying) ─> SQLite store ─ silver: compact typed events    ├─> metric registry ─> datasets ─> workbench ─> FastAPI ─> web app
Wikidata   │                                   └─ gold: per-match counters, versioned ──────┘      (one declaration       (every row, every metric
WhoScored ─┘                                                                                         per number)          and percentile)
```

- `src/app/data`: the local-first data layer: Understat client, SQLite store, repository (single-flight fetches, stale fallback, offline mode), typed models, squad-list and Wikidata birthdate resolvers, strict name matching, and a synthetic demo world simulated shot by shot.
- `src/app/events`: the event pipeline: bronze (raw page), silver (compact columnar events), gold (counters), pitch-map extraction, and linking to Understat.
- `src/app/metrics`: the **metric registry**. Every number in the app (about 110 for players, 100 for teams) is declared once: its formula, inputs, unit, direction, source and explanation. The catalog the browser reads, the data dictionary, the lenses, the column presets and the profile tags are all generated from it.
- `src/app/analytics`, `src/app/insights`: the analysis. Plain functions over typed models, unit tested; insights turn them into ranked, evidence-backed findings.
- `src/app/sync`: the background updater and the demo world's data feed.
- `src/app/workbench.py`, `src/app/api.py`: one service composes views for the pages; the API is thin and uses one error format.
- `src/app/web`: the frontend: vanilla ES modules on a vendored Preact + htm, hash-routed, custom SVG charts, no build step and no runtime network dependencies. Filtering, sorting, Top N and the map all run in the browser on one payload per page, so they respond instantly.

[docs/architecture.md](docs/architecture.md) explains the layers, versions and rebuilds, the updater, caching, how events are linked to Understat, the edge cases handled, and how to add a metric, lens or tag.

## Tests

```bash
uv run pytest                       # backend: data layer, event pipeline, metrics, analytics, updater, API
npm install && npm test             # frontend: pure helpers, and a static check that every module's imports and names exist (node:test)
uv run prem serve --demo --no-open --port 8765 --today 2027-03-10 &
npm run e2e                         # drives the real UI in headless Chromium against the demo world
npm run shoot -- --routes "/;/scout" --theme light,dark --size 1440x900,390x844   # screenshots + console/overflow checks
```

The Understat endpoint notes that the data layer is based on are in [docs/understat_endpoint_inventory.md](docs/understat_endpoint_inventory.md).

## Licence

MIT. Data belongs to Understat, WhoScored, ESPN, Wikidata and their sources; respect their terms and keep the request rate low.
