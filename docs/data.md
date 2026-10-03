# Data: where it comes from, how it stays current, event data and ages

## Sources and their terms

| Source | What it gives | How it is read | Notes |
| --- | --- | --- | --- |
| [Understat](https://understat.com) | Every league table, fixture, shot and expected-goals value, player and team pages | Its public JSON endpoints, paced and retried | The core of the app. Unofficial: the endpoints are undocumented and can change (see [understat_endpoint_inventory.md](understat_endpoint_inventory.md)) |
| ESPN | Club squad lists, with exact dates of birth | Its public JSON feed | Used only for ages; if it is unreachable, ages stay as they were |
| Wikidata | Dates of birth for the few players a squad list leaves out | Its public SPARQL service | Deliberately strict: it only trusts a match it can verify |
| WhoScored (optional) | Every pass, duel, touch and carry | A real browser, through the [`soccerdata`](https://soccerdata.readthedocs.io) package | The only part that needs a browser, and the one whose terms may not allow it: see below |

None of these is an official, supported API. The app is unofficial and not affiliated with or endorsed by any of them. What follows from that:

- **It is for personal use, on your own computer.** What it reads stays on that computer; do not publish the stored data. WhoScored's terms in particular may not allow reading its pages at all, so event data runs only when you switch it on or start it.
- **It cannot be hosted with live data.** A public copy would be re-publishing other people's data. What can be shown publicly is the demo world (`prem serve --demo`): synthetic players, results and events, no network needed.
- **Any of the sources can change under it.** The data layer is built for that: a failed or unreadable response keeps the stored copy, records why, and is retried later with a growing delay; `prem doctor` (or the Data page) walks the data path and says which step broke.
- **A blank is better than a wrong value.** People are linked across sources only on an unambiguous match, and where the sources disagree or none can be sure, the value stays empty and the page says so.

## Your data stays up to date by itself

While the app is open, a background **cycle** runs every 15 minutes (every 90 seconds while there is a backlog). It looks for league seasons whose data may have changed and for **newly finished matches**, and fetches only those:

- A **finished season** is never fetched again. A **live season** refreshes around matchdays. A **match page** is fetched once, after Understat has settled its numbers, and kept for good.
- Work is paced and bounded: a few requests a second, with retries, and a time budget per cycle so a big backlog is worked off over several cycles instead of one long burst.
- **A failed request never stops anything else.** The stored copy keeps being served (flagged as stale), the failure is recorded with its reason, and it is retried later with a growing delay (5 minutes, doubling, up to 6 hours).
- Everything is **resumable and idempotent**: closing the app mid-cycle loses nothing, and the next cycle carries on from what the store holds.
- The **Data** page shows what is on your computer (per league season: matches played, match pages, event matches, squad lists, when it was updated), what the last cycle did, what is failing and when it will be retried, and has the controls: pause updating, how many previous seasons to keep complete, which leagues and seasons to fetch event data for, and an **Update now** button. The top bar carries a small status pill.

Once a page has loaded it is served from the local database; nothing is requested twice. In the browser, answers are also kept (in IndexedDB) and revalidated with ETags, so reopening a page is instant and the data refreshes quietly behind it.

## Event data (optional): passes, duels, tackles, carries and maps

Understat only records shots. An optional second source, WhoScored (read through the [`soccerdata`](https://soccerdata.readthedocs.io) package), supplies every event on the pitch, which adds passing, carrying, defending and duel metrics, possession, pressing, and the maps above. Nothing else in the app depends on it.

```bash
uv run --extra events prem events sync --league EPL --seasons 2025     # or switch it on from the Data page and let the updater do it
uv run prem events status
```

- **Slow, once.** A match takes about 15 seconds, so a full league season is roughly two hours. Every match is stored in the local database as soon as it is read and never fetched again. Stop it any time (Ctrl+C) and run the same command to carry on; later runs only fetch matches played since. From the Data page the updater does the same in a separate process, a few dozen matches at a time.
- **The raw page is kept**, exactly as served (about 100 KB compressed), and everything else is derived from it offline: the compact event arrays, the counters, every metric and map. Improving a definition or adding a metric or a map never needs a new request; `prem rebuild` (or the next start) re-derives from what is stored. See [docs/architecture.md](architecture.md).
- **Needs a browser.** Chrome, Chromium, Brave or Edge must be installed (found automatically; `--browser PATH` overrides). Add `--visible` if the site blocks the hidden window.
- **Safe by design.** WhoScored players and matches are matched to Understat's by name, club, date and score and **left out rather than guessed**; the Data page lists who could not be matched. Existing role scores and percentiles are never changed by event data: the all-data score is a separate column.
- **Personal use only.** It reads a public website, which that site's terms may not allow, so it only runs when you start it and keeps what it reads on your own computer. Do not publish the data.

## Ages

Understat has no birthdates, so ages come from two places, in this order:

1. **Club squad lists (ESPN's public JSON feed).** Each club's squad for a season lists its players with their exact date of birth, goalkeepers included. A player is matched to Understat by the *words of his name and his club*, never by a looser guess (spelling variants such as "Vitalii" / "Vitaliy" are handled, and "Gabriel" on Understat is matched to "Gabriel dos Santos Magalhães" only when he is the one unmatched candidate at that club). In a check against WhoScored's own ages for the Premier League, all 466 players that could be compared agreed. It is about 20 requests for a league and season, made in the background the first time you open Scout (or by `prem sync`), stored for good for finished seasons, and refreshed daily for the current one. A birthdate belongs to the player, not the season, so every stored list is used in every view: someone who has since moved on is found on the list of the club he went to. If the feed has almost nothing for a season (it has one player per club for Serie A 2023, for example) the Data page marks that season as sparse, asks again after a week, and ages there come from the other lists and from Wikidata.
2. **Wikidata, for the players a squad list leaves out** (a few per cent: club-name aliases, rarely a first name written differently). Wikidata has many retired namesakes, so the app is deliberately strict: it only trusts a match that is a plausible footballing age on the date in question, prefers a club the player is at *now* (a club someone left years ago does not count), and refuses to guess for single-word names. Where it cannot be sure the age stays blank, and an age matched by name alone is shown with a `?` but never decides anything: the age filter, similar-player searches and the young-talent highlights treat it as unknown.

The Scout age filter hides players with no sure age (the Age menu says how many, and can show them). The Data page shows, per league and season, how many players the squad lists matched, who is still unknown, and any player where Wikidata, sure of the club, disagrees. Both feeds are public but undocumented and used for personal use only; if one is unreachable, ages simply stay as they were.

If an age is wrong or missing, correct it yourself in `<data dir>/birthdates.json` (read at start-up). Use `"Name"` or, to tell two players of the same name apart, `"Name|Club"`:

```json
{ "Sávio": "2004-04-10", "Pablo Ibáñez|Alaves": "1998-08-03" }
```

## Managers

Understat has no manager data. To split a team's season by manager, add your own stints to `<data dir>/managers.json` (same shape as [`src/app/data/managers.json`](../src/app/data/managers.json)); they are merged in and appear on the Team page.
