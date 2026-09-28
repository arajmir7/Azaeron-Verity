"""Live isolated erasure drill with actual PostgreSQL, workers and MinIO.

Only synthetic accounts created by this invocation are erased. The upload-URL
expiration grace period runs in real time; no test clock or policy override.
"""

import asyncio
import hashlib
import io
import json
import secrets
import time
from uuid import uuid4

import httpx
from minio.error import S3Error

from app.api.v1.documents import get_storage_client
from app.core.config import settings
from app.modules.privacy.storage import maintenance_client


async def main():
    if settings.ENVIRONMENT != "development":
        raise RuntimeError("This fixture drill requires an isolated development stack")
    password = secrets.token_urlsafe(24) + "Aa1!"
    report = {"scope": "synthetic live account and object erasure", "checks": {}}
    async with httpx.AsyncClient(
        base_url="http://backend:8000",
        headers={"Origin": "http://localhost:4700"},
        timeout=45,
    ) as client:
        credentials = {
            "email": f"privacy-drill-{uuid4().hex}@example.com",
            "password": password,
        }
        response = await client.post("/api/v1/auth/register", json=credentials)
        assert response.status_code == 201, response.status_code
        response = await client.post("/api/v1/auth/login", json=credentials)
        assert response.status_code == 200, response.status_code
        response = await client.post(
            "/api/v1/auth/onboarding", json={"product_role": "student"}
        )
        assert response.status_code == 200, response.status_code
        user = (await client.get("/api/v1/auth/me")).json()
        content = b"A privacy erasure fixture. The author may retain approximately 10% of citations."
        upload = await client.post(
            "/api/v1/documents/upload-request",
            json={
                "filename": "erasure-fixture.txt",
                "content_type": "text/plain",
                "file_size": len(content),
            },
        )
        assert upload.status_code == 200, upload.status_code
        upload_data = upload.json()
        app_storage = get_storage_client()
        storage = maintenance_client()
        await asyncio.to_thread(
            app_storage.put_object,
            settings.MINIO_BUCKET,
            upload_data["storage_key"],
            io.BytesIO(content),
            len(content),
            content_type="text/plain",
        )
        response = await client.post(
            "/api/v1/documents/upload-confirm",
            json={
                "upload_id": upload_data["upload_id"],
                "storage_key": upload_data["storage_key"],
                "sha256_fingerprint": hashlib.sha256(content).hexdigest(),
                "original_filename": "erasure-fixture.txt",
            },
        )
        assert response.status_code == 200, response.status_code
        document_id = response.json()["id"]
        for _ in range(40):
            result = await client.get(f"/api/v1/documents/{document_id}/content")
            if result.status_code == 200:
                break
            await asyncio.sleep(1)
        assert result.status_code == 200, "Actual document processing did not finish"
        report["checks"]["processed_document"] = "PASS"
        # A reusable staging PUT cannot grant the upload principal deletion rights.
        try:
            await asyncio.to_thread(
                app_storage.remove_object,
                settings.MINIO_BUCKET,
                upload_data["storage_key"],
            )
        except S3Error as error:
            assert error.code == "AccessDenied"
        else:
            raise AssertionError("Upload principal could delete objects")
        report["checks"]["upload_principal_cannot_delete"] = "PASS"
        started = time.monotonic()
        response = await client.post(
            "/api/v1/privacy/erasures",
            json={
                "scope": "account",
                "target_id": user["id"],
                "current_password": password,
                "confirmation": "ERASE",
            },
        )
        assert response.status_code == 202, response.status_code
        accepted = response.json()
        assert (await client.get("/api/v1/auth/me")).status_code == 401
        assert (
            await client.get(
                f"/api/v1/privacy/erasures/{accepted['id']}",
                headers={"X-Erasure-Receipt": "x" * 43},
            )
        ).status_code == 404
        report["checks"]["session_revoked_and_bad_receipt_denied"] = "PASS"
        statuses = []
        for _ in range(130):
            status = await client.get(
                f"/api/v1/privacy/erasures/{accepted['id']}",
                headers={"X-Erasure-Receipt": accepted["receipt"]},
            )
            assert status.status_code == 200, status.status_code
            state = status.json()["status"]
            if not statuses or statuses[-1] != state:
                statuses.append(state)
                print(
                    json.dumps(
                        {
                            "state": state,
                            "seconds": round(time.monotonic() - started, 1),
                        }
                    ),
                    flush=True,
                )
            if state == "COMPLETED":
                break
            await asyncio.sleep(5)
        assert state == "COMPLETED", f"Erasure did not finish: {state}"
        elapsed = time.monotonic() - started
        assert elapsed >= 480, "Completion bypassed the upload-URL grace period"
        org_id = upload_data["storage_key"].split("/")[1]
        for prefix in [
            f"uploads/{org_id}/",
            f"versions/uploads/{org_id}/",
            f"versions/{org_id}/",
        ]:
            assert not list(
                storage.list_objects(
                    settings.MINIO_BUCKET,
                    prefix=prefix,
                    recursive=True,
                    include_version=True,
                )
            )
        report["checks"]["actual_object_version_absence"] = "PASS"
        report["checks"]["real_expiry_grace"] = "PASS"
        report["states"] = statuses
        report["elapsed_seconds"] = round(elapsed, 2)
        report["status"] = "PASS"
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
