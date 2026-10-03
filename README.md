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

## Run it

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

**Look around first.** The demo world is synthetic, needs no network and nothing to fetch; it fills in its own match pages and event data in the background (the Premier League's within seconds, everything within a few minutes), so every feature, pitch maps included, can be tried:

```bash
uv sync --extra dev
uv run prem serve --demo       # http://127.0.0.1:8000, opens a browser
```

**With real data:**

```bash
uv run prem doctor             # can this machine reach and read Understat?
uv run prem sync --leagues EPL --seasons 2025,2026
uv run prem serve
```

While the app is open it keeps its data current by itself. On a Mac, `tools/prem-lab.command` starts it with a double-click. The other commands, the configuration, the launcher and Docker are in [docs/running.md](docs/running.md).

## What it is for

Every page opens with findings, then the evidence.

- **Briefing**: what stands out right now: teams above or below what their chances deserve, players riding luck, the title race, the latest results and the next fixtures.
- **League** and **Matches**: standings read three ways (results, expected, style) and the table race; every match as a compact card, and for each a full report: the deserved result, the xG race, the shot map and how each side played.
- **Scout** and **Teams**: explorers that list everyone and leave every filter, lens, sort and column to you. Percentiles compare a player only with his own role, a team only with its own league and season.
- **Team** and **Player** pages: a team's overview, style and pitch maps, chances, matches and history; a player's profile against role peers, maps, finishing luck and statistically similar players.
- **Compare**, **Shortlist**, **Dictionary** (every number defined, with its formula and what a typical value looks like) and **Data** (what is stored, what the updater did, what failed).

Press `/` or `Ctrl`/`⌘` + `K` anywhere to search players, teams and pages. The address bar carries a page's state (filters, sort, columns, scope), so any view can be bookmarked or sent to someone. Every page and control is described in [docs/features.md](docs/features.md).

### Ideas the numbers are built on

1. Results are noisy; the quality of chances is steadier. Expected points replay every shot of every match.
2. Small samples are treated cautiously: peers need enough minutes, and rates are pulled toward the role average in proportion to how little football stands behind them.
3. Everyone is compared with their own role, so a percentile means the same thing on every page.
4. Luck is measured, not guessed: a player's goals are placed in the exact distribution of goals his shots could have produced.
5. **Unknown is not zero.** A number that cannot be known (no event data for that match, no known age) is blank, and every filter, sort and chart treats blank as blank.

## Where the data comes from, and what that means

Understat (league tables, shots, expected goals), ESPN's public squad lists and Wikidata (dates of birth) are read from their public endpoints; WhoScored (every event on the pitch) is optional and is read through a real browser. None of them is an official API, and the app is unofficial and for personal use:

- Everything it reads stays on your computer; do not publish it. WhoScored's terms may not allow reading its pages at all, so event data only runs when you switch it on.
- It cannot be hosted with live data. What can be shown publicly is the demo world.
- A source can change under it. The data layer is built for that: a failed response keeps the stored copy, records why, and is retried later; `prem doctor` says which step broke.
- A blank is better than a wrong value: people are linked across sources only on an unambiguous match.

Details, the updater, event data, and how ages are worked out: [docs/data.md](docs/data.md).

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
- `src/app/workbench`: what the app answers with. A small core owns the shared state; shared logic (which season a request means, dates of birth, linking events to Understat, the scouting datasets) and **one module per page** (`pages/`: briefing, league, scout, player, team, compare, matches, search, dictionary, data) sit around it. `src/app/api.py` is a thin layer of routes over those pages and uses one error format.
- `src/app/web`: the frontend: vanilla ES modules on a vendored Preact + htm, hash-routed, custom SVG charts, no build step and no runtime network dependencies. Filtering, sorting, Top N and the map all run in the browser on one payload per page, so they respond instantly.

[docs/architecture.md](docs/architecture.md) explains the layers, versions and rebuilds, the workbench, the updater, caching, how events are linked to Understat, the edge cases handled, and how to add a metric, lens or tag.

## Development

```bash
uv run pytest                       # backend: data layer, event pipeline, metrics, analytics, updater, API
uv run ruff check src tests         # lint
uv run mypy                         # types
npm install && npm test             # frontend: pure helpers, and a static check that every module's imports and names exist (node:test)
uv run prem serve --demo --no-open --port 8765 --today 2027-03-10 &
npm run e2e                         # drives the real UI in headless Chromium against the demo world
```

CI runs all of these on every push. [CONTRIBUTING.md](CONTRIBUTING.md) has the conventions (small, focused commits and how to add things).

## Docker

```bash
docker build -t prem-lab .
docker run --rm -p 127.0.0.1:8000:8000 -v prem-data:/data prem-lab
```

> **The app has no login.** Publish its port on `127.0.0.1` as above, so that only this computer can reach it. `-p 8000:8000` would open it to your whole network, and on the internet anyone could read what it stores. If it must be reachable from elsewhere, put a reverse proxy that asks for a login in front of it. More in [docs/running.md](docs/running.md#docker).

## Licence

MIT. Data belongs to Understat, WhoScored, ESPN, Wikidata and their sources; respect their terms and keep the request rate low.
