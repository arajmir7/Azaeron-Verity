"""Correlation and privacy regressions against real in-process spans and metrics."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import generate_latest
from sqlalchemy import text

from app.core.observability import (
    configure_tracing,
    configure_database_metrics,
    safe_span,
    trace_headers,
)


@pytest.fixture
def spans(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.OTEL_EXPORTER_OTLP_ENDPOINT", None)
    exporter = InMemorySpanExporter()
    configure_tracing().add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


async def test_api_db_denials_and_unknown_paths_exclude_customer_content(
    client, db_session, spans
):
    canary = "private-document-do-not-export"
    configure_database_metrics(db_session.bind)
    with safe_span("test.request"):
        await db_session.execute(text("SELECT '" + canary + "'"))
        with pytest.raises(Exception):
            await db_session.execute(
                text("SELECT missing_column_" + canary.replace("-", "_"))
            )
    await client.get(
        "/unknown/" + canary,
        headers={"x-request-id": canary, "baggage": "document=" + canary},
    )
    denied = await client.post(
        "/api/v1/documents", headers={"origin": "https://untrusted.example"}
    )
    assert denied.status_code == 403
    assert denied.headers["X-Trace-ID"]
    captured = spans.get_finished_spans()
    assert any(s.name == "db.SELECT" for s in captured)
    assert any(s.name == "GET /unmatched" for s in captured)
    assert any(s.status.status_code.name == "ERROR" for s in captured)
    serialized = "".join(s.to_json() for s in captured)
    assert canary not in serialized
    assert "db.statement" not in serialized
    assert all(not s.events for s in captured)
    assert canary not in generate_latest().decode()
    assert "azaeron_authorization_denials_total" in generate_latest().decode()


async def test_browser_report_is_closed_authenticated_metadata(client, spans):
    payload = {"kind": "render", "route": "editor", "event_id": str(uuid4())}
    assert (
        await client.post("/api/v1/telemetry/browser", json=payload)
    ).status_code == 401
    from app.main import app
    from app.core.dependencies import get_current_user

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=str(uuid4())
    )
    try:
        assert (
            await client.post("/api/v1/telemetry/browser", json=payload)
        ).status_code == 202
        assert (
            await client.post(
                "/api/v1/telemetry/browser",
                json={**payload, "message": "private-document"},
            )
        ).status_code == 422
        assert (
            await client.post(
                "/api/v1/telemetry/browser",
                json={**payload, "route": "/documents/private-document"},
            )
        ).status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user)
    assert "private-document" not in "".join(
        s.to_json() for s in spans.get_finished_spans()
    )


def test_queue_consumer_preserves_parent_and_resets_context(spans):
    from app.core.request_context import request_id_ctx
    from app.workers.telemetry import task_started, task_finished

    request_id = str(uuid4())
    token = request_id_ctx.set(request_id)
    with safe_span("api.publish") as parent:
        headers = trace_headers()
        trace_id = parent.get_span_context().trace_id
    task = SimpleNamespace(
        name="app.workers.tasks.process_document",
        request=SimpleNamespace(headers=headers),
    )
    task_started(task=task)
    with safe_span("db.SELECT"):
        assert trace.get_current_span().get_span_context().trace_id == trace_id
    task_finished(task=task, state="SUCCESS")
    request_id_ctx.reset(token)
    finished = spans.get_finished_spans()
    consumer = next(s for s in finished if s.name == "celery.process_document")
    assert consumer.parent.span_id == parent.get_span_context().span_id
    assert consumer.attributes["request.id"] == request_id
    assert set(headers) <= {"traceparent", "tracestate", "verity_request_id"}
    assert request_id_ctx.get() is None


def test_storage_failure_span_contains_no_object_path_or_error(spans, monkeypatch):
    from app.core.object_storage import Minio, SDKMinio

    def fail(*args, **kwargs):
        raise RuntimeError("private-document-content")

    monkeypatch.setattr(SDKMinio, "_execute", fail)
    storage = Minio("localhost:9000", secure=False)
    with pytest.raises(RuntimeError):
        storage._execute("GET", "bucket", "secret-object")
    serialized = "".join(s.to_json() for s in spans.get_finished_spans())
    assert "storage.GET" in serialized
    assert "private-document-content" not in serialized
    assert "secret-object" not in serialized
