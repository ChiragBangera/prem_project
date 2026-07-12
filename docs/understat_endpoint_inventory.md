# Understat Endpoint Inventory

This file tracks the Understat website routes and JSON-style data endpoints we have confirmed while building this project.

Sources used:
- Live Understat pages opened on April 3, 2026:
  - `https://understat.com/`
  - `https://understat.com/league/EPL/2025`
  - `https://understat.com/team/Manchester_United/2025`
  - `https://understat.com/player/565`
  - `https://understat.com/match/11652`
- Original `understat` package docs:
  - `https://understat.readthedocs.io/en/latest/classes/understat.html`
- Original package source:
  - `https://raw.githubusercontent.com/amosbastian/understat/refs/heads/master/understat/understat.py`
  - `https://github.com/amosbastian/understat/blob/master/understat/constants.py`

## Website Routes

- `/`
  - Home page with top-level league stats and export controls.
- `/league/{league_name}/{season}`
  - League overview page with table, fixtures/results, player table, filters, and exports.
- `/team/{team_name}/{season}`
  - Team overview page with team stats, results/fixtures, player table, filters, and exports.
- `/player/{player_id}`
  - Player page with shots, grouped stats, match logs, position stats, filters, and exports.
- `/match/{match_id}`
  - Match page with shot map, rosters, match stats, timeline, and exports.

## Confirmed Data Endpoints

- `GET /getStatData`
  - Home-page monthly stats by league.
- `GET /getLeagueData/{league_name}/{season}`
  - League page payload, including teams, players, and dates.
- `GET /getTeamData/{team_name}/{season}`
  - Team page payload, including statistics, players, and dates.
- `GET /getPlayerData/{player_id}`
  - Player page payload, including shots, matches, grouped stats, and min/max stats.
- `GET /getMatchData/{match_id}`
  - Match page payload, including rosters and shots.
- `POST /main/getPlayersStats/`
  - Filtered player table data for league and team pages.
  - Common payloads:
    - `league`, `season`, `date_start`, `date_end`
    - `team`, `season`, `date_start`, `date_end`
  - Requires AJAX-style headers and a page-specific `Referer`.
- `GET /main/getPlayersName/{query}`
  - Player search endpoint used by the site header search box.
  - Returns `response.success` plus a `players` list with `id`, `player`, and `team`.
- `POST /main/getPlayerMatches/{player_id}`
  - Extra player matches endpoint used by the player compare UI.
  - Returns `response.success`, `matches`, and `lastMatch`.

## Confirmed Public Utility Endpoints

- `POST /promotion/click/`
  - Shared site promotion click tracker referenced in shared frontend JS.
- `POST /office/login`
  - Public login endpoint referenced by the login page bundle.
  - Safely validated with an empty form submission, which returned JSON validation errors.

## Discovered Public Auth Routes

- `POST /office/registration`
  - Discovered in `login.min.js`.
  - Not exercised to avoid creating accounts or sending side effects.
- `POST /office/restorePassword`
  - Discovered in `login.min.js`.
  - Not exercised to avoid sending reset flows or side effects.

## What The Repo Covers

Implemented in the client now:
- Global stats
- League teams, players, results, fixtures, table, and filtered league player stats
- Team raw page data, stats, players, results, fixtures, and filtered team player stats
- Player raw page data, shots, matches, grouped stats, and per-position stats
- Player search and AJAX compare-match helpers
- Match raw page data, rosters, and shots

## Client-Side Only Behaviors Confirmed

- Table export buttons appear to export in-browser using `alasql` and the table's in-memory data.
- No separate server export endpoint was found in the inspected page bundles for `csv`, `json`, or `xlsx`.

## Still Unconfirmed

- Any team search endpoint analogous to player search is still unconfirmed.
- Any endpoints used only after authenticated `office` login remain unconfirmed.

If we need those next, the best follow-up is a browser-network capture against the live site.
