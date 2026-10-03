"""Squad lists with exact dates of birth, from ESPN's public JSON feed.

Understat has no birthdates, and looking people up on Wikidata by name is a weak foundation (namesakes, a lagging
snapshot, missing entries). A club's squad list is a far better identity: the person is already known to be at that
club in that season, so the match to Understat is by name *and* club, and the date of birth comes with him, exact,
goalkeepers included.

* the standings of a season name that season's clubs (the team list ignores the season, so it is not used);
* each club's roster for that season lists its players with their dates of birth;
* a finished season is stored for good, the current one refreshes daily (squads change in transfer windows), and a season for
  which the feed lists only a handful of players a club ("sparse") is looked at again after a week instead of being trusted for good;
* it is resumable: clubs whose roster failed are fetched again next time, the rest are kept;
* one league-season is about 20 requests, paced politely, and never made when offline, in demo mode or when stored.

Personal use only. This is a public but undocumented feed, so every failure is quiet: ages simply stay as they were.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from typing import Any
from collections.abc import Callable, Iterable

import aiohttp

from app.config import Settings
from app.data.people import Person, link_people
from app.data.store import Store
from app.errors import UpstreamError
from app.leagues import current_season

log = logging.getLogger("prem.rosters")

BASE_URL = "https://site.web.api.espn.com/apis"
USER_AGENT = "prem-lab/2.0 (personal football analytics; polite, cached)"
LEAGUE_CODES = {"EPL": "eng.1", "La_liga": "esp.1", "Bundesliga": "ger.1", "Serie_A": "ita.1", "Ligue_1": "fra.1"}
KIND = "roster"
BODY_VERSION = 2  # 2: bodies carry a "sparse" flag (1: a thin season was stored as final)
MIN_SQUAD = 8  # a season whose median club has fewer listed players than this is "sparse": the feed has little for it
SPARSE_RETRY = 7 * 24 * 3600.0  # ...and is asked again after this long
COOLDOWN = 300.0  # after the feed refuses us, leave it alone for this long
RETRY_AFTER = 600.0  # clubs whose roster failed are asked for again no sooner than this
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


def _plausible(dob: str, season: int) -> bool:
    try:
        year = int(dob[:4])
    except ValueError:
        return False
    return 1960 <= year <= season - 13  # nobody in a first-team squad is younger than about 14


def parse_athletes(payload: dict, season: int) -> list[dict]:
    """Players with a usable date of birth from one roster response (a flat list, or grouped by position)."""
    athletes: list[dict] = []
    for item in payload.get("athletes") or []:
        athletes.extend(item["items"] if isinstance(item, dict) and "items" in item else [item])
    out = []
    for a in athletes:
        dob = str(a.get("dateOfBirth") or "")[:10]
        name = a.get("fullName") or a.get("displayName")
        if not name or not _plausible(dob, season):
            continue
        alt = [n for n in (a.get("displayName"),) if n and n != name]
        out.append({"id": str(a.get("id") or ""), "name": name, "alt": alt, "dob": dob, "pos": (a.get("position") or {}).get("abbreviation")})
    return out


class RosterClient:
    source = "espn"

    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        base_url: str = BASE_URL,
        session: aiohttp.ClientSession | None = None,
        clock: Callable[[], float] = time.time,
        today: Callable[[], date] = date.today,
        concurrency: int = 3,
        interval: float = 0.25,
        retries: int = 2,
        backoff: float = 0.6,
    ):
        self.store = store
        self.settings = settings
        self._base = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._clock = clock
        self._today = today
        self._sem = asyncio.Semaphore(concurrency)
        self._interval = interval
        self._retries = retries
        self._backoff = backoff
        self._pace_lock = asyncio.Lock()
        self._next_slot = 0.0
        self._cooldown_until = 0.0
        self.last_error: str | None = None   # why the last run did not fully succeed, for the Data page
        self._locks: dict[tuple[str, int], asyncio.Lock] = {}

    # ------------------------------------------------------------------ reads (never touch the network)

    @staticmethod
    def _key(league: str, season: int) -> str:
        return f"{league}:{season}"

    def cached(self, league: str, season: int) -> dict | None:
        record = self.store.get(KIND, self._key(league, season))
        if record is None or record.body.get("v") != BODY_VERSION:
            return None
        return record.body

    def version(self, league: str, season: int) -> tuple[int, float]:
        """Changes whenever the stored squad lists do: cached results built from them use it to know they are stale."""
        body = self.cached(league, season)
        return (sum(len(t["players"]) for t in body["teams"]), body["fetched"]) if body else (0, 0.0)

    def is_final(self, season: int) -> bool:
        return season < current_season(self._today())

    def fetched_at(self, league: str, season: int) -> float:
        """When a squad list was stored (0 if none), without decoding it."""
        meta = self.store.meta(KIND, self._key(league, season))
        return meta[0] if meta else 0.0

    def stamp(self) -> tuple:
        """A cheap token that changes whenever any stored squad list does (one query, nothing decoded)."""
        return tuple(sorted(self.store.keys(KIND)))

    def fresh(self, body: dict | None, season: int) -> bool:
        if not body or body.get("pending"):
            return False
        if body.get("sparse"):
            return self._clock() - body["fetched"] < SPARSE_RETRY
        return self.is_final(season) or self._clock() - body["fetched"] < self.settings.ttl_roster_live

    def cooling_down(self) -> bool:
        return self._clock() < self._cooldown_until

    def cool_down(self) -> None:
        """Leave the feed alone for a while (it refused us, or something about its answer was not as expected)."""
        self._cooldown_until = self._clock() + COOLDOWN

    def needs_fetch(self, league: str, season: int) -> bool:
        """True when :meth:`ensure` would go to the network: the league is covered, we are allowed out, the stored lists are missing or
        stale, the feed is not cooling down, and these are not clubs that failed moments ago and are waiting for their retry."""
        body = self.cached(league, season)
        if league not in LEAGUE_CODES or self.settings.offline or self.settings.demo or self.fresh(body, season) or self.cooling_down():
            return False
        return not (body and body.get("pending") and self._clock() - body["fetched"] < RETRY_AFTER)

    def seasons(self) -> list[tuple[str, int]]:
        out = []
        for key, _t, _c in self.store.keys(KIND):
            league, _, season = key.partition(":")
            if season.isdigit():
                out.append((league, int(season)))
        return out

    # ------------------------------------------------------------------ network

    async def _pace(self) -> None:
        async with self._pace_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def _get(self, path: str) -> dict:
        session = self._session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.settings.request_timeout))
        if self._session is None:
            self._session = session
        last: Exception | None = None
        for attempt in range(self._retries + 1):
            async with self._sem:
                await self._pace()
                try:
                    async with session.get(f"{self._base}{path}", headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as response:
                        if response.status in RETRY_STATUSES:
                            raise UpstreamError(f"ESPN answered {response.status}")
                        if response.status != 200:
                            raise UpstreamError(f"ESPN answered {response.status}", hint="Squad lists are unavailable right now; ages fall back to Wikidata.")
                        return await response.json(content_type=None)
                except (TimeoutError, aiohttp.ClientError, UpstreamError, ValueError) as exc:
                    last = exc
            if attempt < self._retries:
                await asyncio.sleep(self._backoff * (2 ** attempt))
        raise UpstreamError(f"ESPN could not be read: {last}") from last

    async def _plan(self, code: str, season: int, body: dict | None) -> tuple[list[dict], list[dict], dict[str, dict]]:
        """``(clubs to fetch, rosters already in hand, old rosters to fall back on)`` for what is stored so far."""
        if body is None:                              # first time: the season's standings name its clubs
            standings = await self._get(f"/v2/sports/soccer/{code}/standings?season={season}")
            entries = standings["children"][0]["standings"]["entries"]
            return [{"id": str(e["team"]["id"]), "name": e["team"]["displayName"]} for e in entries], [], {}
        if body.get("pending"):                       # some clubs failed last time: only those again
            return list(body["pending"]), list(body["teams"]), {}
        return [{"id": t["id"], "name": t["name"]} for t in body["teams"]], [], {t["id"]: t for t in body["teams"]}   # a live season, refreshed

    async def ensure(self, league: str, season: int, *, on_progress: Callable[[int, int], None] | None = None) -> dict | None:
        """The squad lists of a league-season: stored if fresh, otherwise fetched (only the clubs still missing). None if unavailable."""
        body = self.cached(league, season)
        if not self.needs_fetch(league, season):       # also: clubs that failed are retried, but not on every request
            return body
        lock = self._locks.setdefault((league, season), asyncio.Lock())
        async with lock:
            body = self.cached(league, season)
            if self.fresh(body, season):
                return body
            code = LEAGUE_CODES[league]
            try:
                todo, teams, previous = await self._plan(code, season, body)
            except (UpstreamError, KeyError, IndexError, TypeError) as exc:
                self.cool_down()
                self.last_error = f"{league} {season}: the season's clubs could not be read ({str(exc)[:120]})"
                log.warning("squad lists for %s %s unavailable: %s", league, season, exc)
                return body
            total, done = len(todo) + len(teams), len(teams)

            async def one(team: dict) -> tuple[dict, dict | None]:
                try:
                    data = await self._get(f"/site/v2/sports/soccer/{code}/teams/{team['id']}/roster?season={season}")
                    return team, {"id": team["id"], "name": team["name"], "players": parse_athletes(data, season)}
                except Exception as exc:  # noqa: BLE001 - one club's odd answer must not cost the league its other squads
                    log.warning("roster for %s (%s %s) failed: %s", team["name"], league, season, exc)
                    self.last_error = f"{team['name']} ({league} {season}): {str(exc)[:120]}"
                    return team, None

            failed: list[dict] = []
            for finished in asyncio.as_completed([one(t) for t in todo]):
                team, result = await finished
                if result is not None:
                    teams.append(result)
                elif team["id"] in previous:
                    teams.append(previous[team["id"]])  # a bad request must not cost a club its squad
                else:
                    failed.append(team)
                done += 1
                if on_progress:
                    on_progress(done, total)
            if not teams:
                self.cool_down()
                return body
            if not failed:
                self.last_error = None
            sizes = sorted(len(t["players"]) for t in teams)
            sparse = sizes[len(sizes) // 2] < MIN_SQUAD
            if sparse:
                log.warning("squad lists for %s %s are sparse (a median of %d players a club): the feed has little for this season", league, season, sizes[len(sizes) // 2])
            new = {"v": BODY_VERSION, "league": league, "season": season, "fetched": self._clock(), "teams": sorted(teams, key=lambda t: t["name"]), "pending": failed, "sparse": sparse}
            self.store.put(KIND, self._key(league, season), new, source=self.source, complete=self.is_final(season) and not failed and not sparse)
            return new

    async def probe(self, league: str = "EPL", season: int | None = None) -> str:
        """One real round trip that stores nothing: the standings name a club and its roster names players. For the connection check."""
        code = LEAGUE_CODES[league]
        season = season or current_season(self._today())
        try:
            club = (await self._get(f"/v2/sports/soccer/{code}/standings?season={season}"))["children"][0]["standings"]["entries"][0]["team"]
            players = parse_athletes(await self._get(f"/site/v2/sports/soccer/{code}/teams/{club['id']}/roster?season={season}"), season)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise UpstreamError(f"ESPN answered, but not in the shape expected ({type(exc).__name__}).", hint="The squad-list feed may have changed; ages fall back to Wikidata until it is updated.") from exc
        if not players:
            raise UpstreamError(f"ESPN named {club['displayName']} but listed no players with birthdates.", hint="Ages fall back to Wikidata.")
        return f"ESPN answered: {club['displayName']} has {len(players)} players with exact birthdates"

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None


def link_roster(roster: dict, players: Iterable[Any]) -> tuple[dict[int, dict], list[dict]]:
    """``({understat id: roster player}, roster players that match no Understat player)`` for one league-season."""
    people, by_key = [], {}
    for team in roster["teams"]:
        for p in team["players"]:
            key = f"{team['id']}:{p['id'] or p['name']}"
            by_key[key] = {**p, "team": team["name"]}
            people.append(Person(key=key, name=p["name"], clubs=[team["name"]], alt_names=p.get("alt", []), pos=p.get("pos")))
    linked, left = link_people(people, players, loose=True)
    return {uid: by_key[person.key] for uid, person in linked.items()}, [by_key[p.key] for p, _c in left]
