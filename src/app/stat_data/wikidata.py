from __future__ import annotations

"""Player date-of-birth enrichment from Wikidata (SPARQL).

Understat exposes no date of birth anywhere (not in its JSON APIs, not in the
player page HTML). Wikidata is the clean free source: every footballer's date
of birth (P569) is available under CC0 via the public SPARQL endpoint. We
batch-query the names shown in a discovery result, disambiguate same-name
players by their club (P54 member-of-sports-team), cache the results, and
never invent a value when the lookup fails.

Failures are graceful: age is simply shown as "—" when Wikidata has no
matching entry.
"""

import asyncio
from datetime import date, datetime

import aiohttp

SPARQL_ENDPOINT = "https://qlever.cs.uni-freiburg.de/api/wikidata"
TIMEOUT_SECONDS = 12.0

_cache: dict[str, str | None] = {}


async def fetch_birthdates(names: list[str], team_hints: dict[str, str] | None = None) -> dict[str, str | None]:
    """Return {player_name: "YYYY-MM-DD" | None} from Wikidata (via QLever).

    `team_hints`: {player_name: understat_team} used to disambiguate namesakes.
    QLever is the public Wikidata SPARQL mirror maintained by Freiburg
    University — same data, no bot-policy friction.
    """
    team_hints = team_hints or {}
    unknown = [name for name in names if name not in _cache]
    if unknown:
        try:
            resolved = await _query_wikidata(unknown, team_hints)
        except Exception:
            resolved = {name: None for name in unknown}
        _cache.update(resolved)
    return {name: _cache.get(name) for name in names}


def age_on(dob: str | None, reference: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        born = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = reference or date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


async def _query_wikidata(names: list[str], team_hints: dict[str, str]) -> dict[str, str | None]:
    values = " ".join(f'"{name}"@en' for name in names)
    query = f"""
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?name ?dob ?teamLabel WHERE {{
      VALUES ?name {{ {values} }}
      ?person rdfs:label ?name ;
              wdt:P106 wd:Q937857 ;
              wdt:P569 ?dob .
      OPTIONAL {{
        ?person wdt:P54 ?team .
        ?team rdfs:label ?teamLabel FILTER(LANG(?teamLabel) = "en")
      }}
    }}
    """
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            SPARQL_ENDPOINT,
            data={"query": query},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "prem-analytics-lab/0.2 (local portfolio football-analytics tool)",
            },
        ) as response:
            response.raise_for_status()
            payload = await response.json()

    candidates: dict[str, list[dict]] = {}
    for binding in payload.get("results", {}).get("bindings", []):
        name = binding["name"]["value"]
        dob = binding["dob"]["value"][:10]
        team = binding.get("teamLabel", {}).get("value")
        candidates.setdefault(name, []).append({"dob": dob, "team": team})

    resolved: dict[str, str | None] = {}
    for name in names:
        options = candidates.get(name, [])
        if not options:
            resolved[name] = None
            continue
        hint = team_hints.get(name)
        if hint and len(options) > 1:
            best = _disambiguate(options, hint)
            resolved[name] = best["dob"] if best else options[0]["dob"]
        else:
            resolved[name] = options[0]["dob"]
    return resolved


def _disambiguate(options: list[dict], hint: str):
    hint_norm = hint.lower()
    for option in options:
        if option.get("team") and (hint_norm in option["team"].lower() or option["team"].lower() in hint_norm):
            return option
    return None
