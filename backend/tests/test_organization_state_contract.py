"""Organization-resolution contract regressions."""

from httpx import AsyncClient


async def _login(client: AsyncClient, email: str) -> str:
    password = "WorkspaceTest123!"
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


async def test_documents_requires_an_explicit_active_organization(client: AsyncClient):
    token = await _login(client, "workspace-none@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    profile = await client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["organizations"] == []
    assert profile.json()["active_organization_id"] is None

    response = await client.get("/api/v1/documents?page=1", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "active_organization_required",
        "message": "Select an organization before accessing tenant-owned resources.",
    }


async def test_selected_organization_is_reflected_in_profile_and_documents_contract(
    client: AsyncClient,
):
    token = await _login(client, "workspace-one@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    organization = await client.post(
        "/api/v1/organizations", json={"name": "Workspace One"}, headers=headers
    )
    assert organization.status_code == 201

    selected = await client.post(
        f"/api/v1/organizations/{organization.json()['id']}/select", headers=headers
    )
    assert selected.status_code == 200
    active_headers = {"Authorization": f"Bearer {selected.cookies.get('access_token')}"}

    profile = await client.get("/api/v1/auth/me", headers=active_headers)
    assert profile.status_code == 200
    assert profile.json()["active_organization_id"] == organization.json()["id"]
    documents = await client.get("/api/v1/documents?page=1", headers=active_headers)
    assert documents.status_code == 200
    assert documents.json()["items"] == []
