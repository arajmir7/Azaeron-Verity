from datetime import datetime, timezone

import pytest

from app.modules.organizations.models import Membership, OrganizationRole


@pytest.mark.parametrize("role", [OrganizationRole.AUDITOR, OrganizationRole.REVIEWER])
async def test_readonly_members_cannot_mutate_documents_jobs_or_refinement(
    client, db_session, role
):
    headers = {"Origin": "http://localhost:3000"}
    password = "TestPassword123!"
    owner = await client.post(
        "/api/v1/auth/register",
        json={"email": "writer@example.com", "password": password},
    )
    assert owner.status_code == 201
    await client.post(
        "/api/v1/auth/login", json={"email": "writer@example.com", "password": password}
    )
    org = await client.post(
        "/api/v1/organizations", json={"name": "Read only boundary"}, headers=headers
    )
    org_id = org.json()["id"]
    reader = await client.post(
        "/api/v1/auth/register",
        json={"email": "reader@example.com", "password": password},
    )
    db_session.add(
        Membership(
            user_id=reader.json()["id"],
            organization_id=org_id,
            role=role,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    await client.post(
        "/api/v1/auth/login", json={"email": "reader@example.com", "password": password}
    )
    assert (
        await client.post(f"/api/v1/organizations/{org_id}/select", headers=headers)
    ).status_code == 200
    assert (await client.get("/api/v1/documents")).status_code == 200
    for method, path, body in [
        (
            "POST",
            "/api/v1/documents/upload-request",
            {"filename": "test.txt", "content_type": "text/plain", "file_size": 4},
        ),
        ("DELETE", "/api/v1/documents/unknown", None),
        ("POST", "/api/v1/jobs/unknown/cancel", None),
        (
            "POST",
            "/api/v1/aegiswrite/refine",
            {"document_id": "unknown", "text": "A draft."},
        ),
    ]:
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code == 403, (path, response.text)
