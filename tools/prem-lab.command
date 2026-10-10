#!/bin/zsh
# Prem Lab launcher for macOS: double-click it to start the app and open it in your browser.
#
# Put an alias or a symlink to this file on the Desktop (it finds the project from its own real location):
#   ln -s /path/to/prem_project/tools/prem-lab.command ~/Desktop/"Prem Lab.command"
#
# The app runs in this window: close the window, or press Ctrl+C, to stop it. If Prem Lab is already running somewhere else (another window,
# or in the background) this just opens it, and offers to stop it: Ctrl+C only reaches what runs in the window you press it in.
# PREM_PORT=8011 changes the port (default 8010). Everything else (PREM_DEMO=1, PREM_DATA_DIR ...) works as for `prem serve`.

PORT="${PREM_PORT:-8010}"
URL="http://127.0.0.1:${PORT}/"
HEALTH="${URL}api/health"

# the project is the folder above tools/ (symlinks resolved); PREM_PROJECT or ~/Developer/prem_project are the fallbacks
PROJECT="${0:A:h:h}"
[[ -f "$PROJECT/pyproject.toml" ]] || PROJECT="${PREM_PROJECT:-$HOME/Developer/prem_project}"

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"   # where uv usually lives; Terminal may not have them on PATH

pause() { [[ -t 0 ]] || return 0; read -k 1 "?Press any key to close this window."; echo; }

# the process listening on the port (empty if none)
listener() { lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1; }

# stop it the way Ctrl+C would (the updater saves its place), and insist only if it does not stop
stop_listener() {
  local pid="$(listener)"
  [[ -n "$pid" ]] || { echo "Nothing is listening on port $PORT any more."; return 0; }
  echo "Stopping Prem Lab (process $pid) ..."
  kill -INT "$pid" 2>/dev/null
  for _ in {1..40}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null
    for _ in {1..10}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  fi
  if kill -0 "$pid" 2>/dev/null; then echo "It would not stop. To force it: kill -9 $pid"; return 1; fi
  echo "Stopped. Open this file again to start it afresh."
}

if curl -sf --max-time 2 "$HEALTH" 2>/dev/null | grep -q '"status":"ok"'; then
  running="$(listener)"
  echo "Prem Lab is already running at $URL${running:+ (process $running)}."
  open "$URL"
  echo "It was not started from this window, so pressing Ctrl+C here does not stop it."
  if [[ -t 0 ]]; then
    echo
    if read -k 1 -t 20 "?Press S to stop it, or any other key to leave it running. "; then
      echo
      if [[ "$REPLY" == [sS] ]]; then stop_listener; exit $?; fi
    else
      echo
    fi
    echo "Leaving it running. To stop it later, open this file again and press S."
  else
    echo "To stop it: kill -INT ${running:-<its process>}"
  fi
  exit 0
fi

if [[ -n "$(listener)" ]]; then
  echo "Port $PORT is in use by another program, so Prem Lab cannot start on it."
  echo "Close that program, or start Prem Lab on another port, e.g. PREM_PORT=8011."
  pause
  exit 1
fi

if [[ ! -f "$PROJECT/pyproject.toml" ]]; then
  echo "Cannot find the Prem Lab project (looked in $PROJECT)."
  echo "Set PREM_PROJECT to its folder, or keep this file inside it (tools/prem-lab.command)."
  pause
  exit 1
fi

cd "$PROJECT" || exit 1

