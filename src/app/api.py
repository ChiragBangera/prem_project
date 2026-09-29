"""HTTP layer: thin routes over the Workbench, uniform errors, static frontend."""

from __future__ import annotations

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


class ShortlistItem(BaseModel):
    name: str = ""
    team: str = ""
    league: str = "EPL"
    note: str | None = None


class SyncRequest(BaseModel):
    leagues: list[str] = Field(default_factory=lambda: ["EPL"])
    seasons: list[int] = Field(default_factory=list)
    force: bool = False


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
        yield
        await app.state.wb.close()

    app = FastAPI(
        title="Prem Lab", version=__version__, lifespan=lifespan, default_response_class=SafeJSONResponse,
        docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
    )
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
        return ok(await wb(request).briefing_view(league, season))

    @app.get("/api/league")
    async def league(request: Request, league: str = "EPL", season: str = "auto", venue: str = "all", last: int | None = Query(None, ge=1, le=40),
                     date_from: str | None = None, date_to: str | None = None):
        return ok(await wb(request).league_view(league, season, venue=venue, last=last, date_from=date_from, date_to=date_to))

    @app.get("/api/team")
    async def team(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team_view(league, season, team))

    @app.get("/api/team/chances")
    async def team_chances(request: Request, team: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).team_chances_view(league, season, team))

    @app.get("/api/players")
    async def players(request: Request, leagues: str = "EPL", seasons: str = "auto", min_minutes: int = Query(90, ge=0, le=3000)):
        return ok(await wb(request).players_view(_list(leagues), _list(seasons) or ["auto"], min_minutes=min_minutes))

    @app.get("/api/player/{player_id}")
    async def player(request: Request, player_id: int, league: str | None = None, season: str = "auto", seasons: str | None = None):
        return ok(await wb(request).player_view(player_id, league, season, _ints(seasons) or None))

    @app.get("/api/player/{player_id}/similar")
    async def similar(request: Request, player_id: int, league: str = "EPL", seasons: str = "", max_age: int | None = None, min_age: int | None = None,
                      min_minutes: int | None = None, other_leagues: str = "", limit: int = Query(12, ge=1, le=30)):
        target_seasons = _ints(seasons)
        if not target_seasons:
            resolved, _ = await wb(request).resolve_season(league, "auto")
            target_seasons = [resolved]
        return ok(await wb(request).similar_view(player_id, league, target_seasons, max_age=max_age, min_age=min_age, min_minutes=min_minutes,
                                                 other_leagues=_list(other_leagues), limit=limit))

    @app.get("/api/compare/players")
    async def compare_players(request: Request, ids: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).compare_players_view(_ints(ids), league, season))

    @app.get("/api/compare/teams")
    async def compare_teams(request: Request, a: str, b: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).compare_teams_view(league, season, a, b))

    @app.get("/api/matches")
    async def matches(request: Request, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).matches_view(league, season))

    @app.get("/api/match/{match_id}")
    async def match(request: Request, match_id: int, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).match_view(match_id, league, season))

    @app.get("/api/forecast/fixtures")
    async def forecast_fixtures(request: Request, league: str = "EPL", season: str = "auto", limit: int = Query(12, ge=1, le=40)):
        return ok(await wb(request).forecast_fixtures_view(league, season, limit))

    @app.get("/api/forecast/match")
    async def forecast_match(request: Request, home: str, away: str, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).forecast_match_view(league, season, home, away))

    @app.get("/api/forecast/season")
    async def forecast_season(request: Request, league: str = "EPL", season: str = "auto", sims: int = Query(4000, ge=500, le=20000)):
        return ok(await wb(request).forecast_season_view(league, season, sims))

    @app.get("/api/forecast/calibration")
    async def forecast_calibration(request: Request, league: str = "EPL", season: str = "auto"):
        return ok(await wb(request).calibration_view(league, season))

    @app.get("/api/search")
    async def search(request: Request, q: str = "", limit: int = Query(8, ge=1, le=20)):
        return ok(await wb(request).search_view(q, limit))

    @app.get("/api/shortlist")
    async def shortlist(request: Request):
        return ok({"items": wb(request).shortlist()})

    @app.put("/api/shortlist/{player_id}")
    async def shortlist_put(request: Request, player_id: int, item: ShortlistItem):
        payload = {"id": player_id, **{k: v for k, v in item.model_dump(exclude_unset=True).items() if v is not None}}
        return ok({"items": wb(request).shortlist_add(payload)})

    @app.delete("/api/shortlist/{player_id}")
    async def shortlist_delete(request: Request, player_id: int):
        return ok({"items": wb(request).shortlist_remove(player_id)})

    @app.get("/api/data/status")
    async def data_status(request: Request):
        return ok(await wb(request).data_status())

    @app.post("/api/data/sync")
    async def data_sync(request: Request, body: SyncRequest):
        return ok(wb(request).start_sync(body.leagues, body.seasons, body.force))

    @app.post("/api/data/check")
    async def data_check(request: Request):
        return ok(await wb(request).check_connection())

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
