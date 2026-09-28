"""First-run, workspace preference, invitation and server plan contracts."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.organizations.models import Membership, Organization, SubscriptionTier
from app.modules.organizations.invitations import InvitationService

PASSWORD = "WorkspaceTest123!"


async def register_login(client, email="onboarding@example.com"):
    client.headers["Origin"] = "http://localhost:3000"
    response = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    user = response.json()
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return user


@pytest.mark.parametrize(
    "role,home",
    [
        ("student", "/check"),
        ("teacher", "/documents"),
        ("professor", "/documents"),
        ("researcher", "/citations"),
        ("reviewer", "/documents"),
        ("institution", "/documents"),
    ],
)
async def test_onboarding_creates_and_selects_one_personal_workspace(
    client, role, home
):
    await register_login(client)
    for _ in range(2):
        response = await client.post(
            "/api/v1/auth/onboarding", json={"product_role": role}
        )
        assert response.status_code == 200, response.text
        profile = response.json()
        assert profile["onboarding_completed"]
        assert profile["product_role"] == role
        assert profile["home_path"] == home
        assert len(profile["organizations"]) == 1
        membership = profile["organizations"][0]
        assert membership["role"] == "owner"
        assert membership["subscription_tier"] == "free"
        assert profile["active_organization_id"] == membership["organization_id"]
        assert (
            decode_access_token(response.cookies["access_token"]).org_id
            == membership["organization_id"]
        )
    assert (await client.get("/api/v1/documents")).status_code == 200


async def test_onboarding_and_workspace_creation_cannot_set_plan_or_admin_role(client):
    assert (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "student"})
    ).status_code == 401
    await register_login(client)
    assert (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "owner"})
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/auth/onboarding",
            json={"product_role": "institution", "subscription_tier": "enterprise"},
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/organizations",
            json={"name": "Injected", "subscription_tier": "enterprise"},
        )
    ).status_code == 422


async def test_refresh_and_login_preserve_workspace_but_recheck_revocation(
    client, db_session
):
    user = await register_login(client)
    first = (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "student"})
    ).json()["active_organization_id"]
    second = (
        await client.post("/api/v1/organizations", json={"name": "Other workspace"})
    ).json()["id"]
    assert (
        await client.post(f"/api/v1/organizations/{second}/select")
    ).status_code == 200
    refreshed = await client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200, refreshed.text
    assert decode_access_token(refreshed.cookies["access_token"]).org_id == second
    await client.post("/api/v1/auth/logout")
    login = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": PASSWORD}
    )
    assert decode_access_token(login.cookies["access_token"]).org_id == second
    membership = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == user["id"],
                Membership.organization_id == second,
            )
        )
    ).scalar_one()
    membership.is_active = False
    await db_session.commit()
    # Even the previously signed cookie loses document access immediately.
    assert (await client.get("/api/v1/documents")).status_code == 400
    refreshed = await client.post("/api/v1/auth/refresh", json={})
    assert refreshed.status_code == 200
    assert decode_access_token(refreshed.cookies["access_token"]).org_id == first
    assert (
        await client.post(f"/api/v1/organizations/{second}/select")
    ).status_code == 404


async def test_invitation_is_email_bound_idempotent_and_cannot_restore_revocation(
    client, db_session
):
    await register_login(client, "inviter@example.com")
    org_id = (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "professor"})
    ).json()["active_organization_id"]
    assert (
        await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "invitee@example.com", "role": "owner"},
        )
    ).status_code == 403
    invitation = await client.post(
        f"/api/v1/organizations/{org_id}/invitations",
        json={"email": "invitee@example.com", "role": "researcher"},
    )
    assert invitation.status_code == 201, invitation.text
    token = invitation.json()["token"]
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept", json={"token": token}
        )
    ).status_code == 403
    await client.post("/api/v1/auth/logout")
    user = await register_login(client, "invitee@example.com")
    for _ in range(2):
        joined = await client.post(
            "/api/v1/organizations/invitations/accept", json={"token": token}
        )
        assert joined.status_code == 200, joined.text
        assert joined.json()["id"] == org_id
    assert (
        await client.post(
            f"/api/v1/organizations/{org_id}/invitations",
            json={"email": "third@example.com"},
        )
    ).status_code == 403
    membership = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == user["id"], Membership.organization_id == org_id
            )
        )
    ).scalar_one()
    assert membership.role.value == "researcher"
    membership.is_active = False
    await db_session.commit()
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept", json={"token": token}
        )
    ).status_code == 403


async def test_invalid_and_expired_invitation_fail(client, db_session, monkeypatch):
    await register_login(client)
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept", json={"token": "forged"}
        )
    ).status_code == 400
    signer = InvitationService(db_session).signer
    import itsdangerous.timed

    with monkeypatch.context() as context:
        context.setattr(
            itsdangerous.timed.TimestampSigner, "get_timestamp", lambda self: 1
        )
        expired = signer.dumps(
            {
                "email": "onboarding@example.com",
                "organization_id": "expired",
                "inviter_id": "old",
                "role": "student",
            }
        )
    assert (
        await client.post(
            "/api/v1/organizations/invitations/accept", json={"token": expired}
        )
    ).status_code == 400


async def test_entitlements_are_server_owned_and_expired_plans_fall_back_to_free(
    client, db_session
):
    await register_login(client)
    org_id = (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "student"})
    ).json()["active_organization_id"]
    response = await client.get(f"/api/v1/organizations/{org_id}/entitlements")
    assert response.status_code == 200, response.text
    assert response.json()["plan"] == "free"
    assert response.json()["documents_this_month"] == 0
    large_upload = {
        "filename": "paper.txt",
        "content_type": "text/plain",
        "file_size": 11 * 1024 * 1024,
    }
    assert (
        await client.post("/api/v1/documents/upload-request", json=large_upload)
    ).status_code == 402
    organization = (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()
    organization.subscription_tier = SubscriptionTier.PRO
    organization.subscription_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    await db_session.commit()
    assert (await client.get(f"/api/v1/organizations/{org_id}/entitlements")).json()[
        "plan"
    ] == "free"
    assert (
        await client.post("/api/v1/documents/upload-request", json=large_upload)
    ).status_code == 402
    await client.post("/api/v1/auth/logout")
    await register_login(client, "outsider@example.com")
    assert (
        await client.get(f"/api/v1/organizations/{org_id}/entitlements")
    ).status_code == 404


async def test_document_and_write_quotas_enforced_by_service(client, db_session):
    from fastapi import HTTPException
    from app.modules.billing.entitlements import EntitlementService

    user = await register_login(client)
    org_id = (
        await client.post("/api/v1/auth/onboarding", json={"product_role": "student"})
    ).json()["active_organization_id"]
    for _ in range(20):
        db_session.add(
            Document(
                organization_id=org_id,
                owner_id=user["id"],
                filename="paper.txt",
                original_filename="paper.txt",
                file_size=100,
                mime_type="text/plain",
                extension="txt",
                sha256_fingerprint="a" * 64,
                storage_path=str(uuid4()),
            )
        )
    await db_session.flush()
    with pytest.raises(HTTPException) as error:
        await EntitlementService(db_session).require_upload(org_id, 100)
    assert error.value.status_code == 402
    with pytest.raises(HTTPException) as error:
        await EntitlementService(db_session).require_write(org_id, 60_001)
    assert error.value.status_code == 402
    # Reading existing documents and revising a bounded passage remain usable.
    await EntitlementService(db_session).require_write(org_id, 100)
