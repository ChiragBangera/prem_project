"""HTTP layer: thin routes over the Workbench, uniform errors, static frontend."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app import __version__
from app.config import Settings
from app.errors import AppError, BadRequest
from app.workbench import Workbench

log = logging.getLogger("prem.api")
WEB_DIR = Path(__file__).parent / "web"


def _clean(value: Any) -> Any:
    """Make analytics output JSON-safe: numpy scalars to Python, NaN/inf to null."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return super().render(_clean(content))


class ETagMiddleware:
    """Gives every cacheable GET under ``/api`` a validator, and answers 304 when the browser already holds that exact body.

    The browser keeps what it has loaded (its own HTTP cache, plus the app's IndexedDB cache) and asks again with ``If-None-Match``;
    an unchanged answer costs a few bytes and no re-parse. Things that must always be live (status, jobs, search) are left alone.
    """

    SKIP = ("/api/data", "/api/health", "/api/search", "/api/shortlist", "/api/docs", "/api/openapi")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or scope["method"] != "GET" or not path.startswith("/api/") or path.startswith(self.SKIP):
            return await self.app(scope, receive, send)
        wanted = next((v.decode() for k, v in scope["headers"] if k == b"if-none-match"), None)
        started: Message | None = None
        chunks: list[bytes] = []

        async def capture(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = message
                return
            if started is None:                  # a body before a start message: not ours to judge, pass it on
                await send(message)
                return
            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            headers = list(started["headers"])
            if started["status"] == 200:
                etag = 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
                headers = [(k, v) for k, v in headers if k not in (b"etag", b"cache-control")] + [(b"etag", etag.encode()), (b"cache-control", b"no-cache")]
                if wanted == etag:
                    keep = [(k, v) for k, v in headers if k in (b"etag", b"cache-control", b"vary")]
                    await send({"type": "http.response.start", "status": 304, "headers": keep})
                    await send({"type": "http.response.body", "body": b""})
                    return
            await send({**started, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, capture)


class ShortlistItem(BaseModel):
    name: str = ""
    team: str = ""
    league: str = "EPL"
    note: str | None = None


class SyncRequest(BaseModel):
    leagues: list[str] = Field(default_factory=lambda: ["EPL"])
    seasons: list[int] = Field(default_factory=list)
    force: bool = False


class AutoPrefs(BaseModel):
    enabled: bool | None = None
    seasons_back: int | None = Field(None, ge=0, le=4)
    events: dict | None = None
    limits: dict | None = None


class EventMatch(BaseModel):
    league: str
    season: int
    game: int
    skip: bool | None = None


class EventPause(BaseModel):
    paused: bool


class EventLink(BaseModel):
    league: str
    season: int
    kind: str = Field(pattern="^(players|matches)$")
    ws: int
    us: int | None = None          # None: forget the person's choice; 0 (players): not in Understat, leave him out


def ok(payload: Any, status: int = 200) -> SafeJSONResponse:
    """Return JSON with numpy scalars and NaN/inf sanitised *before* FastAPI's own encoder sees them."""
    return SafeJSONResponse(payload, status_code=status)


def _ints(value: str | None) -> list[int]:
    if not value:
        return []
    try:
        return [int(v) for v in value.split(",") if v.strip()]
    except ValueError as exc:
        raise BadRequest(f"Expected comma-separated integers, got '{value}'.") from exc


def _list(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def create_app(settings: Settings | None = None, *, provider=None, today: date | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.wb = Workbench(settings, provider=provider, today=today)
        await app.state.wb.start()
        yield
        await app.state.wb.close()

    app = FastAPI(
        title="Prem Lab", version=__version__, lifespan=lifespan, default_response_class=SafeJSONResponse,
        docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
    )
    app.add_middleware(ETagMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    def wb(request: Request) -> Workbench:
        return request.app.state.wb

    # ------------------------------------------------------------------ errors

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return SafeJSONResponse(status_code=exc.status, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []) if p != "query")
        return SafeJSONResponse(status_code=422, content={"error": "invalid_parameters", "message": f"{where}: {first.get('msg', 'invalid value')}".strip(": ")})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return SafeJSONResponse(status_code=exc.status_code, content={"error": code, "message": str(exc.detail)})

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")
        return SafeJSONResponse(status_code=500, content={"error": "internal_error", "message": "Something went wrong on the server.", "hint": "Check the server log."})

    # ------------------------------------------------------------------ routes

    @app.get("/api/health")
    async def health():
        return ok({"status": "ok", "version": __version__})

    @app.get("/api/meta")
    async def meta(request: Request):
        return ok(await wb(request).meta())

    @app.get("/api/catalog")
    async def catalog(request: Request):
        return ok(wb(request).catalog())

    @app.get("/api/briefing")
    async def briefing(request: Request, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).briefing.page(league, season))

    @app.get("/api/league")
    async def league(request: Request, league: str = "EPL", season: str = "auto", venue: str = "all", last: int | None = Query(None, ge=1, le=40),
                     date_from: str | None = None, date_to: str | None = None):
        return ok(await wb(request).league.page(league, season, venue=venue, last=last, date_from=date_from, date_to=date_to))

    @app.get("/api/team")
    async def team(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team.page(league, season, team))

    @app.get("/api/team/history")
    async def team_history(request: Request, team: str, league: str = "EPL", seasons: str = ""):
        return ok(await wb(request).team.history(league, team, _ints(seasons)))

    @app.get("/api/team/chances")
    async def team_chances(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team.chances(league, season, team))

    @app.get("/api/team/chances/league")
    async def team_chances_league(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team.chances_league(league, season, team))

    @app.get("/api/dictionary")
    async def dictionary(request: Request):
        return ok(wb(request).dictionary.entries())

    @app.get("/api/dictionary/stats")
    async def dictionary_stats(request: Request, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).dictionary.stats(league, season))

    @app.get("/api/players")
    async def players(request: Request, leagues: str = "EPL", seasons: str = "auto", min_minutes: int = Query(1, ge=0, le=3000)):
        return ok(await wb(request).scout.players(_list(leagues), _list(seasons) or ["auto"], min_minutes=min_minutes))

    @app.get("/api/teams")
    async def teams(request: Request, leagues: str = "EPL", seasons: str = "auto"):
        return ok(await wb(request).scout.teams(_list(leagues), _list(seasons) or ["auto"]))

    @app.get("/api/maps/team")
    async def maps_team(request: Request, team: str, league: str = "EPL", season: str = "auto", venue: str = "all", last: int | None = Query(None, ge=1, le=60)):
        return ok(await wb(request).team.maps(league, season, team, venue=venue, last=last))

    @app.get("/api/maps/player/{player_id}")
    async def maps_player(request: Request, player_id: int, league: str | None = None, season: str = "auto", last: int | None = Query(None, ge=1, le=60)):
        return ok(await wb(request).player.maps(player_id, league, season, last=last))

    @app.get("/api/team/shots")
    async def team_shots(request: Request, team: str, league: str = "EPL", season: str = "auto", venue: str = "all", last: int | None = Query(None, ge=1, le=60)):
        return ok(await wb(request).team.shots(league, season, team, venue=venue, last=last))

    @app.get("/api/team/matches")
    async def team_matches(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team.matches(league, season, team))

    @app.get("/api/player/{player_id}")
    async def player(request: Request, player_id: int, league: str | None = None, season: str = "auto", seasons: str | None = None):
        return ok(await wb(request).player.page(player_id, league, season, _ints(seasons) or None))

    @app.get("/api/player/{player_id}/trend")
    async def player_trend(request: Request, player_id: int, league: str | None = None, season: str = "auto"):
        return ok(await wb(request).player.trend(player_id, league, season))

    @app.get("/api/player/{player_id}/similar")
    async def similar(request: Request, player_id: int, league: str = "EPL", seasons: str = "", max_age: int | None = None, min_age: int | None = None,
                      min_minutes: int | None = None, other_leagues: str = "", limit: int = Query(12, ge=1, le=30)):
        target_seasons = _ints(seasons)
        if not target_seasons:
            resolved, _ = await wb(request).seasons.resolve(league, "auto")
            target_seasons = [resolved]
        return ok(await wb(request).player.similar(player_id, league, target_seasons, max_age=max_age, min_age=min_age, min_minutes=min_minutes,
                                                 other_leagues=_list(other_leagues), limit=limit))

    @app.get("/api/compare/players")
    async def compare_players(request: Request, ids: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).compare.players(_ints(ids), league, season))

    @app.get("/api/compare/teams")
    async def compare_teams(request: Request, a: str, b: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).compare.teams(league, season, a, b))

    @app.get("/api/matches")
    async def matches(request: Request, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).matches.season(league, season))

    @app.get("/api/match/{match_id}")
    async def match(request: Request, match_id: int, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).matches.report(match_id, league, season))

    @app.get("/api/search")
    async def search(request: Request, q: str = "", limit: int = Query(8, ge=1, le=20)):
        return ok(await wb(request).search.query(q, limit))

    @app.get("/api/shortlist")
    async def shortlist(request: Request):
        return ok({"items": wb(request).shortlist.items()})

    @app.put("/api/shortlist/{player_id}")
    async def shortlist_put(request: Request, player_id: int, item: ShortlistItem):
        payload = {"id": player_id, **{k: v for k, v in item.model_dump(exclude_unset=True).items() if v is not None}}
        return ok({"items": wb(request).shortlist.add(payload)})

    @app.delete("/api/shortlist/{player_id}")
    async def shortlist_delete(request: Request, player_id: int):
        return ok({"items": wb(request).shortlist.remove(player_id)})

    @app.get("/api/data/status")
    async def data_status(request: Request):
        return ok(await wb(request).data.status())

    @app.post("/api/data/sync")
    async def data_sync(request: Request, body: SyncRequest):
        return ok(wb(request).data.start_sync(body.leagues, body.seasons, body.force))

    @app.post("/api/data/check")
    async def data_check(request: Request):
        return ok(await wb(request).diagnostics.check())

    @app.get("/api/data/auto")
    async def data_auto(request: Request):
        return ok(wb(request).auto.state())

    @app.put("/api/data/auto")
    async def data_auto_set(request: Request, body: AutoPrefs):
        return ok({"prefs": wb(request).auto.set_prefs(body.model_dump(exclude_none=True)), **wb(request).auto.state()})

    @app.post("/api/data/auto/run")
    async def data_auto_run(request: Request):
        wb(request).auto.wake()
        return ok({"started": True})

    # ------------------------------------------------------------------ steering the event fetcher

    @app.get("/api/events/review")
    async def events_review(request: Request, league: str, season: int):
        w = wb(request)
        return ok(await asyncio.to_thread(w.links.review, w.seasons.league_code(league), season))

    @app.put("/api/events/link")
    async def events_link(request: Request, body: EventLink):
        w = wb(request)
        league = w.seasons.league_code(body.league)
        w.links.set_override(league, body.season, body.kind, body.ws, body.us)
        return ok(await asyncio.to_thread(w.links.review, league, body.season))

    @app.post("/api/events/retry")
    async def events_retry(request: Request, body: EventMatch):
        return ok({"queue": wb(request).auto.retry_event_match(body.league, body.season, body.game)})

    @app.post("/api/events/skip")
    async def events_skip(request: Request, body: EventMatch):
        return ok({"entry": wb(request).auto.skip_event_match(body.league, body.season, body.game, bool(body.skip))})

    @app.post("/api/events/pause")
    async def events_pause(request: Request, body: EventPause):
        return ok({"control": wb(request).auto.pause_events(body.paused)})

    @app.post("/api/events/stop")
    async def events_stop(request: Request):
        return ok({"control": wb(request).auto.stop_events()})

    @app.post("/api/data/reclaim")
    async def data_reclaim(request: Request):
        return ok(await wb(request).data.reclaim())

    @app.get("/api/data/jobs/{job_id}")
    async def job(request: Request, job_id: str):
        found = wb(request).jobs.get(job_id)
        if found is None:
            raise AppError("No such job.")
        return ok(found.to_dict())

    # ------------------------------------------------------------------ static frontend

    if WEB_DIR.exists():

        @app.middleware("http")
        async def revalidate_static(request: Request, call_next):
            response = await call_next(request)
            if not request.url.path.startswith("/api"):
                response.headers.setdefault("Cache-Control", "no-cache")
            return response

        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app


app = create_app()
