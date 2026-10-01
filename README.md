# Prem Lab

A personal football analytics workbench built on [Understat](https://understat.com) data. It runs on your own computer, keeps everything in a local cache, and is designed to answer questions rather than show dashboards: *who is really better than their results, who is worth scouting, what happens next.*

Unofficial. Not affiliated with or endorsed by Understat.

| Briefing | Scout |
| --- | --- |
| ![Briefing](docs/screens/briefing.jpg) | ![Scout](docs/screens/scout.jpg) |
| **Player** | **Match report** |
| ![Player](docs/screens/player.jpg) | ![Match](docs/screens/match.jpg) |

*The screenshots use the built-in demo world (synthetic players and results), not real data.*

## What it is for

Every page opens with findings, then the evidence.

- **Briefing** – what stands out right now: teams above or below what their chances deserve, players riding luck, the title, top-four and relegation races, the next fixtures, and the players on your shortlist.
- **League** – standings read three ways (results, expected, style), attack against defence, and the table race matchweek by matchweek.
- **Team** – results against chances in every match, percentile profile against the league, rolling form, splits, fixtures with forecasts, squad contributions, and where chances come from.
- **Scout** – filter and rank players by role, minutes, age, club and finishing luck; one-click lenses ("Goal threats", "Unlucky finishers", "Hidden gems", "Young and good"); a table with percentile bars or a map; tick players to compare.
- **Player** – profile against role peers, an exact "how unusual is his finishing" distribution, shot map, season-by-season trend, and statistically similar players (optionally younger, or from other leagues).
- **Compare** – players (percentile dot plot with the differences spelled out) or two teams.
- **Matches** – every match next to the chances behind it, "results that lied", and a match report with xG race, shot map and deserved result.
- **Forecast** – upcoming fixtures, a match lab for any pairing, the season simulated thousands of times, and a walk-forward accuracy check of the model.
- **Shortlist** – players you track, live numbers and your own notes.
- **Data** and **Method** – sync and cache status, a connection check, and plain-language documentation of every number.

### Ideas the numbers are built on

1. Results are noisy; the quality of chances is steadier. Expected points replay every shot of every match.
2. Small samples are treated cautiously: peers need enough minutes, and rates are pulled toward the role average in proportion to how little football stands behind them.
3. Everyone is compared with their own role, so a percentile means the same thing on every page.
4. Luck is measured, not guessed: a player's goals are placed in the exact distribution of goals his shots could have produced.

## Run it

Requires Python 3.11+. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
uv run prem doctor          # can this machine reach and read Understat?
uv run prem sync --leagues EPL --seasons 2025,2026
uv run prem serve           # http://127.0.0.1:8000, opens a browser
```

Just want to look around first? `uv run prem serve --demo` serves a synthetic league that needs no network.

| Command | What it does |
| --- | --- |
| `prem serve` | Run the app. `--demo`, `--offline`, `--port`, `--data-dir`, `--no-open`, `--reload` |
| `prem sync` | Fetch league seasons into the cache (`--leagues EPL,La_liga`, `--seasons 2025,2026`, `--force`) |
| `prem doctor` | Walk the real data path once and report which step fails |
| `prem status` | Show what is cached and how old it is |
| `prem clear --yes` | Delete cached match and player data (your shortlist stays) |

Understat is read at a polite pace (a few requests per second, with retries), so a first sync of several seasons takes minutes. Finished seasons never change and are fetched once. Live seasons refresh when their cache is a few hours old; if a refresh fails you keep seeing the saved data, flagged as stale.

### Configuration

| Variable | Meaning |
| --- | --- |
| `PREM_DATA_DIR` | Where the cache lives (default `<repo>/.prem-data`, or `~/.prem-lab` when installed) |
| `PREM_DEMO=1` | Serve the synthetic demo world |
| `PREM_OFFLINE=1` | Never touch the network; serve what is cached |
| `PREM_TODAY=YYYY-MM-DD` | Pretend today is this date (demo and testing) |

### Ages

Understat has no birthdates, so ages are looked up on Wikidata by name and club. Wikidata has many retired namesakes, so the app is deliberately strict: it only trusts a match that is a plausible footballing age on the date in question, prefers a club the player is at *now* (a club someone left years ago does not count), and refuses to guess for single-word names. Where it cannot be sure the age stays blank, and an age matched by name alone is shown with a `?`.

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

The image serves the app on port 8000 and keeps the cache in the `/data` volume.

## How it is built

```
Understat ──> client (paced, retrying) ──> SQLite payload store ──> repository ──> typed models
                                                                        │
              analytics (players, teams, league, matches, similarity) ◄─┤
              forecast  (ratings, Elo, scorelines, season simulation)  ◄─┤
              insights  (ranked, evidence-backed findings)              ◄─┘
                                        │
                                  workbench (page-shaped views) ──> FastAPI ──> no-build web app
```

- `src/app/data` – the local-first data layer: Understat client, SQLite store, repository (single-flight fetches, stale fallback, offline mode), typed models, a Wikidata birthdate resolver, and a synthetic demo world simulated shot by shot.
- `src/app/analytics`, `src/app/forecast`, `src/app/insights` – the analysis. Everything is a plain function over typed models and is unit tested.
- `src/app/workbench.py`, `src/app/api.py` – one service composes views for the pages; the API is thin and uses one error format.
- `src/app/web` – the frontend: vanilla ES modules on a vendored Preact + htm, hash-routed (the URL carries page state), custom SVG charts, no build step and no runtime network dependencies.

## Tests

```bash
uv run pytest                       # backend: data layer, analytics, forecasts, insights, API
npm install && npm test             # pure frontend helpers (node:test)
uv run prem serve --demo --no-open --port 8765 --today 2027-03-10 &
npm run e2e                         # drives the real UI in headless Chromium against the demo world
npm run shoot -- --routes "/;/scout" --theme light,dark --size 1440x900,390x844   # screenshots + console/overflow checks
```

The Understat endpoint notes that the data layer is based on are in [docs/understat_endpoint_inventory.md](docs/understat_endpoint_inventory.md).

## Licence

MIT. Data belongs to Understat and its sources; respect their terms and keep the request rate low.
