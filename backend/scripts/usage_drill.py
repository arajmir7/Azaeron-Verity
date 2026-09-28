"""Actual isolated HTTP, PostgreSQL, Celery and MinIO usage/retry drill."""

import asyncio
import hashlib
import io
import json
import secrets
from uuid import uuid4

import httpx

from app.api.v1.documents import get_storage_client
from app.core.config import settings


async def main():
    if settings.ENVIRONMENT != "development":
        raise RuntimeError("Use an isolated development stack")
    password = secrets.token_urlsafe(24) + "Aa1!"
    credentials = {
        "email": f"usage-drill-{uuid4().hex}@example.com",
        "password": password,
    }
    report = {"scope": "synthetic isolated HTTP and actual worker usage", "checks": {}}
    async with httpx.AsyncClient(
        base_url="http://backend:8000",
        headers={"Origin": "http://localhost:4700"},
        timeout=45,
    ) as client:
        assert (
            await client.post("/api/v1/auth/register", json=credentials)
        ).status_code == 201
        assert (
            await client.post("/api/v1/auth/login", json=credentials)
        ).status_code == 200
        assert (
            await client.post(
                "/api/v1/auth/onboarding", json={"product_role": "student"}
            )
        ).status_code == 200
        user = (await client.get("/api/v1/auth/me")).json()
        issued = await client.post(
            "/api/v1/api-keys",
            json={
                "name": "Usage drill",
                "scopes": [
                    "text:analyze",
                    "text:verify",
                    "text:refine",
                    "usage:read",
                    "documents:read",
                    "documents:write",
                ],
            },
        )
        assert issued.status_code == 201
        headers = {"X-API-Key": issued.json()["secret"]}
        payload = {
            "operation_id": str(uuid4()),
            "text": "A fixture may preserve approximately 10% of citations.",
        }
        for replay in (False, True):
            response = await client.post(
                "/api/v1/text/analyze", json=payload, headers=headers
            )
            assert response.status_code == 200
            if replay:
                assert response.headers["Idempotent-Replay"] == "true"
        report["checks"]["discarded_response_replay"] = "PASS"
        assert (
            await client.post(
                "/api/v1/text/analyze",
                json={**payload, "text": "different"},
                headers=headers,
            )
        ).status_code == 409
        report["checks"]["changed_payload_rejected"] = "PASS"
        unavailable = await client.post(
            "/api/v1/text/refine",
            json={**payload, "operation_id": str(uuid4())},
            headers=headers,
        )
        assert unavailable.status_code == 503
        content = (
            b"In order to explain the finding, the the report uses clear language."
        )
        requested = await client.post(
            "/api/v1/documents/upload-request",
            json={
                "filename": "usage-fixture.txt",
                "content_type": "text/plain",
                "file_size": len(content),
            },
            headers=headers,
        )
        assert requested.status_code == 200
        upload = requested.json()
        await asyncio.to_thread(
            get_storage_client().put_object,
            settings.MINIO_BUCKET,
            upload["storage_key"],
            io.BytesIO(content),
            len(content),
            content_type="text/plain",
        )
        confirmation = {
            "upload_id": upload["upload_id"],
            "storage_key": upload["storage_key"],
            "sha256_fingerprint": hashlib.sha256(content).hexdigest(),
            "original_filename": "usage-fixture.txt",
        }
        document = await client.post(
            "/api/v1/documents/upload-confirm", json=confirmation, headers=headers
        )
        assert document.status_code == 200
        replay = await client.post(
            "/api/v1/documents/upload-confirm", json=confirmation, headers=headers
        )
        assert (
            replay.status_code == 200 and replay.json()["id"] == document.json()["id"]
        )
        for _ in range(60):
            usage = (await client.get("/api/v1/usage", headers=headers)).json()
            counters = {row["task"]: row for row in usage["limits"]}
            if counters["document_processing"]["committed"] == 1:
                break
            await asyncio.sleep(1)
        for task in ["document_upload", "document_processing", "text_analyze"]:
            assert (
                counters[task]["committed"] == 1 and counters[task]["reserved"] == 0
            ), counters
        assert (
            counters["text_refine"]["committed"]
            == counters["text_refine"]["reserved"]
            == 0
        )
        assert all(
            row["input_tokens"] is None
            and row["output_tokens"] is None
            and not row["billable"]
            for row in usage["recent_operations"]
        )
        report["checks"]["actual_worker_commit_and_upload_retry"] = "PASS"
        report["checks"]["unavailable_inference_released"] = "PASS"
        report["checks"]["no_fabricated_tokens_or_billing"] = "PASS"
        parsed = (
            await client.get(
                f"/api/v1/documents/{document.json()['id']}/content", headers=headers
            )
        ).json()
        editorial = {
            "document_id": document.json()["id"],
            "document_version_id": parsed["document_version_id"],
            "operation_id": str(uuid4()),
            "text": content.decode(),
            "preserve_voice": True,
        }
        first = await client.post("/api/v1/aegiswrite/refine", json=editorial)
        assert first.status_code == 200
        second = await client.post("/api/v1/aegiswrite/refine", json=editorial)
        assert second.status_code == 200 and first.json() == second.json()
        assert second.headers["Idempotent-Replay"] == "true"
        report["checks"]["editorial_artifacts_replay_once"] = "PASS"
        report["counters"] = counters
        erasure = await client.post(
            "/api/v1/privacy/erasures",
            json={
                "scope": "account",
                "target_id": user["id"],
                "current_password": password,
                "confirmation": "ERASE",
            },
        )
        assert erasure.status_code == 202
        report["fixture_cleanup"] = (
            "Account erasure queued; the normal eight-minute object grace applies."
        )
        report["status"] = "PASS"
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
