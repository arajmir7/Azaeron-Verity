"""Bounded metrics, correlation context, and OpenTelemetry tracing.

This module is intentionally infrastructure-only.  Metrics use stable labels
such as route templates, queue names, and task types; raw IDs, URLs, SQL, and
tenant identifiers are never emitted as metric labels.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import UUID

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import time
from typing import Any, Iterator

from prometheus_client import Counter, Gauge, Histogram

from app.core.config import settings

API_REQUESTS = Counter(
    "azaeron_api_requests_total",
    "HTTP requests handled by the API.",
    ("method", "route", "status"),
)
API_ERRORS = Counter(
    "azaeron_api_errors_total",
    "HTTP 4xx/5xx responses by stable route template.",
    ("method", "route", "status_class"),
)
API_LATENCY = Histogram(
    "azaeron_api_request_duration_seconds",
    "HTTP request latency in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 2, 5, 10, 30, 60),
)

DB_QUERIES = Counter(
    "azaeron_db_queries_total",
    "SQL statements executed by operation class.",
    ("operation",),
)
DB_QUERY_ERRORS = Counter(
    "azaeron_db_query_errors_total",
    "SQL statement failures by operation class.",
    ("operation",),
)
DB_LATENCY = Histogram(
    "azaeron_db_query_duration_seconds",
    "SQL statement latency in seconds.",
    ("operation",),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
DB_POOL_SIZE = Gauge("azaeron_db_pool_size", "Configured database pool size.")
DB_POOL_CHECKED_OUT = Gauge(
    "azaeron_db_pool_checked_out", "Database connections currently checked out."
)
DB_POOL_OVERFLOW = Gauge(
    "azaeron_db_pool_overflow", "Database pool overflow connections currently in use."
)

REDIS_OPERATIONS = Counter(
    "azaeron_redis_operations_total",
    "Redis operations by outcome.",
    ("operation", "outcome"),
)
REDIS_HEALTH = Gauge("azaeron_redis_health", "Redis health: 1 healthy, 0 unhealthy.")

QUEUE_DEPTH = Gauge(
    "azaeron_queue_depth", "Current Redis/Celery queue depth.", ("queue",)
)
WORKER_HEALTH = Gauge(
    "azaeron_worker_health",
    "Healthy Celery workers observed by control ping.",
    ("queue",),
)
WORKER_COUNT = Gauge(
    "azaeron_worker_count", "Number of Celery workers responding to ping."
)

JOB_ACTIVE = Gauge(
    "azaeron_jobs_active",
    "Jobs currently being processed.",
    ("job_type",),
    multiprocess_mode="livesum",
)
JOB_DURATION = Histogram(
    "azaeron_job_duration_seconds",
    "Background job duration in seconds.",
    ("job_type", "status"),
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 900, 1800),
)
JOB_RETRIES = Counter(
    "azaeron_job_retries_total", "Background job retries.", ("job_type",)
)
JOB_FAILURES = Counter(
    "azaeron_job_failures_total", "Background job terminal failures.", ("job_type",)
)
DEAD_LETTERED = Counter(
    "azaeron_dead_lettered_jobs_total",
    "Jobs written to the dead-letter queue.",
    ("job_type",),
)

STORAGE_OPERATIONS = Counter(
    "azaeron_storage_operations_total",
    "Object-storage operations by operation and outcome.",
    ("operation", "outcome"),
)
STORAGE_LATENCY = Histogram(
    "azaeron_storage_operation_duration_seconds",
    "Object-storage operation latency in seconds.",
    ("operation",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)

ML_INFERENCE_LATENCY = Histogram(
    "azaeron_ml_inference_duration_seconds",
    "AI-writing inference latency in seconds.",
    ("pipeline", "outcome"),
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)


def stable_route(request: Any) -> str:
    """Return a bounded route-template label after routing has completed."""
    route = getattr(request, "scope", {}).get("route")
    template = getattr(route, "path", None)
    if not template:
        return "/unmatched"
    # FastAPI nested routers expose the local template in scope["route"].
    if request.url.path.startswith("/api/v1/") and not template.startswith("/api/v1/"):
        return "/api/v1" + template
    return template


def record_api_request(
    method: str, route: str, status_code: int, duration: float
) -> None:
    method = (
        method
        if method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        else "OTHER"
    )
    status = str(status_code)
    API_REQUESTS.labels(method, route, status).inc()
    API_LATENCY.labels(method, route).observe(duration)
    if status_code in {401, 403}:
        AUTH_DENIALS.labels(route, status).inc()
    if status_code == 429:
        RATE_LIMITS.labels(route).inc()
    if status_code >= 400:
        API_ERRORS.labels(method, route, f"{status_code // 100}xx").inc()


def record_redis(operation: str, outcome: str) -> None:
    REDIS_OPERATIONS.labels(operation, outcome).inc()


def record_storage(operation: str, outcome: str, duration: float) -> None:
    STORAGE_OPERATIONS.labels(operation, outcome).inc()
    STORAGE_LATENCY.labels(operation).observe(duration)


def record_job_started(job_type: str) -> None:
    JOB_ACTIVE.labels(job_type).inc()


def record_job_finished(job_type: str, status: str, duration: float) -> None:
    JOB_ACTIVE.labels(job_type).dec()
    JOB_DURATION.labels(job_type, status).observe(duration)
    if status == "failed":
        JOB_FAILURES.labels(job_type).inc()


def record_job_retry(job_type: str) -> None:
    JOB_RETRIES.labels(job_type).inc()


def record_dead_letter(job_type: str) -> None:
    DEAD_LETTERED.labels(job_type).inc()


@contextmanager
def timed_ml_inference(
    pipeline: str = "ai-writing", outcome: str = "success"
) -> Iterator[dict[str, str]]:
    """Observe a detector inference without leaking document or tenant IDs."""
    started = time.perf_counter()
    state = {"outcome": outcome}
    try:
        yield state
    except Exception:
        state["outcome"] = "error"
        raise
    finally:
        ML_INFERENCE_LATENCY.labels(pipeline, state["outcome"]).observe(
            time.perf_counter() - started
        )


def configure_database_metrics(engine: Any) -> None:
    """Attach SQLAlchemy engine/pool metrics once to the application engine."""
    from sqlalchemy import event

    sync_engine = engine.sync_engine
    if getattr(sync_engine, "_azaeron_metrics_configured", False):
        return
    sync_engine._azaeron_metrics_configured = True

    def operation(statement: str) -> str:
        first = (
            (statement or "").lstrip().split(None, 1)[0].upper()
            if statement
            else "OTHER"
        )
        return (
            first
            if first
            in {"SELECT", "INSERT", "UPDATE", "DELETE", "BEGIN", "COMMIT", "ROLLBACK"}
            else "OTHER"
        )

    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        context._azaeron_query_started = time.perf_counter()
        context._azaeron_query_operation = operation(statement)
        context._azaeron_span = trace.get_tracer("azaeron.database").start_span(
            "db." + context._azaeron_query_operation,
            kind=SpanKind.CLIENT,
            attributes={
                "db.operation.name": context._azaeron_query_operation,
                "db.system.name": sync_engine.dialect.name,
            },
        )

    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        op = getattr(context, "_azaeron_query_operation", "OTHER")
        context._azaeron_span.end()
        DB_QUERIES.labels(op).inc()
        DB_LATENCY.labels(op).observe(
            time.perf_counter()
            - getattr(context, "_azaeron_query_started", time.perf_counter())
        )

    def handle_error(exception_context):
        execution_context = getattr(exception_context, "execution_context", None)
        op = getattr(execution_context, "_azaeron_query_operation", "OTHER")
        span = getattr(execution_context, "_azaeron_span", None)
        if span is not None:
            span.set_status(Status(StatusCode.ERROR))
            span.end()
        DB_QUERY_ERRORS.labels(op).inc()

    def pool_checkout(dbapi_conn, connection_record, connection_proxy):
        _update_pool_metrics(engine)

    def pool_checkin(dbapi_conn, connection_record):
        _update_pool_metrics(engine)

    event.listen(sync_engine, "before_cursor_execute", before_cursor_execute)
    event.listen(sync_engine, "after_cursor_execute", after_cursor_execute)
    event.listen(sync_engine, "handle_error", handle_error)
    event.listen(sync_engine.pool, "checkout", pool_checkout)
    event.listen(sync_engine.pool, "checkin", pool_checkin)
    _update_pool_metrics(engine)


def _update_pool_metrics(engine: Any) -> None:
    pool = getattr(engine.sync_engine, "pool", None)
    if pool is None:
        return
    for metric, method, default in (
        (DB_POOL_SIZE, "size", 0),
        (DB_POOL_CHECKED_OUT, "checkedout", 0),
        (DB_POOL_OVERFLOW, "overflow", 0),
    ):
        try:
            metric.set(float(max(0, getattr(pool, method)())))
        except (AttributeError, TypeError):
            metric.set(default)


_tracer_provider: Any = None


def configure_tracing() -> Any:
    """Configure OTLP tracing when the SDK is installed and an endpoint exists."""
    global _tracer_provider
    if _tracer_provider is not None:
        return _tracer_provider
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return None

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment": settings.ENVIRONMENT,
            "release.id": settings.RELEASE_ID,
        }
    )
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO)),
    )
    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(
                        endpoint=endpoint,
                        insecure=settings.OTEL_EXPORTER_OTLP_INSECURE,
                        timeout=settings.OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS,
                    )
                )
            )
        except ImportError:
            # The SDK still produces spans for in-process instrumentation. The
            # startup log and readiness metadata make missing export explicit.
            pass
    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    return provider


def shutdown_tracing() -> None:
    if _tracer_provider is not None:
        _tracer_provider.shutdown()


AUTH_DENIALS = Counter(
    "azaeron_authorization_denials_total",
    "Rejected authentication/authorization requests.",
    ("route", "status"),
)
RATE_LIMITS = Counter(
    "azaeron_rate_limit_events_total",
    "Rejected rate/concurrency admission requests.",
    ("route",),
)
FRONTEND_ERRORS = Counter(
    "azaeron_frontend_errors_total",
    "Bounded browser error reports; never messages or stacks.",
    ("kind", "route"),
)
INFERENCE_CALLS = Counter(
    "azaeron_inference_calls_total",
    "Private gateway calls by task and outcome.",
    ("task", "outcome"),
)
DEPENDENCY_HEALTH = Gauge(
    "azaeron_dependency_health",
    "Last active dependency probe: 1 healthy, 0 unhealthy.",
    ("dependency",),
)
TRACE_CONTEXT = TraceContextTextMapPropagator()


def opaque_id(value: Any) -> str | None:
    """Only UUIDs enter propagated operation/job/request correlation fields."""
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def trace_headers() -> dict[str, str]:
    from app.core.request_context import request_id_ctx

    carrier: dict[str, str] = {}
    TRACE_CONTEXT.inject(carrier)
    request_id = opaque_id(request_id_ctx.get())
    if request_id:
        carrier["verity_request_id"] = request_id
    return carrier


@contextmanager
def safe_span(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    context=None,
    kind=SpanKind.INTERNAL,
):
    """Callers supply fixed names and reviewed metadata, never exception values."""
    with trace.get_tracer("azaeron").start_as_current_span(
        name,
        attributes=attributes,
        context=context,
        kind=kind,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        try:
            yield span
        except BaseException:
            span.set_status(Status(StatusCode.ERROR))
            raise


@contextmanager
def inference_telemetry(task: str, operation_id: str):
    started = time.perf_counter()
    outcome = "error"
    with safe_span(
        "inference.gateway",
        attributes={"inference.task": task, "operation.id": operation_id},
    ):
        try:
            yield
            outcome = "success"
        finally:
            INFERENCE_CALLS.labels(task, outcome).inc()
            ML_INFERENCE_LATENCY.labels("private-" + task, outcome).observe(
                time.perf_counter() - started
            )
