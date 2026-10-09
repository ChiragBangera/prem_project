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

While the app is open, a background updater keeps everything current. It does not look every few minutes: every fixture's kickoff is known, so after each **cycle** it works out the next moment something *can* have changed and sleeps until then (90 seconds while there is a backlog; the sleep follows the wall clock, so a laptop closed meanwhile does not delay it). The Data page says what it is waiting for, for example "Next: full time of Arsenal v Chelsea (Premier League), at 16:52". It fetches only what changed:

- A **live season**'s table is read again shortly after each match's full time, then every 20 minutes until Understat lists the result (every 2 hours after six hours; a match still missing after two days counts as postponed), every 6 hours while a recent match's xG settles, and otherwise twice a day so a moved fixture is noticed. A quiet Tuesday costs two requests per league, not a hundred.
- A **finished season** is never fetched again. A **match page** is fetched once, after Understat has settled its numbers, and kept for good.
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

- **On matchday, at half time and full time.** With event data switched on, every match of your event leagues is read shortly after its final whistle (kickoff + 112 minutes; again ten minutes later while WhoScored still has it in play, for up to four hours). The matches you **follow** are also read during the half-time break: your favourite teams' (the button on a team page) and any match you open while it is being played. Only those, because there is one browser and a read takes about half a minute: ten half-times at once would end after the second half had started. WhoScored's match centre is a live page, so a page read before the final whistle is kept apart as *provisional* and never counted in season totals; the full-time read replaces it.
- **Three daily limits, each counting pages read by the updater since midnight.** *Understat match pages* (300 by default): one page per finished match. *Event data, catching up* (40): older finished matches still missing their event data, 20 a run, 10 to 20 seconds apart, never while matches are being played. *Event data on matchday*: not a setting; two reads for each of the day's matches in your event leagues (full time, and half time for the ones you follow) and ten to spare, so a busy Saturday gets more than a quiet Tuesday. Matchday reads go first and do not use the catching-up limit.
- **Slow, once.** A match takes about 15 seconds, so a full league season is roughly two hours. Every match is stored in the local database as soon as it is read and never fetched again. Stop it any time (Ctrl+C) and run the same command to carry on; later runs only fetch matches played since. From the Data page the updater does the same in a separate process, a few dozen matches at a time.
- **The raw page is kept**, exactly as served (about 100 KB compressed), and everything else is derived from it offline: the compact event arrays, the counters, every metric and map. Improving a definition or adding a metric or a map never needs a new request; `prem rebuild` (or the next start) re-derives from what is stored. See [docs/architecture.md](architecture.md).
- **Needs a browser, and extra packages.** Google Chrome, Chromium or Brave must be installed (found automatically; `--browser PATH`, or the `PREM_BROWSER` variable for the Data page's updater, overrides). Microsoft Edge, although it comes with Windows, does not work: the tool that reads WhoScored only drives Chrome-family browsers. The packages come with `uv sync --extra events`; a later plain `uv sync` removes them again, so use `uv sync --extra events` when you update. Add `--visible` if the site blocks the hidden window.
- **Safe by design.** WhoScored players and matches are matched to Understat's by name, club, date and score and **left out rather than guessed**; the Data page lists who could not be matched. Existing role scores and percentiles are never changed by event data: the all-data score is a separate column.
- **Personal use only.** It reads a public website, which that site's terms may not allow, so it only runs when you start it and keeps what it reads on your own computer. Do not publish the data.

## How much is fetched, and how to steer it

Both sources are public websites read without an agreement, so the background updater reads like a patient person, not a crawler, and a new install fills its seasons over days rather than in one burst.

- **Daily limits** (Data page, *Fetching: limits and pace*): at most 300 Understat match pages and 40 WhoScored matches a day by default (both changeable). Understat pages are read one at a time, 1.5 s apart; WhoScored matches 10 to 20 s apart (at random), 20 to a run, with at least 20 minutes' rest between runs. Pages you open yourself load at once and are not held back (they are counted).
- **Pause, Resume, Stop.** Pause ends the run in progress at its next match and starts nothing until you resume (it survives restarts). *Stop this run* ends only the run in progress. The fetcher reads these between matches, so stopping always keeps what was read, on every system.
- **Fetch plan.** For every league season the updater keeps: what is still to come from each source and roughly how many days that takes at your limits.
- **Matches that could not be read** are not tried on every run: each is retried by itself up to three times, half a day apart, then waits for you. *Needs your eye* lists them with **Retry now** (read next, ahead of everything) and **Skip**.
- **Linking by hand.** The automatic matching only links what it is sure of. *Needs your eye* lists the WhoScored players and matches it could not place, with the likeliest Understat candidates (same club first, closest spelling, minutes alongside). Pick one, or say a player is not in Understat; your choice always wins, shows under *Your links*, and can be undone. Everything built on the event data follows at once.

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
