from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import __version__
from app.endpoint_manifest import get_endpoint_manifest, get_endpoint_spec
from app.endpoint_runner import EndpointRunner
from app.errors import UnderstatRequestError
from app.question_answering import FootballQuestionAnswerer
from app.stat_data import UnderstatData


PROJECT_SUMMARY = "Evidence-backed football analytics powered by Understat data."


class QuestionRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=500,
        examples=["Compare Arsenal vs Liverpool in 2025"],
    )


class EndpointRequest(BaseModel):
    params: dict[str, Any] = Field(
        default_factory=dict,
        examples=[{"league_name": "EPL", "season": 2025}],
    )


class ProjectInfoResponse(BaseModel):
    name: str
    version: str
    description: str
    docs: str
    health: str
    api: str
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


@app.exception_handler(UnderstatRequestError)
async def understat_error_handler(_: Request, exc: UnderstatRequestError):
    return JSONResponse(
        status_code=502,
        content={
            "error": "upstream_data_error",
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
        "data_source": "Understat",
        "affiliation": "Unofficial project",
    }


@app.get("/health", tags=["Project"], response_model=HealthResponse)
async def health_check():
    return {"status": "ok", "version": __version__}


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
