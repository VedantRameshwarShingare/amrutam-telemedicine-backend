from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.api.router import api_router
from app.common.exceptions import (
    AppException,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ValidationError,
)
from app.core.base import Base
from app.core.config import settings
from app.core.database import engine
from app.core.logging import logger
from app.core.observability import (
    http_errors_total,
    http_request_duration_seconds,
    http_requests_total,
)
from app.core.telemetry import instrument_application


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if settings.app_env.lower() not in {"prod", "production"}:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Amrutam Telemedicine System API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

_CORRELATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

instrument_application(app, engine)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    requested_correlation_id = request.headers.get("X-Correlation-ID", "")
    correlation_id = (
        requested_correlation_id
        if _CORRELATION_ID_PATTERN.fullmatch(requested_correlation_id)
        else str(uuid4())
    )
    bind_contextvars(correlation_id=correlation_id)
    started = perf_counter()
    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = perf_counter() - started
        route = request.scope.get("route")
        route_name = getattr(route, "path", request.url.path)
        http_requests_total.labels(request.method, route_name, str(status_code)).inc()
        if status_code >= 400:
            http_errors_total.labels(request.method, route_name, str(status_code)).inc()
        http_request_duration_seconds.labels(request.method, route_name).observe(duration)
        logger.info(
            "http_request",
            method=request.method,
            route=route_name,
            status_code=status_code,
            duration_ms=round(duration * 1000, 2),
        )
        if response is not None:
            response.headers["X-Correlation-ID"] = correlation_id
        clear_contextvars()


@app.exception_handler(AuthenticationError)
async def authentication_exception_handler(request: Request, exc: AuthenticationError) -> Response:
    return error_response(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_ERROR", exc.message)


@app.exception_handler(AuthorizationError)
async def authorization_exception_handler(request: Request, exc: AuthorizationError) -> Response:
    return error_response(status.HTTP_403_FORBIDDEN, "FORBIDDEN", exc.message)


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_exception_handler(
    request: Request, exc: ResourceNotFoundError
) -> Response:
    return error_response(status.HTTP_404_NOT_FOUND, "NOT_FOUND", exc.message)


@app.exception_handler(ConflictError)
async def conflict_exception_handler(request: Request, exc: ConflictError) -> Response:
    return error_response(status.HTTP_409_CONFLICT, "CONFLICT", exc.message)


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError) -> Response:
    return error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        exc.message,
    )


@app.exception_handler(RateLimitExceededError)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceededError) -> Response:
    return error_response(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "RATE_LIMIT_EXCEEDED",
        exc.message,
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> Response:
    return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", exc.message)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
