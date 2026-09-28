"""API-key lifecycle through real ASGI routes, persisted digests and audit rows."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.dependencies import api_key_rate_limiter, api_tenant_rate_limiter
from app.main import app
from app.modules.audit.models import AuditAction, AuditLog
from app.modules.auth.models import ApiKey


async def owner(client, email="keys@example.com"):
    password = secrets.token_urlsafe(24) + "Aa1!"
    assert (
        await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
    ).status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    headers = {"Authorization": "Bearer " + login.cookies["access_token"]}
    organization = await client.post(
        "/api/v1/organizations", json={"name": "Key fixture"}, headers=headers
    )
    org = organization.json()["id"]
    selected = await client.post(f"/api/v1/organizations/{org}/select", headers=headers)
    return {"Authorization": "Bearer " + selected.cookies["access_token"]}, org


async def issue(client, auth, scopes=None, **extra):
    response = await client.post(
        "/api/v1/api-keys",
        headers=auth,
        json={"name": "Regression key", "scopes": scopes or ["text:verify"], **extra},
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def payload():
    return {
        "operation_id": str(uuid4()),
        "original": "It may work.",
        "candidate": "It will work.",
    }


@pytest.mark.asyncio
async def test_lifecycle_digest_display_once_rotation_revocation_audit(client):
    auth, org = await owner(client)
    issued = await issue(client, auth)
    key_id, secret = issued["key"]["id"], issued["secret"]
    listed = await client.get("/api/v1/api-keys", headers=auth)
    assert (
        listed.status_code == 200
        and secret not in listed.text
        and "hashed_key" not in listed.text
    )
    assert listed.json()[0]["organization_id"] == org
    response = await client.post(
        "/api/v1/text/verify", headers={"X-API-Key": secret}, json=payload()
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "REJECTED"
    async with app.state.test_session_factory() as db:
        record = await db.get(ApiKey, key_id)
        assert record.hashed_key == hashlib.sha256(secret.encode()).hexdigest()
        assert record.last_used_at and secret not in record.hashed_key
    rotated = await client.post(f"/api/v1/api-keys/{key_id}/rotate", headers=auth)
    assert rotated.status_code == 201, rotated.text
    new = rotated.json()
    assert new["key"]["rotated_from_id"] == key_id
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": secret}, json=payload()
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": new["secret"]}, json=payload()
        )
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/api-keys/{key_id}/rotate", headers=auth)
    ).status_code == 409
    for _ in range(2):
        assert (
            await client.delete(f"/api/v1/api-keys/{new['key']['id']}", headers=auth)
        ).status_code == 204
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": new["secret"]}, json=payload()
        )
    ).status_code == 401
    async with app.state.test_session_factory() as db:
        events = (
            await db.scalars(
                select(AuditLog).where(
                    AuditLog.organization_id == org, AuditLog.resource_type == "api_key"
                )
            )
        ).all()
        assert [e.action for e in events].count(AuditAction.API_KEY_CREATED) == 2
        assert [e.action for e in events].count(AuditAction.API_KEY_REVOKED) == 2
        assert secret not in json.dumps([e.details for e in events])


@pytest.mark.asyncio
async def test_invalid_expired_scope_tenant_legacy_and_no_cookie_fallback(client):
    auth, org = await owner(client)
    key = await issue(client, auth)
    secret = key["secret"]
    for credential in [
        "",
        "avk.invalid",
        secret[:-1] + ("A" if secret[-1] != "A" else "B"),
        secret.replace(org, str(uuid4())),
    ]:
        response = await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": credential}, json=payload()
        )
        assert response.status_code == 401
    assert (
        await client.post(
            "/api/v1/text/verify", headers={**auth, "X-API-Key": secret}, json=payload()
        )
    ).status_code == 401
    for path in ["/api/v1/documents", "/api/v1/api-keys", "/api/v1/auth/me"]:
        assert (
            await client.get(path, headers={"X-API-Key": secret})
        ).status_code == 403
    async with app.state.test_session_factory() as db:
        row = await db.get(ApiKey, key["key"]["id"])
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": secret}, json=payload()
        )
    ).status_code == 401
    async with app.state.test_session_factory() as db:
        row = await db.get(ApiKey, key["key"]["id"])
        row.expires_at = None
        row.credential_version = 0
        await db.commit()
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": secret}, json=payload()
        )
    ).status_code == 401
    for bad in [
        {"scopes": ["*"]},
        {"scopes": []},
        {"scopes": ["text:verify", "text:verify"]},
        {"organization_id": str(uuid4())},
        {"expires_at": "2020-01-01T00:00:00Z"},
    ]:
        assert (
            await client.post(
                "/api/v1/api-keys",
                headers=auth,
                json={"name": "bad", "scopes": ["text:verify"], **bad},
            )
        ).status_code == 422


@pytest.mark.asyncio
async def test_other_tenant_cannot_list_rotate_or_revoke_key(client):
    auth, _ = await owner(client)
    key = await issue(client, auth)
    other, _ = await owner(client, "other-key-owner@example.com")
    assert (await client.get("/api/v1/api-keys", headers=other)).json() == []
    assert (
        await client.delete(f"/api/v1/api-keys/{key['key']['id']}", headers=other)
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/api-keys/{key['key']['id']}/rotate", headers=other)
    ).status_code == 404


@pytest.mark.asyncio
async def test_identity_rate_limits_and_openapi_contract(client, monkeypatch):
    auth, org = await owner(client)
    key = await issue(client, auth)
    monkeypatch.setattr(api_key_rate_limiter, "requests", 1)
    for expected in [200, 429]:
        response = await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": key["secret"]}, json=payload()
        )
        assert response.status_code == expected, response.text
    assert response.headers["Retry-After"]
    assert f"api-key-rate:{key['key']['id']}" in api_key_rate_limiter._fallback
    monkeypatch.setattr(api_tenant_rate_limiter, "requests", 1)
    second = await issue(client, auth)
    assert (
        await client.post(
            "/api/v1/text/verify",
            headers={"X-API-Key": second["secret"]},
            json=payload(),
        )
    ).status_code == 429
    assert f"api-tenant-rate:{org}" in api_tenant_rate_limiter._fallback
    schema = (await client.get("/api/openapi.json")).json()
    assert (
        schema["components"]["securitySchemes"]["AzaeronAPIKey"]["name"] == "X-API-Key"
    )
    verify = schema["paths"]["/api/v1/text/verify"]["post"]
    assert verify["x-api-key-scopes"] == ["text:verify"]
    assert {"AzaeronAPIKey": []} in verify["security"]
    assert {"AzaeronAPIKey": []} not in schema["paths"]["/api/v1/api-keys"]["post"][
        "security"
    ]


@pytest.mark.asyncio
async def test_membership_revocation_and_manager_role_are_enforced(client):
    from app.modules.organizations.models import Membership, OrganizationRole

    auth, org = await owner(client)
    key = await issue(client, auth)
    async with app.state.test_session_factory() as db:
        member = await db.scalar(
            select(Membership).where(Membership.organization_id == org)
        )
        member.role = OrganizationRole.REVIEWER
        await db.commit()
    assert (
        await client.post(
            "/api/v1/api-keys",
            headers=auth,
            json={"name": "blocked", "scopes": ["documents:write"]},
        )
    ).status_code == 403
    async with app.state.test_session_factory() as db:
        member = await db.scalar(
            select(Membership).where(Membership.organization_id == org)
        )
        member.is_active = False
        await db.commit()
    assert (
        await client.post(
            "/api/v1/text/verify", headers={"X-API-Key": key["secret"]}, json=payload()
        )
    ).status_code == 401


def test_expiry_is_normalized_before_storage():
    from app.modules.auth.api_keys import KeyCreate

    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    requested = expiry.astimezone(timezone(timedelta(hours=5, minutes=30)))
    created = KeyCreate(
        name="Timezone fixture", scopes=["documents:read"], expires_at=requested
    )
    assert created.expires_at == expiry
    assert created.expires_at.utcoffset() == timedelta(0)
