# Running it

Requires Python 3.11+. With [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev
uv run prem doctor          # can this machine reach and read Understat?
uv run prem sync --leagues EPL --seasons 2025,2026
uv run prem serve           # http://127.0.0.1:8000, opens a browser
```

Just want to look around first? `uv run prem serve --demo` serves a synthetic world that needs no network. It fills in its own match pages and event data in the background (current seasons first: the Premier League's is there within seconds, everything within a few minutes), so every feature, including the pitch maps, can be tried.

## On a Mac: the launcher

`tools/prem-lab.command` starts the app with a double-click: it opens your browser when the app is ready, and Ctrl+C (or closing its window) stops the app, within a few seconds even if the updater is in the middle of something. If the app is already running somewhere else (another window, or in the background) the launcher just opens it and offers to stop it: Ctrl+C only reaches what runs in the window it is pressed in, so press S there instead. Put a link to it on the Desktop with `ln -s "$PWD/tools/prem-lab.command" ~/Desktop/"Prem Lab.command"`. It uses port 8010 (`PREM_PORT=8011` changes that) and `PREM_DEMO=1` makes it start the demo world. The launcher wears the Prem Lab icon (`tools/icon/`); macOS keeps a file's icon beside it rather than in it, so Git does not carry it: after a fresh clone, or a pull that replaces the launcher, run `tools/set-icon.sh` to put it back.

## Commands

| Command | What it does |
| --- | --- |
| `prem serve` | Run the app. `--demo`, `--offline`, `--port`, `--data-dir`, `--today`, `--no-open`, `--reload` |
| `prem sync` | Fetch league seasons, and their club squad lists (exact birthdates), into the local store (`--leagues EPL,La_liga`, `--seasons 2025,2026`, `--force`) |
| `prem doctor` | Walk the real data path once and report which step fails |
| `prem status` | Show what is stored and how old it is |
| `prem events sync` | Fetch event data from WhoScored (see [data.md](data.md#event-data-optional-passes-duels-tackles-carries-and-maps)). `--league`, `--seasons`, `--limit`, `--pause`, `--browser`, `--visible` |
| `prem events status` | Show how many event matches are stored per league season |
| `prem events import` | Adopt event pages the download cache already holds (offline), then derive from them |
| `prem events reclaim --yes` | Delete the download cache's duplicate event pages (the store keeps every match) |
| `prem rebuild` | Bring every derived event layer up to date with the current definitions, from the stored pages, with no network |
| `prem clear --yes` | Delete stored league, match and player data (your shortlist stays; event data stays unless you add `--events`) |

The server writes what it does and any error, with its traceback, to `<data dir>/logs/server.log` (rotated; the event fetcher keeps its own logs in the same folder), so a problem seen in the browser can be traced even when the server was started in the background.

## Configuration

| Variable | Meaning |
| --- | --- |
| `PREM_DATA_DIR` | Where the local store lives (default `<repo>/.prem-data`, or `~/.prem-lab` when installed) |
| `PREM_DEMO=1` | Serve the synthetic demo world |
| `PREM_DEMO_EVENTS=0` | In the demo world, skip the synthetic event data (default: generated in the background) |
| `PREM_OFFLINE=1` | Never touch the network; serve what is stored |
| `PREM_AUTO=0` | Do not update data in the background (default: on, except in demo and offline modes) |
| `PREM_AUTO_EVENTS=0/1` | Whether the background updater may also run the event fetcher (default: on once event data has been used and its dependencies are installed) |
| `PREM_TODAY=YYYY-MM-DD` | Pretend today is this date (demo and testing) |

## Docker

```bash
docker build -t prem-lab .
docker run --rm -p 127.0.0.1:8000:8000 -v prem-data:/data prem-lab
```

The image serves the app on port 8000 and keeps the store in the `/data` volume. (Event fetching needs a browser, so it is not available in the image.)

> **There is no login.** Inside the container the app listens on every interface (that is how the published port reaches it), so what protects it is where you publish the port. The command above publishes it on `127.0.0.1` only: reachable from this computer and nothing else. Do not use `-p 8000:8000` (that opens it to your whole network) and do not put it on the internet as it is: anyone who can reach it can read everything it stores and start fetches from your connection. If it has to be reachable from elsewhere, put a reverse proxy that asks for a login in front of it.
