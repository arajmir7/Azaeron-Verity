"""Real API retries, failure release and receipt privacy, without model claims."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.main import app
from app.modules.billing.models import UsageBucket, UsageOperation
from app.modules.billing.usage import UsageService, now
from tests.test_api_keys import issue, owner


async def test_lost_response_retry_is_counted_once_and_is_credential_bound(client):
    auth, org = await owner(client)
    key = await issue(client, auth, scopes=["text:analyze", "usage:read"])
    headers = {"X-API-Key": key["secret"]}
    operation = str(uuid4())
    payload = {
        "operation_id": operation,
        "text": "Private fixture text that must never enter usage metadata.",
    }
    first = await client.post("/api/v1/text/analyze", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    replay = await client.post("/api/v1/text/analyze", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert replay.headers["idempotent-replay"] == "true"
    assert (
        await client.post(
            "/api/v1/text/analyze", headers=headers, json={**payload, "text": "Changed"}
        )
    ).status_code == 409
    assert (
        await client.post("/api/v1/text/analyze", headers=auth, json=payload)
    ).status_code == 409
    response = await client.get("/api/v1/usage", headers=headers)
    assert response.status_code == 200
    assert (
        payload["text"] not in response.text
        and "response_ciphertext" not in response.text
    )
    counter = next(
        item for item in response.json()["limits"] if item["task"] == "text_analyze"
    )
    assert counter["committed"] == 1 and counter["reserved"] == 0
    async with app.state.test_session_factory() as db:
        record = await db.scalar(
            select(UsageOperation).where(UsageOperation.operation_id == operation)
        )
        assert record.api_key_id == key["key"]["id"] and record.organization_id == org
        assert record.input_tokens is None and record.output_tokens is None
        assert record.billable is False and record.chargeable is True
        assert payload["text"] not in record.response_ciphertext
        record.response_expires_at = now() - timedelta(seconds=1)
        await db.commit()
    assert (
        await client.post("/api/v1/text/analyze", headers=headers, json=payload)
    ).status_code == 409


async def test_unavailable_inference_releases_reservation_and_replays_failure(client):
    auth, org = await owner(client)
    payload = {"operation_id": str(uuid4()), "text": "The text remains unchanged."}
    first = await client.post("/api/v1/text/refine", headers=auth, json=payload)
    assert first.status_code == 503
    second = await client.post("/api/v1/text/refine", headers=auth, json=payload)
    assert second.status_code == 503 and second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    async with app.state.test_session_factory() as db:
        record = await db.scalar(
            select(UsageOperation).where(
                UsageOperation.operation_id == payload["operation_id"]
            )
        )
        bucket = await db.scalar(
            select(UsageBucket).where(
                UsageBucket.organization_id == org, UsageBucket.task == "text_refine"
            )
        )
        assert record.status == "RELEASED" and not record.chargeable
        assert (bucket.reserved, bucket.committed) == (0, 0)


async def test_worker_settlement_is_idempotent(client):
    auth, org = await owner(client)
    user = (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]
    async with app.state.test_session_factory() as db:
        service = UsageService(db)
        job = str(uuid4())
        record, replay = await service.reserve(
            org, user, "document_processing", job, {"job": job}, job_id=job
        )
        assert not replay
        await service.settle_job(
            job, org, success=True, outcome="completed", duration_ms=123
        )
        await service.settle_job(
            job, org, success=True, outcome="completed", duration_ms=456
        )
        await service.settle_job(job, org, success=False, outcome="failed")
        bucket = await service.bucket(
            org, now().strftime("%Y-%m"), "document_processing"
        )
        assert (bucket.reserved, bucket.committed) == (0, 1)
        assert record.status == "COMMITTED" and record.duration_ms == 123


async def test_expired_reservation_never_reexecutes(client):
    from fastapi import HTTPException

    auth, org = await owner(client)
    user = (await client.get("/api/v1/auth/me", headers=auth)).json()["id"]
    operation = str(uuid4())
    async with app.state.test_session_factory() as db:
        service = UsageService(db)
        record, _ = await service.reserve(
            org, user, "text_analyze", operation, {"text": "fixture"}
        )
        record.expires_at = now() - timedelta(seconds=1)
        await db.commit()
        record, replay = await service.reserve(
            org, user, "text_analyze", operation, {"text": "fixture"}
        )
        assert replay and record.status == "RELEASED"
        with pytest.raises(HTTPException) as error:
            service.replay(record)
        assert error.value.status_code == 409
        bucket = await service.bucket(org, now().strftime("%Y-%m"), "text_analyze")
        assert (bucket.reserved, bucket.committed) == (0, 0)
