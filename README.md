# Premier League Analytics Lab

An async football analytics API and CLI built around Understat's public website data. The project turns league, team, player, and match data into reproducible analytical answers rather than one-off notebook work.

This is a personal portfolio project. It is unofficial and is not affiliated with or endorsed by Understat.

## What It Does

- Fetches JSON data for league, team, player, match, search, and filtered-stat endpoints.
- Derives league tables with xG, xGA, xPTS, PPDA, and deep-completion metrics.
- Answers natural-language questions about form, process versus results, player comparisons, coach windows, chance profiles, and defensive trends.
- Exposes the data and analysis through a hosted HTTP API and a local CLI.
- Returns written evidence and share-ready copy without coupling the analytics engine to a visualization framework.

The confirmed endpoint inventory is documented in [docs/understat_endpoint_inventory.md](docs/understat_endpoint_inventory.md).

## Run Locally

The project requires Python 3.11 or newer. With `uv` installed:

```bash
uv sync --extra dev
uv run uvicorn app.api:app --reload
```

Open these locally:

- API overview: `http://127.0.0.1:8000/`
- Interactive API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

Run the tests with:

```bash
uv run python -m unittest discover -s tests -v
```

## API

All application routes are versioned under `/api/v1`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check without calling Understat |
| `GET` | `/api/v1/endpoints` | List supported data operations |
| `GET` | `/api/v1/endpoints/{name}` | Describe one operation and its parameters |
| `POST` | `/api/v1/endpoints/{name}` | Execute a supported Understat operation |
| `POST` | `/api/v1/ask` | Run a natural-language analytics question |

Example analytics request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Compare Arsenal vs Liverpool in 2025"}'
```

Example raw-data request:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/endpoints/league_table \
  -H 'Content-Type: application/json' \
  -d '{"params":{"league_name":"EPL","season":2025}}'
```

## CLI

The package installs `prem-analytics`, with `understat-cli` retained as a compatibility alias.

```bash
uv run prem-analytics endpoints
uv run prem-analytics describe league_table
uv run prem-analytics run league_table league_name=EPL season=2025
uv run prem-analytics ask "Compare Arsenal first 5 vs last 5 league matches in 2025"
uv run prem-analytics shell
```

Reusable analytical questions are available through `prem-analytics templates`, and Manchester United examples through `prem-analytics manutd-presets`.

## Deploy For Free

The repository includes a Render Blueprint in `render.yaml`. Render currently offers free web services suitable for hobby and portfolio projects.

1. Push this repository to GitHub, GitLab, or Bitbucket.
2. In Render, choose **New > Blueprint** and connect the repository.
3. Accept the `prem-analytics-api` service defined in `render.yaml`.
4. After deployment, open the generated `onrender.com/docs` URL.

No database or paid add-on is required. Free Render services spin down after inactivity, so the first request after an idle period can take about a minute. The same application can also run from the included `Dockerfile` on any container host.

## Configuration

`FOOTBALL_ANALYTICS_CORS_ORIGINS` controls which browser origins may call the API. It accepts a comma-separated list and defaults to `*` because the API is read-only.

```bash
FOOTBALL_ANALYTICS_CORS_ORIGINS=https://your-portfolio.example,https://your-app.example
```

## Design Notes

- The endpoint manifest is the allowlist for public raw-data execution. Users cannot supply arbitrary upstream URLs.
- One async HTTP session is shared for the lifetime of the hosted application.
- Upstream timeouts, HTTP failures, and invalid JSON are translated into a consistent `502` API response.
- The health endpoint never calls Understat, so hosting platforms can distinguish application health from upstream availability.
- The service stores no user data and requires no persistent filesystem.

## Limitations

- Understat is an upstream website, not a guaranteed service-level API. Its routes or response shapes can change.
- Advanced goalkeeper conclusions need post-shot xG or save-quality data that Understat does not expose cleanly.
- Coach timelines are curated in the repository and should be updated as managerial eras change.
- This project explains statistical evidence; it does not claim that xG or xPTS alone proves tactical causation.

## License

Project code is available under the MIT License. Understat data remains subject to the source site's terms and ownership.
