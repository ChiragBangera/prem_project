from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictBool, model_validator

from app import __version__
from app.analytics_service import AnalyticsService
from app.endpoint_manifest import get_endpoint_manifest, get_endpoint_spec
from app.endpoint_runner import EndpointRunner
from app.errors import UnderstatRequestError
from app.prediction_service import PredictionService
from app.question_answering import FootballQuestionAnswerer
from app.stat_data import UnderstatData
from app.utils.utils import get_current_season


PROJECT_SUMMARY = "Evidence-backed football analytics powered by Understat data."


class QuestionRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=500,
        examples=["Compare Arsenal vs Liverpool"],
    )


class EndpointRequest(BaseModel):
    params: dict[str, Any] = Field(
        default_factory=dict,
        examples=[{"league_name": "EPL", "season": 2026}],
    )


class ProjectInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    docs: str
    health: str
    api: str
    dashboard: str
    data_source: str
    affiliation: str


class HealthResponse(BaseModel):
    status: str
    version: str


class EndpointSpecResponse(BaseModel):
    name: str
    method_name: str
    category: str
    description: str
    required_params: tuple[str, ...]
    optional_params: tuple[str, ...]
    example: str


class EndpointListResponse(BaseModel):
    endpoints: list[EndpointSpecResponse]


class EndpointExecutionResponse(BaseModel):
    endpoint: str
    params: dict[str, Any]
    data: Any


class QuestionResponse(BaseModel):
    plan: dict[str, Any]
    answer: dict[str, Any]
    data_summary: dict[str, Any]
    template: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: str
    upstream_status: int | None = None


def _cors_origins() -> list[str]:
    configured = os.getenv("FOOTBALL_ANALYTICS_CORS_ORIGINS", "*")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    return origins or ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = UnderstatData()
    app.state.client = client
    app.state.runner = EndpointRunner(client=client)
    app.state.answerer = FootballQuestionAnswerer(client=client)
    from .analytics.enrichment import provider_from_env

    app.state.analytics = AnalyticsService(client=client, enrichment=provider_from_env())
    app.state.predictions = PredictionService(client=client)
    yield
    await client.close()


app = FastAPI(
    title="Premier League Analytics API",
    summary=PROJECT_SUMMARY,
    description=(
        "A portfolio analytics API for exploring league, team, player, match, "
        "and natural-language analytical questions. This project is unofficial "
        "and is not affiliated with Understat."
    ),
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

cors_origins = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount(
    "/dashboard",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "dashboard"), html=True),
    name="dashboard",
)


@app.exception_handler(UnderstatRequestError)
async def understat_error_handler(_: Request, exc: UnderstatRequestError):
    return JSONResponse(
        status_code=502,
        content={
            "error": "upstream_service_error",
            "detail": str(exc),
            "upstream_status": exc.status_code,
        },
    )


@app.get("/", tags=["Project"], response_model=ProjectInfoResponse)
async def project_info():
    return {
        "name": app.title,
        "version": __version__,
        "description": PROJECT_SUMMARY,
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
        "dashboard": "/dashboard/",
        "data_source": "Understat",
        "affiliation": "Unofficial project",
    }


@app.get("/health", tags=["Project"], response_model=HealthResponse)
async def health_check():
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/glossary", tags=["Project"])
async def glossary():
    from app.analytics.glossary import glossary_response
    return glossary_response()


@app.get("/api/v1/endpoints", tags=["Data"], response_model=EndpointListResponse)
async def list_endpoints():
    return {
        "endpoints": [
            asdict(spec)
            for _, spec in sorted(get_endpoint_manifest().items())
        ]
    }


@app.get(
    "/api/v1/endpoints/{endpoint_name}",
    tags=["Data"],
    response_model=EndpointSpecResponse,
    responses={404: {"model": ErrorResponse}},
)
async def describe_endpoint(endpoint_name: str):
    try:
        return asdict(get_endpoint_spec(endpoint_name))
    except KeyError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "endpoint_not_found", "detail": str(exc)},
        )


@app.post(
    "/api/v1/endpoints/{endpoint_name}",
    tags=["Data"],
    response_model=EndpointExecutionResponse,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def run_endpoint(endpoint_name: str, payload: EndpointRequest, request: Request):
    try:
        result = await request.app.state.runner.run(endpoint_name, **payload.params)
        return {"endpoint": endpoint_name, "params": payload.params, "data": result}
    except KeyError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "endpoint_not_found", "detail": str(exc)},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/ask",
    tags=["Analytics"],
    response_model=QuestionResponse,
    responses={502: {"model": ErrorResponse}},
)
async def ask_question(payload: QuestionRequest, request: Request):
    return await request.app.state.answerer.answer(payload.question)


