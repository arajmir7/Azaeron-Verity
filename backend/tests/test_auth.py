"""AZAERON authentication tests."""

import pytest
from httpx import AsyncClient
from app.core.security import create_refresh_token


class TestAuth:
    async def test_register_user(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "TestPassword123!",
                "first_name": "Test",
                "last_name": "User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["is_active"] is True

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "TestPassword123!"},
        )
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "dup@example.com", "password": "TestPassword123!"},
        )
        assert response.status_code == 409

    async def test_login_success(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "TestPassword123!"},
        )
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "TestPassword123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] is None
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    async def test_login_invalid_credentials(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "WrongPassword123!"},
        )
        assert response.status_code == 401

    async def test_get_me_unauthorized(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_tenant_isolation(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "usera@example.com", "password": "TestPassword123!"},
        )
        login_a = await client.post(
            "/api/v1/auth/login",
            json={"email": "usera@example.com", "password": "TestPassword123!"},
        )
        token_a = login_a.cookies.get("access_token")
        org_a = await client.post(
            "/api/v1/organizations",
            json={"name": "Org A"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        org_a_id = org_a.json()["id"]

        await client.post(
            "/api/v1/auth/register",
            json={"email": "userb@example.com", "password": "TestPassword123!"},
        )
        login_b = await client.post(
            "/api/v1/auth/login",
            json={"email": "userb@example.com", "password": "TestPassword123!"},
        )
        token_b = login_b.cookies.get("access_token")

        response = await client.get(
            f"/api/v1/organizations/{org_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert response.status_code == 404

    async def test_refresh_token_rotation_rejects_reuse(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "rotate@example.com", "password": "TestPassword123!"},
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "rotate@example.com", "password": "TestPassword123!"},
        )
        original_refresh = login.cookies.get("refresh_token")
        same_origin = {"Origin": "http://localhost:3000"}
        first = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
            headers=same_origin,
        )
        assert first.status_code == 200
        rotated_refresh = first.cookies.get("refresh_token")
        reused = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
            headers=same_origin,
        )
        assert reused.status_code == 401
        assert (
            await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": rotated_refresh},
                headers=same_origin,
            )
        ).status_code == 401

    async def test_cookie_refresh_rejects_cross_origin_post(self, client: AsyncClient):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "csrf-refresh@example.com", "password": "TestPassword123!"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": "csrf-refresh@example.com", "password": "TestPassword123!"},
        )
        response = await client.post("/api/v1/auth/refresh", json={})
        assert response.status_code == 403

    async def test_signed_but_unregistered_refresh_token_is_rejected(
        self, client: AsyncClient
    ):
        token, _, _ = create_refresh_token("missing-user")
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": token},
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 401
