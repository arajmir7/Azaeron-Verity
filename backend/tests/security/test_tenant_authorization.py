"""Regression tests for cross-tenant resource access."""

from httpx import AsyncClient
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs.models import Job, JobStatus, JobType


async def _register_and_login(client: AsyncClient, email: str) -> str:
    password = "TestPassword123!"
    assert (
        await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
    ).status_code == 201
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200
    # Bearer is used here to prove authorization does not depend on a shared cookie jar.
    return response.cookies.get("access_token")


async def test_tenant_escape_is_not_possible_for_organization_or_document_endpoints(
    client: AsyncClient,
):
    token_a = await _register_and_login(client, "owner-a@example.com")
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Tenant A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 201
    org_id = created.json()["id"]
    assert (
        await client.post(
            f"/api/v1/organizations/{org_id}/select",
            headers={"Authorization": f"Bearer {token_a}"},
        )
    ).status_code == 200

    token_b = await _register_and_login(client, "owner-b@example.com")
    assert (
        await client.get(
            f"/api/v1/organizations/{org_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/organizations/{org_id}/select",
            headers={"Authorization": f"Bearer {token_b}"},
        )
    ).status_code == 404
    assert (
        await client.get(
            "/api/v1/documents/not-a-document",
            headers={"Authorization": f"Bearer {token_b}"},
        )
    ).status_code == 400


async def test_tenant_escape_is_not_possible_for_document_derived_resources(
    client: AsyncClient, db_session
):
    token_a = await _register_and_login(client, "doc-owner-a@example.com")
    org_a = await client.post(
        "/api/v1/organizations",
        json={"name": "Document Tenant A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    org_a_id = org_a.json()["id"]
    document = Document(
        organization_id=org_a_id,
        owner_id=(
            await client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"}
            )
        ).json()["id"],
        filename="safe.txt",
        original_filename="safe.txt",
        file_size=4,
        mime_type="text/plain",
        extension="txt",
        sha256_fingerprint="0" * 64,
        storage_path="uploads/test/safe.txt",
    )
    db_session.add(document)
    await db_session.flush()
    version = DocumentVersion(
        document_id=str(document.id),
        version_number=1,
        storage_path=document.storage_path,
        content_hash=document.sha256_fingerprint,
        sha256_fingerprint=document.sha256_fingerprint,
        created_by_id=document.owner_id,
    )
    db_session.add(version)
    await db_session.flush()
    job = Job(
        organization_id=org_a_id,
        document_id=str(document.id),
        document_version_id=str(version.id),
        job_type=JobType.DOCUMENT_PROCESSING,
        status=JobStatus.PENDING,
    )
    db_session.add(job)
    await db_session.flush()
    doc_id, job_id = str(document.id), str(job.id)
    # Release SQLite's write lock before exercising the API through a separate
    # session. Production tests use PostgreSQL transactions instead.
    await db_session.commit()

    token_b = await _register_and_login(client, "doc-owner-b@example.com")
    org_b = await client.post(
        "/api/v1/organizations",
        json={"name": "Document Tenant B"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    selected = await client.post(
        f"/api/v1/organizations/{org_b.json()['id']}/select",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert selected.status_code == 200
    headers = {"Authorization": f"Bearer {selected.cookies.get('access_token')}"}
    assert (
        await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{doc_id}/content", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/detection/documents/{doc_id}", headers=headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/evidence/documents/{doc_id}/graph", headers=headers)
    ).status_code == 404
