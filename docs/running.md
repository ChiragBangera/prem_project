# Running it

Requires Python 3.11+. The [README](../README.md#get-started) walks through downloading and installing it step by step, on Windows, macOS and Linux, with or without [uv](https://docs.astral.sh/uv/). In short, with uv:

```bash
uv sync                     # add --extra dev for the tests and linters
uv run prem doctor          # can this machine reach and read Understat, ESPN and Wikidata?
uv run prem sync --leagues EPL --seasons 2025,2026
uv run prem serve           # http://127.0.0.1:8000, opens a browser
```

Without uv, make a `.venv` with `python3 -m venv .venv` and `.venv/bin/pip install -e .` (Windows: `py -m venv .venv` and `.venv\Scripts\pip install -e .`), and start it with `.venv/bin/prem` (Windows: `.venv\Scripts\prem`) wherever uv's `uv run prem` is written.

Just want to look around first? `uv run prem serve --demo` serves a synthetic world that needs no network. It fills in its own match pages and event data in the background (current seasons first: the Premier League's is there within seconds, everything within a few minutes), so every feature, including the pitch maps, can be tried.

## On a Mac: the launcher

`tools/prem-lab.command` starts the app with a double-click: it opens your browser when the app is ready, and Ctrl+C (or closing its window) stops the app, within a few seconds even if the updater is in the middle of something. If the app is already running somewhere else (another window, or in the background) the launcher just opens it and offers to stop it: Ctrl+C only reaches what runs in the window it is pressed in, so press S there instead. Put a link to it on the Desktop with `ln -s "$PWD/tools/prem-lab.command" ~/Desktop/"Prem Lab.command"`. It uses port 8010 (`PREM_PORT=8011` changes that) and `PREM_DEMO=1` makes it start the demo world. It runs the app with uv if that is installed, otherwise with the project's `.venv` (made by `python3 -m venv .venv`), otherwise with a `prem` on the PATH. Before it starts the app, the launcher brings the project up to date, like `git pull`, and lists what is new. It does this only when it is safe and never at the cost of starting: it skips the update when there is no Git (a downloaded ZIP), the copy is not on a branch that follows one on GitHub, tracked files have been changed here, or this copy has commits of its own that GitHub's does not; it allows the fetch 10 seconds; and offline it starts the version you have. When the update changes `pyproject.toml` or `uv.lock` it updates the packages too: `uv run` does that by itself, except for the event data packages, which it keeps with `uv sync --inexact --extra events` (a plain `uv sync` would remove them); a `.venv` made with pip gets `pip install -e .` again. If the update replaced the launcher, it puts the icon back on it (see below) and starts the new one instead. `PREM_NO_UPDATE=1` skips all this. The launcher wears the Prem Lab icon (`tools/icon/`); macOS keeps a file's icon beside it rather than in it, so Git does not carry it: after a fresh clone, or a `git pull` of your own that replaces the launcher, run `tools/set-icon.sh` to put it back (the launcher's own update does that itself).

## On Windows: the launcher and the shortcut

`tools\prem-lab.bat` starts the app with a double-click: it opens your browser when the app is ready, and Ctrl+C (or closing its window) stops the app. If the app is already running on that port it only opens it. It runs the project's own environment (`.venv`, made by `uv sync` or by `py -m venv .venv`) if there is one, otherwise `uv run prem`, otherwise a `prem` on the PATH. Like the Mac's, it first brings the project up to date (`tools\prem-update.ps1`, with the same rules; a `.venv` made with pip is installed again after every update, made with uv it gets `uv sync --inexact` when the packages changed). cmd reads a `.bat` file line by line while running it, so the update and a restart of the launcher sit in a single block: once the update may have replaced the file, nothing more is read from it. `PREM_NO_UPDATE=1` skips the update. Whatever you type after the file name goes to `prem serve`, so `tools\prem-lab.bat --demo` starts the demo world. It uses port 8010 (`PREM_PORT=8011` changes that), and `PREM_NO_OPEN=1` stops it opening the browser.

A `.bat` file cannot carry an icon, but a shortcut can. This puts a **Prem Lab** shortcut with the Prem Lab icon (`tools\icon\prem-lab.ico`, several sizes from 16 to 256 pixels) on your Desktop:

```powershell
powershell -ExecutionPolicy Bypass -File tools\make-windows-shortcut.ps1
```

Add `-Folder "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"` to put it in the Start menu instead. The shortcut points at the launcher inside this folder, so run the script again if you move the folder. Unlike the Mac's, the Windows icon is part of the shortcut, so a fresh clone or a pull does not lose it. The Windows job in CI installs both ways, starts the demo through the launcher, opens the shortcut, and checks that Windows can read every size of the icon.

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
| `PREM_BROWSER` | Path of the Chrome, Chromium or Brave the event fetcher drives, for one that is installed where it is not found automatically (Edge does not work) |

## Docker

```bash
docker build -t prem-lab .
docker run --rm -p 127.0.0.1:8000:8000 -v prem-data:/data prem-lab
```

The image serves the app on port 8000 and keeps the store in the `/data` volume. Add `-e PREM_DEMO=1` to the `docker run` line to serve the demo world. (Event fetching needs a browser, so it is not available in the image.)

> **There is no login.** Inside the container the app listens on every interface (that is how the published port reaches it), so what protects it is where you publish the port. The command above publishes it on `127.0.0.1` only: reachable from this computer and nothing else. Do not use `-p 8000:8000` (that opens it to your whole network) and do not put it on the internet as it is: anyone who can reach it can read everything it stores and start fetches from your connection. If it has to be reachable from elsewhere, put a reverse proxy that asks for a login in front of it.
