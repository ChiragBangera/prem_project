"""Date-of-birth enrichment from Wikidata (CC0).

Understat has no ages, and age is central to scouting ("under-21s with real
output"). Wikidata has a birth date for most professional footballers. We look
players up by name in batches, keep *all* candidate namesakes in the local
cache, and choose between them at read time using the club as a hint. When the
name is ambiguous or unknown the age is left blank - never guessed.

Failures are quiet and self-healing: an unreachable endpoint just means no ages
this time (with a short cool-down), and misses are cached so we do not re-ask
Wikidata about the same unknown name on every page load.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Iterable

import aiohttp

from app.config import Settings
from app.leagues import fold

from .store import Store

QLEVER = "https://qlever.cs.uni-freiburg.de/api/wikidata"
WDQS = "https://query.wikidata.org/sparql"
ENDPOINTS = (QLEVER, WDQS)
BATCH = 40
COOLDOWN = 300.0
PLAUSIBLE_BORN = (1970, 2012)
USER_AGENT = "prem-lab/2.0 (personal football analytics; birth-date lookups, cached)"

QUERY = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?name ?dob ?teamLabel WHERE {{
  VALUES ?name {{ {values} }}
  ?person {label_prop} ?name ;
          wdt:P106 wd:Q937857 ;
          wdt:P569 ?dob .
  OPTIONAL {{
    ?person wdt:P54 ?team .
    ?team rdfs:label ?teamLabel FILTER(LANG(?teamLabel) = "en")
  }}
}}
"""


def age_on(dob: str | None, today: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def pick_birthdate(candidates: list[dict], team_hint: str | None) -> str | None:
    """Choose a date of birth among namesakes, or None when it would be a guess."""
    plausible = [
        c for c in candidates if c.get("dob") and PLAUSIBLE_BORN[0] <= int(c["dob"][:4]) <= PLAUSIBLE_BORN[1]
    ]
    if not plausible:
        return None
    if len({c["dob"] for c in plausible}) == 1:
        return plausible[0]["dob"]
    hint = fold(team_hint)
    if hint:
        matching = {
            c["dob"]
            for c in plausible
            if any(hint in fold(t) or (fold(t) and fold(t) in hint) for t in c.get("teams", []))
        }
        if len(matching) == 1:
            return matching.pop()
    return None


def _quote(name: str) -> str:
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"@en'


class BirthdateResolver:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        *,
        endpoints: tuple[str, ...] = ENDPOINTS,
        session: aiohttp.ClientSession | None = None,
        clock=time.time,
    ):
        self.store = store
        self.settings = settings
        self.endpoints = endpoints
        self._session = session
        self._clock = clock
        self._cooldown_until = 0.0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ reads

    def cached(self, name: str, team_hint: str | None = None) -> str | None:
        record = self.store.get("dob", fold(name))
        if record is None:
            return None
        return pick_birthdate(record.body.get("candidates", []), team_hint)

    def known(self, name: str) -> bool:
        return self.store.meta("dob", fold(name)) is not None

    # ------------------------------------------------------------------ resolve

    async def resolve(self, people: Iterable[tuple[str, str | None]]) -> dict[str, str | None]:
        """Return ``{fold(name): 'YYYY-MM-DD' | None}`` for the given (name, club) pairs."""
        wanted: dict[str, tuple[str, str | None]] = {}
        for name, hint in people:
            if name and fold(name) not in wanted:
                wanted[fold(name)] = (name, hint)

        result: dict[str, str | None] = {}
        missing: list[str] = []
        now = self._clock()
        for key, (name, hint) in wanted.items():
            record = self.store.get("dob", key)
            if record is not None:
                candidates = record.body.get("candidates", [])
                ttl = self.settings.ttl_dob_hit if candidates else self.settings.ttl_dob_miss
                if now - record.fetched_at < ttl:
                    result[key] = pick_birthdate(candidates, hint)
                    continue
            missing.append(name)

        if missing and not self.settings.offline and not self.settings.demo and now >= self._cooldown_until:
            async with self._lock:
                await self._fetch_missing(missing)
            for name in missing:
                key = fold(name)
                record = self.store.get("dob", key)
                result[key] = pick_birthdate(record.body.get("candidates", []), wanted[key][1]) if record else None
        else:
            for name in missing:
                result.setdefault(fold(name), None)
        return result

    async def _fetch_missing(self, names: list[str]) -> None:
        for start in range(0, len(names), BATCH):
            batch = names[start : start + BATCH]
            try:
                found = await self._query(batch, "rdfs:label")
                leftovers = [n for n in batch if fold(n) not in found]
                if leftovers:
                    try:
                        found.update(await self._query(leftovers, "skos:altLabel"))
                    except Exception:  # alt-label pass is best effort
                        pass
            except Exception:
                self._cooldown_until = self._clock() + COOLDOWN
                return
            stamp = self._clock()
            for name in batch:
                self.store.put(
                    "dob",
                    fold(name),
                    {"candidates": found.get(fold(name), []), "name": name},
                    source="wikidata",
                    fetched_at=stamp,
                )

    async def _query(self, names: list[str], label_prop: str) -> dict[str, list[dict]]:
        query = QUERY.format(values=" ".join(_quote(n) for n in names), label_prop=label_prop)
        session = self._session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        owns = self._session is None
        last_error: Exception | None = None
        try:
            for endpoint in self.endpoints:
                try:
                    async with session.post(
                        endpoint,
                        data={"query": query},
                        headers={"Accept": "application/sparql-results+json", "User-Agent": USER_AGENT},
                    ) as response:
                        response.raise_for_status()
                        payload = await response.json(content_type=None)
                    return self._parse(payload)
                except Exception as exc:  # try the next endpoint
                    last_error = exc
            assert last_error is not None
            raise last_error
        finally:
            if owns:
                await session.close()

    @staticmethod
    def _parse(payload: dict) -> dict[str, list[dict]]:
        grouped: dict[str, dict[str, set[str]]] = {}
        for binding in payload.get("results", {}).get("bindings", []):
            try:
                name = binding["name"]["value"]
                dob = binding["dob"]["value"][:10]
            except KeyError:
                continue
            team = binding.get("teamLabel", {}).get("value")
            teams = grouped.setdefault(fold(name), {}).setdefault(dob, set())
            if team:
                teams.add(team)
        return {
            key: [{"dob": dob, "teams": sorted(teams)} for dob, teams in sorted(by_dob.items())]
            for key, by_dob in grouped.items()
        }
