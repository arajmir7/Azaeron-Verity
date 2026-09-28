"""High-risk security gate regressions."""

from httpx import AsyncClient

from app.core.config import settings
from app.modules.organizations.models import Organization


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
    return response.cookies.get("access_token")


async def test_inactive_organization_cannot_be_selected(
    client: AsyncClient, db_session
):
    token = await _register_and_login(client, "inactive-org@example.com")
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Inactive Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201
    organization = await db_session.get(Organization, created.json()["id"])
    organization.is_active = False
    await db_session.commit()

    response = await client.post(
        f"/api/v1/organizations/{organization.id}/select",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_pagination_limits_block_resource_exhaustion_inputs(client: AsyncClient):
    token = await _register_and_login(client, "pagination@example.com")
    created = await client.post(
        "/api/v1/organizations",
        json={"name": "Pagination Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201
    selected = await client.post(
        f"/api/v1/organizations/{created.json()['id']}/select",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert selected.status_code == 200
    assert (await client.get("/api/v1/documents?page_size=101")).status_code == 422
    assert (await client.get("/api/v1/jobs?page_size=101")).status_code == 422


async def test_production_metrics_require_a_dedicated_bearer_token(client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "METRICS_TOKEN", "m" * 40)
    assert (await client.get("/metrics")).status_code == 401
    assert (
        await client.get("/metrics", headers={"Authorization": "Bearer wrong"})
    ).status_code == 401
    response = await client.get(
        "/metrics", headers={"Authorization": f"Bearer {'m' * 40}"}
    )
    assert response.status_code == 200
    assert "python_info" in response.text
