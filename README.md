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

## Get started

Prem Lab is a small web app that runs on your own computer: you start it, it opens in your browser, and everything it reads is kept in a folder on your disk. There is nothing to sign up for and nothing to host. It works on Windows, macOS and Linux.

**You need**

- **Python 3.11 or newer** (check with `python3 --version`; on Windows `py --version`). [uv](https://docs.astral.sh/uv/), the installer recommended below, finds or downloads a suitable Python by itself, so with uv you do not have to install Python at all.
- **The code**, through [Git](https://git-scm.com/downloads) or the green **Code → Download ZIP** button at the top of this page.
- **A web browser**, and an internet connection for real data (the demo needs none once it is installed).
- **Disk space**: about 100 MB for the install, then a few MB for each league season of data. The optional event data is far bigger (about 100 KB for every match).

### 1. Get the code

```bash
git clone https://github.com/ChiragBangera/prem_project.git
cd prem_project
```

Without Git, download the ZIP, unzip it and open a terminal in the folder it made (on Windows: open the folder in File Explorer, type `cmd` in the address bar and press Enter).

### 2. Install it

Do **one** of the two, inside the `prem_project` folder.

**With uv (recommended).** If you do not have uv yet, install it with one of these lines and then open a **new** terminal, so that it is found. On macOS and Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows, in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

(`brew install uv`, `winget install --id=astral-sh.uv -e` and `pip install uv` work as well.) Then:

```bash
uv sync
```

**Without uv** (Python and pip only). This makes a private environment in a folder called `.venv`. On macOS and Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

On Windows, in Command Prompt or PowerShell:

```bat
py -m venv .venv
.venv\Scripts\pip install -e .
```

The `prem` commands below are written for uv (`uv run prem …`). If you installed without uv, replace `uv run prem` with `.venv/bin/prem` (Windows: `.venv\Scripts\prem`), for example `.venv/bin/prem serve --demo`.

### 3. Look around with the demo

```bash
uv run prem serve --demo
```

The terminal prints the address, `http://127.0.0.1:8000/`, and your browser opens on it. The demo is a synthetic world (made-up players, results and events), so it needs no network and nothing to fetch. It fills in its own match pages and event data in the background, the Premier League's within seconds and everything within a few minutes, so every feature, the pitch maps included, can be tried.

Press `Ctrl`+`C` in the terminal to stop it.

### 4. Use real data

```bash
uv run prem doctor
uv run prem serve
```

`prem doctor` tries each source (Understat, ESPN and Wikidata) with a few small requests and says what worked and, if something did not, which step and why. `prem serve` then runs the app on real data: a page fetches what it needs the first time you open it (a few seconds), the app keeps it, and while it is open it keeps its data current by itself.

To fetch ahead of time, for example before a journey, name the leagues and seasons:

```bash
uv run prem sync --leagues EPL,La_liga --seasons 2025,2026
```

The leagues are `EPL`, `La_liga`, `Bundesliga`, `Serie_A` and `Ligue_1`, and a season is named by the year it starts (2025 is 2025/26). With no options, `sync` fetches the Premier League's current season.

### One-click start (optional)

Instead of typing, double-click a launcher. Each one starts the app on port 8010, opens your browser when it is ready, and stops the app when you close its window or press `Ctrl`+`C`. If the app is already running they just open it. On Linux, use the terminal commands above.

- **Windows:** double-click `tools\prem-lab.bat`. To get a **Prem Lab** shortcut with the app's icon on your Desktop, run this once in the project folder (again if you move the folder):

  ```powershell
  powershell -ExecutionPolicy Bypass -File tools\make-windows-shortcut.ps1
  ```

- **macOS:** double-click `tools/prem-lab.command`. Run `tools/set-icon.sh` once to give it the Prem Lab icon (macOS keeps an icon beside a file, not inside it, so a download does not carry it), and put a link to it on your Desktop with `ln -s "$PWD/tools/prem-lab.command" ~/Desktop/"Prem Lab.command"`.

Both work whichever way you installed. To start the demo world from a launcher, run `tools\prem-lab.bat --demo` in a terminal (Windows), or `PREM_DEMO=1 tools/prem-lab.command` (macOS). More in [docs/running.md](docs/running.md).

### Stop, start again, update

- **Stop:** press `Ctrl`+`C` in the terminal where it runs, or close that window.
- **Start again:** run the same `serve` command (or double-click the launcher). Nothing needs installing again.
- **Update:** in the project folder run `git pull`, then the install command again (`uv sync`, or `.venv/bin/pip install -e .`). Your data is kept. If you downloaded the ZIP, download it again and move your `.prem-data` folder into the new one.
- **Where the data is:** in the folder `.prem-data` inside the project, which Git ignores. `--data-dir` or the `PREM_DATA_DIR` variable put it somewhere else, `uv run prem status` shows what is stored, and `uv run prem clear --yes` deletes the stored data (your shortlist stays).
- **Remove it:** delete the project folder.

### If something goes wrong

| What you see | What to do |
| --- | --- |
| `Prem Lab could not start: port 8000 is probably in use` | Prem Lab may already be running (open `http://127.0.0.1:8000`), or another program holds the port. Choose another: `uv run prem serve --port 8001`. |
| `uv`, `python3` or `py` "not found" or "not recognized" | Open a new terminal after installing it. For Python from python.org, tick "Add python.exe to PATH" in its installer. Or install uv, which brings its own Python. |
| `prem` "not recognized" or "command not found" | Start it with `uv run prem …` or `.venv/bin/prem …` as above; a bare `prem` works only inside an activated environment. |
| `requires a different Python` | Your Python is older than 3.11. Use uv, or install a newer Python. |
| `ensurepip is not available` (Debian, Ubuntu) | `sudo apt install python3-venv`, or use uv. |
| Pages are empty, or `prem doctor` shows `FAIL` | The sources are public websites that can be slow, change, or refuse a request. The app keeps what it already stored and tries again later; `prem doctor` names the step that broke. A blank number means "unknown", never zero. |
| Double-clicking a launcher does nothing | Run the command from step 3 or 4 in a terminal instead; it does the same, and any message stays on the screen. |
| The browser did not open | Open the address the terminal printed, `http://127.0.0.1:8000/`. |

The server also writes everything it does, with errors and their tracebacks, to `logs/server.log` in the data folder.

### Optional: event data

By default the app knows shots and expected goals, which is what Understat records. A second, optional source adds every pass, duel, tackle and carry: the passing and defending numbers, possession, pressing and the pitch maps. It needs Chrome, Chromium, Brave or Edge on your computer, takes about two hours once per league season, and is for personal use only. See [docs/data.md](docs/data.md#event-data-optional-passes-duels-tackles-carries-and-maps) for how to switch it on.

### Optional: Docker

If you have Docker and would rather not install Python:

```bash
docker build -t prem-lab .
docker run --rm -p 127.0.0.1:8000:8000 -v prem-data:/data prem-lab
```

Then open `http://127.0.0.1:8000` yourself (Docker cannot open your browser). Add `-e PREM_DEMO=1` to the `docker run` line for the demo world. Your data lives in the `prem-data` volume. Event fetching needs a browser, so it is not available in the image.

> **The app has no login.** Publish its port on `127.0.0.1` as above, so that only this computer can reach it. `-p 8000:8000` would open it to your whole network, and on the internet anyone could read what it stores. If it must be reachable from elsewhere, put a reverse proxy that asks for a login in front of it. More in [docs/running.md](docs/running.md#docker).

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
uv sync --extra dev                 # the test and lint tools, on top of the install above
uv run pytest                       # backend: data layer, event pipeline, metrics, analytics, updater, API
uv run ruff check src tests         # lint
uv run mypy                         # types
npm install && npm test             # frontend: pure helpers, and a static check that every module's imports and names exist (node:test)
uv run prem serve --demo --no-open --port 8765 --today 2027-03-10 &
npm run e2e                         # drives the real UI in headless Chromium against the demo world
```

CI runs all of these on every push. [CONTRIBUTING.md](CONTRIBUTING.md) has the conventions (small, focused commits and how to add things).

## Licence

MIT. Data belongs to Understat, WhoScored, ESPN, Wikidata and their sources; respect their terms and keep the request rate low.