# Bring the project up to date before starting, the way `git pull` would, but only when that is safe, and never in the way of starting:
# no Git (a downloaded ZIP), not on a branch that follows one on GitHub, files changed here, offline, or a history that has gone its own way
# all mean "start the version you have". PREM_NO_UPDATE=1 skips it.
update() {
  [[ -z "$PREM_NO_UPDATE" && -e .git ]] || return 0
  command -v git >/dev/null 2>&1 || return 0
  git symbolic-ref -q HEAD >/dev/null && git rev-parse -q --verify '@{upstream}' >/dev/null 2>&1 || return 0
  if [[ -n "$(git status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
    echo "Not looking for updates: files in $PROJECT have been changed here."
    echo
    return 0
  fi
  echo "Looking for updates ..."
  # fetching is the only step that uses the network, so it gets a time limit (stopping a fetch is harmless); the merge after it is local
  GIT_TERMINAL_PROMPT=0 git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 fetch --quiet 2>/dev/null &
  local fetch=$! waited=0
  while kill -0 "$fetch" 2>/dev/null && (( waited < 40 )); do sleep 0.25; (( waited++ )); done
  if kill -0 "$fetch" 2>/dev/null; then kill "$fetch" 2>/dev/null; wait "$fetch" 2>/dev/null
    echo "No answer from GitHub, so starting the version you have."; echo; return 0
  fi
  if ! wait "$fetch"; then echo "Could not reach GitHub (offline?), so starting the version you have."; echo; return 0; fi
  local before="$(git rev-parse HEAD)"
  if git merge-base --is-ancestor '@{upstream}' HEAD; then echo "Up to date."; echo; return 0; fi
  if ! git merge --ff-only --quiet '@{upstream}' >/dev/null 2>&1; then
    echo "There is an update, but this copy has changes of its own, so it was not applied. Run git pull in $PROJECT to sort it out."
    echo
    return 0
  fi
  echo "Updated. What is new:"
  git log --no-merges --format='  - %s' "$before..HEAD" | head -15
  echo
  # new or changed packages: uv run installs them by itself, unless event data is in use (only uv sync --extra events keeps those up to date);
  # an environment made with pip needs pip again
  if ! git diff --quiet "$before" HEAD -- pyproject.toml uv.lock; then
    if command -v uv >/dev/null 2>&1; then
      if [[ -n "$(echo .venv/lib/python*/site-packages/soccerdata(N))" ]]; then
        echo "Updating the packages ..."; uv sync --inexact --extra events --quiet || echo "Updating the packages failed: run uv sync --extra events in $PROJECT."
      fi
    elif [[ -x .venv/bin/pip ]]; then
      echo "Updating the packages ..."; .venv/bin/pip install --quiet -e . || echo "Updating the packages failed: run .venv/bin/pip install -e . in $PROJECT."
    fi
  fi
  # the launcher itself may have changed: Git replaced the file, which loses its icon (macOS keeps that beside the file), so put the icon back
  # and run the new launcher
  if ! git diff --quiet "$before" HEAD -- tools/prem-lab.command; then
    zsh tools/set-icon.sh >/dev/null 2>&1
    exec env PREM_NO_UPDATE=1 /bin/zsh "$PROJECT/tools/prem-lab.command"
  fi
}
update

# what to run: uv (it also keeps the environment in step with the project), else the project's own environment (made by "python3 -m venv .venv"), else a prem on the PATH
if command -v uv >/dev/null 2>&1; then PREM=(uv run prem)
elif [[ -x .venv/bin/prem ]]; then PREM=(.venv/bin/prem)
elif command -v prem >/dev/null 2>&1; then PREM=(prem)
else
  echo "Prem Lab is not installed yet. In $PROJECT, run:  uv sync"
  echo "(or, without uv:  python3 -m venv .venv  and then  .venv/bin/pip install -e .)"
  pause
  exit 1
fi

echo "Starting Prem Lab from $PROJECT"
echo "It opens at $URL when it is ready. Close this window or press Ctrl+C to stop it."
echo

# open the browser once the server answers (it takes a few seconds the first time)
( for _ in {1..90}; do curl -sf --max-time 1 "$HEALTH" >/dev/null 2>&1 && { open "$URL"; break; }; sleep 1; done ) &
OPENER=$!
trap 'kill "$OPENER" 2>/dev/null' EXIT
trap ':' INT                                  # Ctrl+C is for the server: this script waits for it to stop, then says so

"${PREM[@]}" serve --port "$PORT" --no-open
code=$?

echo
if (( code == 0 || code == 130 )); then echo "Prem Lab stopped."; else echo "Prem Lab stopped unexpectedly (exit code $code): the lines above say why."; fi
pause
exit "$code"
