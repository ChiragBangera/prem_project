# Contributing

Prem Lab is a personal project, but changes are welcome. This is how they are easiest to review.

## Set up

```bash
uv sync --extra dev        # Python 3.11+; installs the app, pytest, ruff and mypy
npm install                # only for the frontend tests and the browser checks
```

`uv run prem serve --demo` runs the app on a synthetic world with no network, which is also what the tests and the browser checks use.

## Checks

CI runs all of these on every push and pull request; run them before you push.

```bash
uv run pytest                    # backend tests (no network, no browser)
uv run ruff check src tests      # lint: likely bugs, unused names, modern syntax
uv run mypy                      # types
npm test                         # frontend helpers, and a check that every module's imports and names exist
uv run prem serve --demo --no-open --port 8765 --today 2027-03-10 &
npm run e2e                      # the real UI in headless Chromium against the demo world
```

The lint and type settings live in `pyproject.toml`. A blind `except Exception` has to either log with its traceback or say, in a `# noqa: BLE001 - reason` comment, why it is broad.

## Commits and pull requests

The history is meant to be read, so a change is easiest to follow when it is made of small steps.

- **One logical change per commit**, small enough to read in one sitting (as a rule of thumb, a few hundred changed lines at most). The title says what, the body says why.
- **Conventional titles**: `feat:`, `fix:`, `refactor:`, `perf:`, `docs:`, `test:`, `chore:`, with an optional scope, for example `fix(scout): keep blanks out of the sort`.
- **Keep a refactor and a behaviour change apart.** Move code in one commit and change it in the next, so the move can be checked by eye.
- **Mechanical changes get their own commit** (an automatic lint fix, a rename), so the interesting commits are not buried in them.
- A change comes with its test, in the same commit.
- Do not rewrite history that has been pushed.

## Where things go

- **A metric, a lens, a profile tag**: declare it once in `src/app/metrics`; the catalog, the dictionary and the tables follow. See "Adding things" in [docs/architecture.md](docs/architecture.md).
- **A page**: a module in `src/app/workbench/pages/` with a class that extends `Part`, created in `src/app/workbench/core.py`, plus a thin route in `src/app/api.py`. The logic several pages share (which season a request means, dates of birth, event links, the datasets) lives next to the core, not in a page.
- **A data source or a derived layer**: see "The data flow" and "Versions and rebuilds" in the architecture notes; raw pages are kept, so a new derived number never needs a new request.
- **Frontend**: vanilla ES modules in `src/app/web/js`, no build step.

## Data and terms

The app reads public but undocumented sources for personal use (see [docs/data.md](docs/data.md)). Do not commit fetched data, raw pages or anything from a real data folder; the demo world exists so that nothing real is needed.
