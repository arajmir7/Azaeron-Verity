"""Celery lifecycle hooks: initialize OTLP after fork and propagate safe context."""

import os
import time
from pathlib import Path

from prometheus_client import Counter, Histogram
from celery import signals
from opentelemetry import context, trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from structlog.contextvars import bind_contextvars, clear_contextvars
from app.core.config import settings
from app.core.observability import (
    TRACE_CONTEXT,
    configure_tracing,
    opaque_id,
    shutdown_tracing,
)
from app.core.request_context import request_id_ctx

TASKS = Counter(
    "azaeron_celery_tasks_total",
    "All registered tasks by terminal delivery state.",
    ("task", "state"),
)
TASK_LATENCY = Histogram(
    "azaeron_celery_task_duration_seconds",
    "All task delivery latency.",
    ("task",),
    buckets=(0.01, 0.1, 1, 10, 60, 300, 900),
)


@signals.worker_init.connect
def start_metrics(**kwargs):
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return
    from prometheus_client import CollectorRegistry, multiprocess, start_http_server

    registry = CollectorRegistry()

    class LiveCollector(multiprocess.MultiProcessCollector):
        def collect(self):
            # SIGKILL can bypass Celery's shutdown signal. Prune stale live
            # gauges at scrape time, keeping dead-process counters intact.
            for file in Path(os.environ["PROMETHEUS_MULTIPROC_DIR"]).glob(
                "gauge_live*.db"
            ):
                pid = int(file.stem.rsplit("_", 1)[1])
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    multiprocess.mark_process_dead(pid)
            yield from super().collect()

    LiveCollector(registry)
    # Internal Compose network only; never publish this port to the host.
    start_http_server(9100, registry=registry)


@signals.worker_process_init.connect
def child_started(**kwargs):
    configure_tracing()


@signals.worker_process_shutdown.connect
def child_stopped(pid=None, **kwargs):
    shutdown_tracing()
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(pid or os.getpid())


@signals.task_prerun.connect
def task_started(task=None, **kwargs):
    headers = task.request.headers or {}
    request_id = opaque_id(headers.get("verity_request_id"))
    name = task.name.rsplit(".", 1)[-1]
    # Only registered task names, not arguments, become span names/attributes.
    span = trace.get_tracer("azaeron.worker").start_span(
        "celery." + name,
        context=TRACE_CONTEXT.extract(headers),
        kind=SpanKind.CONSUMER,
        attributes={"celery.task": name, "release.id": settings.RELEASE_ID},
    )
    if request_id:
        span.set_attribute("request.id", request_id)
    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        trace_id=format(span.get_span_context().trace_id, "032x"),
        release_id=settings.RELEASE_ID,
    )
    task.request._verity_telemetry = (
        span,
        context.attach(trace.set_span_in_context(span)),
        request_id_ctx.set(request_id),
        time.perf_counter(),
    )


@signals.task_postrun.connect
def task_finished(task=None, state=None, **kwargs):
    state_data = getattr(task.request, "_verity_telemetry", None)
    if state_data is None:
        return
    span, token, request_token, started = state_data
    task_name = task.name.rsplit(".", 1)[-1]
    outcome = (
        state if state in {"SUCCESS", "FAILURE", "RETRY", "REVOKED"} else "UNKNOWN"
    )
    TASKS.labels(task_name, outcome).inc()
    TASK_LATENCY.labels(task_name).observe(time.perf_counter() - started)
    if state in {"FAILURE", "REVOKED", "RETRY"}:
        span.set_status(Status(StatusCode.ERROR))
    span.set_attribute("celery.state", state or "UNKNOWN")
    span.end()
    context.detach(token)
    request_id_ctx.reset(request_token)
    clear_contextvars()
