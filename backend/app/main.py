"""AZAERON FastAPI application."""

from contextlib import asynccontextmanager

import time
import re
import secrets
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.database import init_db, close_db, engine
from app.core.logging import configure_logging, get_logger
from app.api.v1 import api_router
from app.core.dependencies import rate_limiter
from app.core.health import readiness_report, refresh_operational_metrics
from app.core.observability import (
    configure_database_metrics,
    configure_tracing,
    record_api_request,
    shutdown_tracing,
    stable_route,
)
from app.core.request_context import correlation_id_ctx, request_id_ctx
from opentelemetry.trace import Status, StatusCode

# Register the complete SQLAlchemy relationship graph before the first request.
# Individual route imports otherwise leave string-based relationships unresolved.
import app.models as registered_models  # noqa: F401

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    configure_database_metrics(engine)
    logger.info("azaeron_starting", version=settings.APP_VERSION)
    from app.modules.inference.service import validate_inference_startup

    validate_inference_startup()
    from app.modules.auth.identity import validate_identity_startup

    validate_identity_startup()
    from app.modules.billing.usage import cipher as usage_cipher

    usage_cipher()
    await init_db()
    yield
    await close_db()
    shutdown_tracing()
    logger.info("azaeron_shutting_down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Privacy-first writing intelligence with reviewable evidence",
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=(
        ["*"] if settings.ENVIRONMENT == "development" else settings.TRUSTED_HOSTS
    ),
)


@app.middleware("http")
async def protect_browser_cookie_requests(request: Request, call_next):
    """Reject unsafe, cookie-authenticated cross-origin browser requests."""
    unsafe_method = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    uses_cookie_auth = bool(
        request.cookies.get("access_token") or request.cookies.get("refresh_token")
    )
    uses_bearer = bool(
        re.fullmatch(
            r"Bearer [^\s]+",
            request.headers.get("authorization", ""),
            flags=re.IGNORECASE,
        )
    )
    # Authentication bootstrap endpoints do not act on an authenticated
    # browser session. Exempting them prevents a stale session cookie from
    # blocking signup/login/rotation while keeping CSRF protection on all
    # tenant and account mutation endpoints.
    auth_bootstrap_path = request.url.path in {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
        "/api/v1/auth/verification/confirm",
    }
    origin = request.headers.get("origin")
    # Refresh always consumes a cookie unless the caller explicitly supplies a
    # body token; a bearer header must never disable protection for this route.
    cookie_mutation = uses_cookie_auth and (
        (not uses_bearer and request.headers.get("x-api-key") is None)
        or request.url.path == "/api/v1/auth/refresh"
    )
    if unsafe_method and (
        cookie_mutation and not auth_bootstrap_path or origin is not None
    ):
        if not origin or origin not in settings.CORS_ORIGINS:
            return JSONResponse(
                status_code=403,
                content={"detail": "Cross-origin cookie request rejected"},
            )

    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Correlate every response, including CSRF and admission denials."""
    from app.core.observability import TRACE_CONTEXT, opaque_id, safe_span
    from opentelemetry.trace import SpanKind
    from structlog.contextvars import bind_contextvars, clear_contextvars

    request_id = opaque_id(request.headers.get("X-Request-ID")) or str(uuid.uuid4())
    correlation_id = opaque_id(request.headers.get("X-Correlation-ID")) or request_id
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    request_token = request_id_ctx.set(request_id)
    correlation_token = correlation_id_ctx.set(correlation_id)
    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        correlation_id=correlation_id,
        release_id=settings.RELEASE_ID,
    )
    started = time.perf_counter()
    method = (
        request.method
        if request.method
        in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        else "OTHER"
    )
    try:
        with safe_span(
            "HTTP " + method,
            context=TRACE_CONTEXT.extract(dict(request.headers)),
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": method,
                "request.id": request_id,
                "correlation.id": correlation_id,
                "release.id": settings.RELEASE_ID,
            },
        ) as span:
            trace_id = format(span.get_span_context().trace_id, "032x")
            bind_contextvars(trace_id=trace_id)
            try:
                if request.url.path not in {
                    "/health",
                    "/health/live",
                    "/health/ready",
                    "/metrics",
                }:
                    await rate_limiter(request)
                response = await call_next(request)
            except HTTPException as exc:
                response = JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                response = await global_exception_handler(request, exc)
            route = stable_route(request)
            span.update_name(method + " " + route)
            span.set_attribute("http.route", route)
            span.set_attribute("http.response.status_code", response.status_code)
            if response.status_code >= 500:
                span.set_status(Status(StatusCode.ERROR))
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            response.headers["X-Release-ID"] = settings.RELEASE_ID
            if span.get_span_context().is_valid:
                response.headers["X-Trace-ID"] = trace_id
            record_api_request(
                method, route, response.status_code, time.perf_counter() - started
            )
            return response
    finally:
        request_id_ctx.reset(request_token)
        correlation_id_ctx.reset(correlation_token)
        clear_contextvars()


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        request_id=getattr(request.state, "request_id", None),
        correlation_id=getattr(request.state, "correlation_id", None),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


app.include_router(api_router, prefix="/api")


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics at the canonical, non-redirecting path."""
    if settings.ENVIRONMENT == "production" or settings.METRICS_TOKEN:
        authorization = request.headers.get("authorization", "")
        supplied = authorization.removeprefix("Bearer ").strip()
        if not settings.METRICS_TOKEN or not secrets.compare_digest(
            supplied, settings.METRICS_TOKEN
        ):
            return JSONResponse(
                status_code=401, content={"detail": "Metrics authentication required"}
            )
    await refresh_operational_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.APP_VERSION}


@app.get("/health/live")
async def liveness_check():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    report = await readiness_report()
    if report["status"] != "ready":
        return JSONResponse(status_code=503, content=report)
    return report


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "description": "Privacy-first writing intelligence with reviewable evidence",
        "status": "incomplete",
    }


def public_openapi():
    from fastapi.openapi.utils import get_openapi
    from app.modules.auth.api_keys import scope_for_route

    if app.openapi_schema is None:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        for path, operations in schema["paths"].items():
            for method, operation in operations.items():
                if not isinstance(operation, dict):
                    continue
                required = scope_for_route(method.upper(), path)
                if required:
                    operation["x-api-key-scopes"] = [required]
                else:
                    operation["security"] = [
                        item
                        for item in operation.get("security", [])
                        if "AzaeronAPIKey" not in item
                    ]
        app.openapi_schema = schema
    return app.openapi_schema


setattr(app, "openapi", public_openapi)
