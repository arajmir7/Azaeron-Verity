"""Failure-gate regression tests for fail-closed processing and recovery wiring."""

from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import uuid

import pytest
import jwt

from app.core.config import settings
from app.core.queue import QueueUnavailable, enqueue_with_retry
from app.modules.processing.service import DocumentProcessingService
from app.workers.celery_app import celery_app


def test_task_publish_is_bounded_and_fails_closed(monkeypatch):
    calls = 0

    class FailingTask:
        name = "failure-gate.task"

        def apply_async(self, **kwargs):
            nonlocal calls
            calls += 1
            raise OSError("redis unavailable")

    monkeypatch.setattr("app.core.queue.time.sleep", lambda _: None)
    with pytest.raises(QueueUnavailable):
        enqueue_with_retry(FailingTask(), ("job-1",))
    assert calls == 3


async def test_corrupt_pdf_fails_without_persisting_processed_content():
    service = DocumentProcessingService(None)
    document = SimpleNamespace(extension="pdf")
    with pytest.raises(ValueError, match="Could not extract text"):
        service._extract_text(document, b"not-a-pdf")


async def test_oversized_extracted_text_fails_before_database_write(monkeypatch):
    service = DocumentProcessingService(None)
    document = SimpleNamespace(
        extension="txt", id="document-1", organization_id="org-1"
    )
    monkeypatch.setattr(settings, "MAX_DOCUMENT_TEXT_CHARS", 4)
    with pytest.raises(ValueError, match="processing limit"):
        service._extract_text(document, b"12345")


async def test_expired_access_session_is_rejected(client):
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "jti": "expired-session",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


async def test_logout_revokes_refresh_session(client):
    password = "TestPassword123!"
    await client.post(
        "/api/v1/auth/register",
        json={"email": "failure-session@example.com", "password": password},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "failure-session@example.com", "password": password},
    )
    refresh_token = login.cookies.get("refresh_token")
    logout = await client.post(
        "/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}
    )
    assert logout.status_code == 200
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code == 401


def test_worker_failure_contract_is_enabled():
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_acks_on_failure_or_timeout is False
    assert celery_app.conf.task_time_limit == settings.CELERY_TASK_TIME_LIMIT_SECONDS
    assert (
        celery_app.conf.task_soft_time_limit
        == settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS
    )