class AnalyzePlayerRequest(BaseModel):
    player_id: int | None = None
    player_name: str | None = None
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    start_date: str | None = None
    end_date: str | None = None
    seasons: list[int] | str | None = None


class CareerRequest(BaseModel):
    player_name: str | None = None
    player_id: int | None = None
    league_name: str = "EPL"
    seasons: list[int] | None = None
    season_end: int | None = None


class ComparePlayersRequest(BaseModel):
    player_1: str | None = None
    player_2: str | None = None
    players: list[str] | None = None
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    start_date: str | None = None
    end_date: str | None = None


class CompareTeamsRequest(BaseModel):
    team_1: str
    team_2: str
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    start_date: str | None = None
    end_date: str | None = None


class AnalyzeTeamRequest(BaseModel):
    team_name: str
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    with_shots: bool = False
    start_date: str | None = None
    end_date: str | None = None
    seasons: list[int] | str | None = None


class TeamTimelineRequest(BaseModel):
    team_name: str
    league_name: str = "EPL"
    seasons: list[int] | None = None
    season_end: int | None = None


class AnalyzeLeagueRequest(BaseModel):
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    start_date: str | None = None
    end_date: str | None = None


class DiscoverPlayersRequest(BaseModel):
    model_config = {"extra": "forbid"}

    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    position_group: str | None = None
    positions: list[str] | None = None
    minimum_minutes: float = 900
    order_by: str = "npxG"
    limit: int = 20
    start_date: str | None = None
    end_date: str | None = None
    seasons: list[int] | str | None = None
    min_age: int | None = None
    max_age: int | None = None
    per90_sort: StrictBool = False
    min_npxG_per90: float | None = Field(default=None, ge=0, le=5)
    min_xA_per90: float | None = Field(default=None, ge=0, le=5)
    min_xGChain_per90: float | None = Field(default=None, ge=0, le=5)
    min_xGBuildup_per90: float | None = Field(default=None, ge=0, le=5)
    template_player_name: str | None = None
    template_player_id: int | None = None

    @model_validator(mode="after")
    def _validate_template_exclusive(self):
        if self.template_player_name is not None and self.template_player_id is not None:
            raise ValueError("template_player_name and template_player_id are exclusive (provide only one)")
        if isinstance(self.template_player_name, str) and not self.template_player_name.strip():
            object.__setattr__(self, "template_player_name", None)
        return self


