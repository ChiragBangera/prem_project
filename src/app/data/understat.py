"""Network client for Understat's public JSON endpoints.

This module only knows how to *fetch* raw payloads politely and reliably:

* at most ``max_concurrency`` requests in flight, and ``min_interval`` seconds
  between request starts, so a bulk sync never hammers the site;
* retry with exponential backoff + jitter on 429/5xx/timeouts, honouring
  ``Retry-After``;
* a clear error when the body is not JSON (Understat changed, or a bot wall).

Parsing/typing lives in :mod:`app.data.normalize`; caching in
:mod:`app.data.repository`. Nothing here is cached or interpreted.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any
from urllib.parse import quote

import aiohttp

from app.errors import UpstreamError, UpstreamTimeout

BASE_URL = "https://understat.com"
USER_AGENT = "prem-lab/2.0 (personal football analytics; polite, cached)"
RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 20.0


def team_slug(name: str) -> str:
    return quote(name.replace(" ", "_"), safe="._")


class UnderstatClient:
    source = "understat"

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 25.0,
        max_concurrency: int = 4,
        min_interval: float = 0.25,
        retries: int = 3,
        base_url: str = BASE_URL,
        backoff_base: float = 0.6,
    ):
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(max_concurrency)
        self._min_interval = min_interval
        self._retries = retries
        self._backoff_base = backoff_base
        self._base = base_url.rstrip("/")
        self._pace_lock = asyncio.Lock()
        self._next_slot = 0.0
        self.requests_made = 0

    # ------------------------------------------------------------------ plumbing

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        loop = asyncio.get_running_loop()
        async with self._pace_lock:
            now = loop.time()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._min_interval
        if wait > 0:
            await asyncio.sleep(wait)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        referer: str | None = None,
        data: dict | None = None,
    ) -> Any:
        url = f"{self._base}{path}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        if data is not None:
            headers["Origin"] = self._base
        session = await self._ensure_session()

        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            delay = 0.0
            try:
                async with self._sem:
                    await self._pace()
                    self.requests_made += 1
                    async with session.request(method, url, headers=headers, data=data) as resp:
                        if resp.status in RETRY_STATUSES and attempt < self._retries:
                            delay = _retry_after(resp.headers.get("Retry-After"))
                            last_error = UpstreamError(
                                f"Understat returned HTTP {resp.status}.", upstream_status=resp.status
                            )
                        elif resp.status >= 400:
                            raise UpstreamError(
                                f"Understat returned HTTP {resp.status} for {path}.",
                                upstream_status=resp.status,
                                hint="The page may not exist for that league/season/team yet."
                                if resp.status == 404
                                else None,
                            )
                        else:
                            return _parse_json(await resp.text(), path)
            except asyncio.TimeoutError as exc:
                last_error = UpstreamTimeout(f"Understat did not answer {path} in time.")
                last_error.__cause__ = exc
            except aiohttp.ClientError as exc:
                last_error = UpstreamError(
                    f"Could not connect to Understat ({type(exc).__name__}).",
                    hint="Check your connection, or run in demo/offline mode.",
                )
                last_error.__cause__ = exc
            if attempt >= self._retries:
                break
            await asyncio.sleep(delay or _backoff(attempt, self._backoff_base))
        assert last_error is not None
        raise last_error

    async def _get(self, path: str, referer: str | None = None) -> Any:
        return await self._request("GET", path, referer=referer)

    async def _post(self, path: str, data: dict, referer: str) -> Any:
        return await self._request("POST", path, referer=referer, data=data)

    # ------------------------------------------------------------------ endpoints

    async def league(self, league: str, season: int) -> dict:
        return await self._get(f"/getLeagueData/{league}/{season}", f"{self._base}/league/{league}/{season}")

    async def team(self, team: str, season: int) -> dict:
        slug = team_slug(team)
        return await self._get(f"/getTeamData/{slug}/{season}", f"{self._base}/team/{slug}/{season}")

    async def player(self, player_id: int) -> dict:
        return await self._get(f"/getPlayerData/{int(player_id)}", f"{self._base}/player/{int(player_id)}")

    async def match(self, match_id: int) -> dict:
        return await self._get(f"/getMatchData/{int(match_id)}", f"{self._base}/match/{int(match_id)}")

    async def search_players(self, query: str) -> list[dict]:
        payload = await self._get(f"/main/getPlayersName/{quote(query)}", self._base + "/")
        if isinstance(payload, dict):
            inner = payload.get("response", payload)
            players = inner.get("players", []) if isinstance(inner, dict) else []
            return players if isinstance(players, list) else []
        return []

    async def league_players(
        self, league: str, season: int, date_start: str | None = None, date_end: str | None = None
    ) -> list[dict]:
        """Season player table for an optional date window (POST, as the site does)."""
        payload = {
            "league": league,
            "season": str(season),
            "date_start": f"{date_start} 00:00:00" if date_start else "",
            "date_end": f"{date_end} 23:59:59" if date_end else "",
        }
        response = await self._post(
            "/main/getPlayersStats/", payload, f"{self._base}/league/{league}/{season}"
        )
        players = response.get("players", response) if isinstance(response, dict) else response
        return players if isinstance(players, list) else []


# ---------------------------------------------------------------------- helpers


def _parse_json(text: str, path: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        head = text.lstrip()[:1]
        reason = (
            "an HTML page (the site may be blocking automated requests or has changed)"
            if head == "<"
            else "a response that is not valid JSON"
        )
        raise UpstreamError(
            f"Understat returned {reason} for {path}.",
            hint="Try again later; if it persists the endpoint may have changed.",
        ) from exc


def _backoff(attempt: int, base: float = 0.6) -> float:
    return min(8.0, base * (2**attempt)) * (0.75 + random.random() * 0.5)


def _retry_after(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return max(0.0, min(float(value), MAX_RETRY_AFTER))
    except ValueError:
        return 0.0
