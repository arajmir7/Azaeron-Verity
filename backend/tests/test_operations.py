"""Operational contract tests: identifiers, liveness, and production gates."""

import pytest
from fastapi import HTTPException

from app.core.config import Settings


async def test_liveness_and_correlation_headers(client):
    response = await client.get(
        "/health/live",
        headers={
            "X-Request-ID": "a08499f2-f4ce-44d3-b482-f01c611e2269",
            "X-Correlation-ID": "5f52b3c9-c82c-47d2-a663-4dc985462f22",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    assert response.headers["X-Request-ID"] == "a08499f2-f4ce-44d3-b482-f01c611e2269"
    assert (
        response.headers["X-Correlation-ID"] == "5f52b3c9-c82c-47d2-a663-4dc985462f22"
    )


async def test_metrics_include_api_instrumentation(client):
    await client.get("/health/live")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "azaeron_api_requests_total" in response.text
    assert "azaeron_api_request_duration_seconds" in response.text


async def test_rate_limit_rejection_is_a_429_not_a_middleware_500(client, monkeypatch):
    async def reject(_request):
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"}
        )

    monkeypatch.setattr("app.main.rate_limiter", reject)
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert response.headers["Retry-After"] == "60"


def _production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "s" * 40,
        "REFRESH_SECRET_KEY": "r" * 40,
        "DATABASE_URL": "postgresql+asyncpg://azaeron_app:unique-production-password@db:5432/azaeron",
        "MINIO_SECURE": True,
        "MINIO_PUBLIC_ENDPOINT": "objects.example.com",
        "MINIO_ACCESS_KEY": "production-app-user",
        "MINIO_SECRET_KEY": "production-app-password",
        "CORS_ORIGINS": "https://app.example.com",
        "TRUSTED_HOSTS": "app.example.com",
        "METRICS_TOKEN": "m" * 40,
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.com:4317",
        "READINESS_REQUIRE_WORKER": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_settings_require_trace_export_and_worker_readiness():
    with pytest.raises(ValueError, match="OTLP tracing endpoint"):
        _production_settings(OTEL_EXPORTER_OTLP_ENDPOINT=None)
    with pytest.raises(ValueError, match="worker health"):
        _production_settings(READINESS_REQUIRE_WORKER=False)
    assert _production_settings().READINESS_REQUIRE_WORKER is True