@app.post(
    "/api/v1/analyze/player",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def analyze_player(payload: AnalyzePlayerRequest, request: Request):
    try:
        return await request.app.state.analytics.analyze_player(
            player_id=payload.player_id,
            player_name=payload.player_name,
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
            seasons=payload.seasons,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/player/shots",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def player_shots(payload: AnalyzePlayerRequest, request: Request):
    try:
        return await request.app.state.analytics.player_shot_map(
            player_id=payload.player_id,
            player_name=payload.player_name,
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
            seasons=payload.seasons,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/player/career",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def player_career(payload: CareerRequest, request: Request):
    try:
        return await request.app.state.analytics.player_career(
            player_name=payload.player_name,
            player_id=payload.player_id,
            league_name=payload.league_name,
            seasons=payload.seasons,
            season_end=payload.season_end,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/team/timeline",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def team_timeline(payload: TeamTimelineRequest, request: Request):
    try:
        return await request.app.state.analytics.team_timeline(
            team_name=payload.team_name,
            league_name=payload.league_name,
            seasons=payload.seasons,
            season_end=payload.season_end,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/compare/players",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def compare_players(payload: ComparePlayersRequest, request: Request):
    try:
        return await request.app.state.analytics.compare_players(
            player_1=payload.player_1,
            player_2=payload.player_2,
            players=payload.players,
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/compare/teams",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def compare_teams(payload: CompareTeamsRequest, request: Request):
    try:
        return await request.app.state.analytics.compare_teams(
            team_1=payload.team_1,
            team_2=payload.team_2,
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/team",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def analyze_team(payload: AnalyzeTeamRequest, request: Request):
    try:
        return await request.app.state.analytics.analyze_team(
            team_name=payload.team_name,
            league_name=payload.league_name,
            season=payload.season,
            with_shots=payload.with_shots,
            start_date=payload.start_date,
            end_date=payload.end_date,
            seasons=payload.seasons,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/team/shots",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def team_shots(payload: AnalyzeTeamRequest, request: Request):
    try:
        return await request.app.state.analytics.team_shot_map(
            team_name=payload.team_name,
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
            seasons=payload.seasons,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/analyze/league",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def analyze_league(payload: AnalyzeLeagueRequest, request: Request):
    try:
        return await request.app.state.analytics.analyze_league(
            league_name=payload.league_name,
            season=payload.season,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/matches/rounds",
    tags=["Analytics"],
    responses={502: {"model": ErrorResponse}},
)
async def match_rounds(payload: AnalyzeLeagueRequest, request: Request):
    return await request.app.state.analytics.match_rounds(
        league_name=payload.league_name,
        season=payload.season,
    )


@app.post(
    "/api/v1/matches/live",
    tags=["Analytics"],
    responses={502: {"model": ErrorResponse}},
)
async def match_live(payload: AnalyzeLeagueRequest, request: Request):
    return await request.app.state.analytics.match_live(
        league_name=payload.league_name,
        season=payload.season,
    )


@app.post(
    "/api/v1/analyze/match/{match_id}",
    tags=["Analytics"],
    responses={502: {"model": ErrorResponse}},
)
async def analyze_match(match_id: int, request: Request):
    return await request.app.state.analytics.analyze_match(match_id)


@app.post(
    "/api/v1/discover/players",
    tags=["Analytics"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def discover_players(payload: DiscoverPlayersRequest, request: Request):
    try:
        return await request.app.state.analytics.discover_players(
            league_name=payload.league_name,
            season=payload.season,
            position_group=payload.position_group,
            minimum_minutes=payload.minimum_minutes,
            order_by=payload.order_by,
            limit=payload.limit,
            start_date=payload.start_date,
            end_date=payload.end_date,
            seasons=payload.seasons,
            min_age=payload.min_age,
            max_age=payload.max_age,
            positions=payload.positions,
            per90_sort=payload.per90_sort,
            min_npxG_per90=payload.min_npxG_per90,
            min_xA_per90=payload.min_xA_per90,
            min_xGChain_per90=payload.min_xGChain_per90,
            min_xGBuildup_per90=payload.min_xGBuildup_per90,
            template_player_name=payload.template_player_name,
            template_player_id=payload.template_player_id,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


class PredictMatchRequest(BaseModel):
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    home: str
    away: str
    use_xg: bool = True
    pool_leagues: bool = True

    @model_validator(mode="before")
    @classmethod
    def _accept_team_aliases(cls, data: Any) -> Any:
        """Backward compatibility both ways: accept home_team/away_team as aliases.

        The dashboard sends home_team/away_team; earlier API clients send
        home/away. Canonical home/away always wins when both are present.
        """
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if "home" not in normalized and "home_team" in normalized:
            normalized["home"] = normalized["home_team"]
        normalized.pop("home_team", None)
        if "away" not in normalized and "away_team" in normalized:
            normalized["away"] = normalized["away_team"]
        normalized.pop("away_team", None)
        return normalized


class SimulateSeasonRequest(BaseModel):
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    n_sims: int = 2000
    use_xg: bool = True


class CalibrateRequest(BaseModel):
    league_name: str = "EPL"
    season: int = Field(default_factory=get_current_season)
    use_xg: bool = True
    min_train: int = 30
    step: int = 5
    pool_leagues: bool = True


@app.post(
    "/api/v1/predict/match",
    tags=["Predictions"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def predict_match(payload: PredictMatchRequest, request: Request):
    try:
        return await request.app.state.predictions.predict_match(
            league_name=payload.league_name,
            season=payload.season,
            home=payload.home,
            away=payload.away,
            use_xg=payload.use_xg,
            pool_leagues=payload.pool_leagues,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/predict/season",
    tags=["Predictions"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def simulate_season(payload: SimulateSeasonRequest, request: Request):
    try:
        return await request.app.state.predictions.simulate_season(
            league_name=payload.league_name,
            season=payload.season,
            n_sims=payload.n_sims,
            use_xg=payload.use_xg,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )


@app.post(
    "/api/v1/predict/calibration",
    tags=["Predictions"],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def calibrate(payload: CalibrateRequest, request: Request):
    try:
        return await request.app.state.predictions.calibrate(
            league_name=payload.league_name,
            season=payload.season,
            use_xg=payload.use_xg,
            min_train=payload.min_train,
            step=payload.step,
            pool_leagues=payload.pool_leagues,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_parameters", "detail": str(exc)},
        )
