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
import re
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
AGE_RANGE = (15, 40)  # a plausible age for a first-team footballer on the date being asked about
NAME_ONLY_MAX_AGE = 38  # with no club evidence the retired namesake is the likelier explanation for an older player
_CLUB_NOISE = {"fc", "cf", "afc", "cd", "ud", "sd", "rc", "rcd", "sc", "ac", "as", "ssc", "us", "fk", "sv", "vfb", "vfl", "tsv", "de", "del", "la", "el", "the", "of", "and", "club", "futbol", "football", "calcio", "association", "balompie"}
USER_AGENT = "prem-lab/2.0 (personal football analytics; birth-date lookups, cached)"

QUERY = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?name ?dob ?teamLabel ?start ?end WHERE {{
  VALUES ?name {{ {values} }}
  ?person {label_prop} ?name ;
          wdt:P106 wd:Q937857 ;
          wdt:P569 ?dob .
  OPTIONAL {{
    ?person p:P54 ?membership .
    ?membership ps:P54 ?team .
    ?team rdfs:label ?teamLabel FILTER(LANG(?teamLabel) = "en")
    OPTIONAL {{ ?membership pq:P580 ?start }}
    OPTIONAL {{ ?membership pq:P582 ?end }}
  }}
}}
"""
CACHE_VERSION = 2  # 2 added the dates of each club stint; older cached answers are asked again


def age_on(dob: str | None, today: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob[:10])
    except ValueError:
        return None
    today = today or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", fold(text)) if t not in _CLUB_NOISE}


def _same_club(hint: str, team: str) -> bool:
    """Understat says "Celta Vigo", Wikidata says "RC Celta de Vigo": compare the meaningful words, not the strings."""
    folded = fold(team)
    wanted = _tokens(hint)
    return bool(hint in folded or (folded and folded in hint) or (wanted and wanted <= _tokens(team)))


def same_club(a: str, b: str) -> bool:
    """Whether two spellings plausibly name the same club ("Celta Vigo" / "RC Celta de Vigo", "Newcastle" / "Newcastle United")."""
    fa, fb = fold(a), fold(b)
    if not fa or not fb:
        return False
    if fa == fb or fa in fb or fb in fa:
        return True
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb and (ta <= tb or tb <= ta))


def _year(value: str | None) -> int | None:
    try:
        return int(value[:4]) if value else None
    except ValueError:
        return None


def _club_evidence(candidate: dict, hints: list[str], reference: date) -> str | None:
    """How well the candidate's clubs support the player being at one of ``hints`` around ``reference``.

    ``"current"``: a matching stint with no end, or one that ended within two years;
    ``"undated"``: a match with no dates at all (older cached answers, or Wikidata gaps);
    ``"past"``: the candidate did play there, but long ago (a retired namesake, most likely);
    ``None``: no matching club.
    """
    stints = candidate.get("stints") or [{"team": t, "start": None, "end": None} for t in candidate.get("teams", [])]
    best = None
    for stint in stints:
        if not any(_same_club(h, stint["team"]) for h in hints):
            continue
        start, end = _year(stint.get("start")), _year(stint.get("end"))
        if end is None and start is None:
            best = best or "undated"
        elif end is None or end >= reference.year - 2:
            return "current"
        else:
            best = best or "past"
    return best


def resolve_birthdate(
    candidates: list[dict], team_hints: str | list[str] | None, *, name: str | None = None, reference: date | None = None
) -> tuple[str | None, str | None]:
    """Choose a date of birth among namesakes, or ``(None, None)`` when it would be a guess.

    Returns ``(dob, basis)`` where basis is ``"club"`` (a club the player is at matches a *recent* stint on the
    Wikidata entry) or ``"name"`` (the only plausible person with that name, nothing for or against). Rules:

    * a candidate must be a plausible age (15 to 40) on ``reference``, which rules out the retired namesakes
      that Wikidata is full of;
    * a recent stint at one of the player's clubs settles it, unless that still leaves two people;
    * a match with no dates counts the same, but only if no recent stint exists elsewhere;
    * with no club evidence, a lone plausible candidate is accepted only for a full name (a single word such
      as "Sávio" or "Mariano" is far too likely to be someone else), only up to age 38, and never when the
      entry shows they played for this club long ago and left (a retired namesake).
    """
    reference = reference or date.today()
    plausible = []
    for c in candidates:
        age = age_on(c.get("dob"), reference)
        if age is not None and AGE_RANGE[0] <= age <= AGE_RANGE[1]:
            plausible.append(c)
    if not plausible:
        return None, None
    hints = [fold(h) for h in ([team_hints] if isinstance(team_hints, str) else team_hints or []) if h]
    evidence = {id(c): _club_evidence(c, hints, reference) for c in plausible}
    for level in ("current", "undated"):
        found = {c["dob"] for c in plausible if evidence[id(c)] == level}
        if len(found) == 1:
            return next(iter(found)), "club"
        if len(found) > 1:
            return None, None
    dobs = {c["dob"] for c in plausible}
    if len(dobs) != 1:
        return None, None
    if name is not None and len(name.split()) < 2:
        return None, None
    only = next(iter(dobs))
    if (age_on(only, reference) or 0) > NAME_ONLY_MAX_AGE or any(evidence[id(c)] == "past" for c in plausible):
        return None, None
    return only, "name"


def pick_birthdate(candidates: list[dict], team_hint: str | list[str] | None, *, name: str | None = None, reference: date | None = None) -> str | None:
    return resolve_birthdate(candidates, team_hint, name=name, reference=reference)[0]


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

    def cached(self, name: str, team_hint: str | list[str] | None = None, reference: date | None = None) -> str | None:
        return self.cached_info(name, team_hint, reference)[0]

    def cached_info(self, name: str, team_hint: str | list[str] | None = None, reference: date | None = None) -> tuple[str | None, str | None]:
        """``(dob, basis)`` from what Wikidata returned earlier; nothing is fetched here."""
        record = self.store.get("dob", fold(name))
        if record is None:
            return None, None
        return resolve_birthdate(record.body.get("candidates", []), team_hint, name=name, reference=reference)

    def known(self, name: str) -> bool:
        record = self.store.get("dob", fold(name))
        return record is not None and record.body.get("v") == CACHE_VERSION

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
            if record is not None and record.body.get("v") == CACHE_VERSION:
                candidates = record.body.get("candidates", [])
                ttl = self.settings.ttl_dob_hit if candidates else self.settings.ttl_dob_miss
                if now - record.fetched_at < ttl:
                    result[key] = pick_birthdate(candidates, hint, name=name)
                    continue
            missing.append(name)

        if missing and not self.settings.offline and not self.settings.demo and now >= self._cooldown_until:
            async with self._lock:
                await self._fetch_missing(missing)
            for name in missing:
                key = fold(name)
                record = self.store.get("dob", key)
                result[key] = pick_birthdate(record.body.get("candidates", []), wanted[key][1], name=name) if record else None
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
                    {"candidates": found.get(fold(name), []), "name": name, "v": CACHE_VERSION},
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
        grouped: dict[str, dict[str, dict[str, set]]] = {}
        for binding in payload.get("results", {}).get("bindings", []):
            try:
                name = binding["name"]["value"]
                dob = binding["dob"]["value"][:10]
            except KeyError:
                continue
            entry = grouped.setdefault(fold(name), {}).setdefault(dob, {"teams": set(), "stints": set()})
            team = binding.get("teamLabel", {}).get("value")
            if team:
                entry["teams"].add(team)
                entry["stints"].add((team, binding.get("start", {}).get("value", "")[:10], binding.get("end", {}).get("value", "")[:10]))
        return {
            key: [
                {
                    "dob": dob,
                    "teams": sorted(e["teams"]),
                    "stints": [{"team": t, "start": st or None, "end": en or None} for t, st, en in sorted(e["stints"])],
                }
                for dob, e in sorted(by_dob.items())
            ]
            for key, by_dob in grouped.items()
        }
