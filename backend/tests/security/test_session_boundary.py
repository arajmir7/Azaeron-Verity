"""Regression attacks on real cookie, token, and persistence boundaries."""

from datetime import datetime, timedelta, timezone

import pytest
import jwt

from app.core.config import settings


async def login(client):
    credentials = {"email": "boundary@example.com", "password": "OriginalPassword123!"}
    assert (
        await client.post("/api/v1/auth/register", json=credentials)
    ).status_code == 201
    response = await client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    return response.cookies.get("access_token"), credentials


@pytest.mark.parametrize("authorization", ["Basic broken", "Bearer", "Bearer invalid"])
async def test_header_cannot_disable_cookie_refresh_csrf(client, authorization):
    await login(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={}, headers={"Authorization": authorization}
    )
    assert response.status_code == 403


async def test_invalid_authorization_never_falls_back_to_cookie(client):
    await login(client)
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Basic broken"}
    )
    assert response.status_code == 401


async def test_logout_revokes_copied_access_token_and_allows_new_login(client):
    token, credentials = await login(client)
    assert (
        await client.post(
            "/api/v1/auth/logout", headers={"Origin": "http://localhost:3000"}
        )
    ).status_code == 200
    assert (
        await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
    ).status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json=credentials)
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    onboard = await client.post(
        "/api/v1/auth/onboarding",
        json={"product_role": "student"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert onboard.status_code == 200
    org_id = onboard.json()["active_organization_id"]
    assert (
        await client.post(
            f"/api/v1/organizations/{org_id}/select",
            headers={"Origin": "http://localhost:3000"},
        )
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_password_change_revokes_copied_access_token(client):
    token, credentials = await login(client)
    response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Origin": "http://localhost:3000"},
        json={
            "current_password": credentials["password"],
            "new_password": "ChangedPassword456!",
        },
    )
    assert response.status_code == 200
    assert (
        await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
    ).status_code == 401


@pytest.mark.parametrize("missing", ["sub", "jti", "exp", "iat"])
async def test_signed_malformed_token_is_unauthorized_not_server_error(client, missing):
    payload = {
        "sub": "unknown",
        "jti": "test",
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    del payload[missing]
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    assert (
        await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
    ).status_code == 401


async def test_login_rejects_foreign_browser_origin(client):
    _, credentials = await login(client)
    response = await client.post(
        "/api/v1/auth/login",
        json=credentials,
        headers={"Origin": "https://foreign.invalid"},
    )
    assert response.status_code == 403
