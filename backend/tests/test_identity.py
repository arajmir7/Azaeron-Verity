"""Identity tokens, MFA and device controls exercised through actual ASGI routes."""

import base64
from datetime import timedelta
import json
import re
import secrets
import time
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import (
    auth_rate_limiter,
    identity_rate_limiter,
    mfa_rate_limiter,
)
from app.main import app
from app.modules.auth import identity
from app.modules.auth.identity_models import IdentityMail, IdentityToken
from app.modules.auth.models import User
from app.modules.auth.mail import deliver_pending


@pytest.fixture(autouse=True)
def identity_test_settings(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
    monkeypatch.setattr(auth_rate_limiter, "requests", 100)
    identity_rate_limiter._fallback.clear()
    mfa_rate_limiter._fallback.clear()


async def account(client):
    email = f"identity-{uuid4()}@example.com"
    password = secrets.token_urlsafe(20) + "Aa1!"
    assert (
        await client.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
    ).status_code == 201
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return (
        email,
        password,
        {"Authorization": "Bearer " + response.cookies["access_token"]},
    )


async def mail_token():
    async with app.state.test_session_factory() as db:
        mail = await db.scalar(
            select(IdentityMail).order_by(
                IdentityMail.created_at.desc(), IdentityMail.id.desc()
            )
        )
        payload = json.loads(identity.decrypt(mail.encrypted_payload))
        secret = re.search(r"#token=([A-Za-z0-9_-]+)", payload["body"]).group(1)
        return str(mail.id), secret, payload


@pytest.mark.asyncio
async def test_verification_single_use_expiry_and_encrypted_delivery(client):
    email, _, auth = await account(client)
    response = await client.post("/api/v1/auth/verification/request", headers=auth)
    assert response.status_code == 200
    mail_id, secret, payload = await mail_token()
    async with app.state.test_session_factory() as db:
        mail = await db.get(IdentityMail, mail_id)
        token = await db.scalar(select(IdentityToken))
        assert secret not in mail.encrypted_payload and secret != token.digest
        assert email not in mail.encrypted_payload
    assert (
        await client.post("/api/v1/auth/verification/confirm", json={"token": secret})
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth)).json()[
        "is_verified"
    ] is True
    assert (
        await client.post("/api/v1/auth/verification/confirm", json={"token": secret})
    ).status_code == 400
    delivered = []

    class Sink:
        def send(self, message, message_id):
            delivered.append((message, message_id))

    async with app.state.test_session_factory.begin() as db:
        assert await deliver_pending(db, Sink()) == {
            "sent": 1,
            "failed": 0,
            "expired": 0,
        }
    async with app.state.test_session_factory.begin() as db:
        assert await deliver_pending(db, Sink()) == {
            "sent": 0,
            "failed": 0,
            "expired": 0,
        }
        assert (await db.get(IdentityMail, mail_id)).encrypted_payload is None
    assert delivered == [(payload, mail_id)]


@pytest.mark.asyncio
async def test_reset_generic_single_use_revokes_sessions_and_expires(client):
    email, password, auth = await account(client)
    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    unknown = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "unknown@example.com"}
    )
    assert (
        response.status_code == unknown.status_code == 200
        and response.json() == unknown.json()
    )
    _, secret, _ = await mail_token()
    replacement = secrets.token_urlsafe(20) + "Aa1!"
    assert (
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": secret, "new_password": replacement},
        )
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=auth)).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": secret, "new_password": password},
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": replacement}
        )
    ).status_code == 200
    await client.post("/api/v1/auth/forgot-password", json={"email": email})
    async with app.state.test_session_factory.begin() as db:
        token = await db.scalar(
            select(IdentityToken).where(IdentityToken.used_at.is_(None))
        )
        token.expires_at = identity.now() - timedelta(seconds=1)
        # Find the new token-bearing message by decrypting fixture records only.
        messages = (await db.scalars(select(IdentityMail))).all()
        secrets_in_mail = [
            re.search(
                r"#token=([A-Za-z0-9_-]+)",
                json.loads(identity.decrypt(row.encrypted_payload))["body"],
            ).group(1)
            for row in messages
        ]
        expired = next(value for value in secrets_in_mail if value != secret)
    assert (
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": expired, "new_password": password},
        )
    ).status_code == 400


@pytest.mark.asyncio
async def test_mail_failure_is_durable_and_rate_limit_identity_is_private(client):
    email, _, auth = await account(client)
    for status in [200, 200, 200, 429]:
        response = await client.post("/api/v1/auth/verification/request", headers=auth)
        assert response.status_code == status
    assert all(email not in key for key in identity_rate_limiter._fallback)

    class Unavailable:
        def send(self, payload, message_id):
            raise RuntimeError("sensitive SMTP response must not be persisted")

    async with app.state.test_session_factory.begin() as db:
        counts = await deliver_pending(db, Unavailable())
        assert counts["failed"] == 3
    async with app.state.test_session_factory.begin() as db:
        records = (await db.scalars(select(IdentityMail))).all()
        assert all(
            row.attempts == 1 and row.last_error == "delivery_unavailable"
            for row in records
        )
        for row in records:
            row.expires_at = identity.now() - timedelta(seconds=1)
            row.next_attempt_at = identity.now() - timedelta(seconds=1)
    async with app.state.test_session_factory.begin() as db:
        assert (await deliver_pending(db, Unavailable()))["expired"] == 3
        assert all(
            row.encrypted_payload is None
            for row in (await db.scalars(select(IdentityMail))).all()
        )


@pytest.mark.asyncio
async def test_mfa_enrollment_login_replay_recovery_and_disable(client, monkeypatch):
    email, password, auth = await account(client)
    other = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    other_auth = {"Authorization": "Bearer " + other.cookies["access_token"]}
    response = await client.post(
        "/api/v1/auth/mfa/enroll", headers=auth, json={"current_password": password}
    )
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    secret = response.json()["secret"]
    current_time = time.time()
    code = identity.totp(base64.b32decode(secret)).generate(current_time).decode()
    response = await client.post(
        "/api/v1/auth/mfa/confirm", headers=auth, json={"code": code}
    )
    assert response.status_code == 200
    recovery = response.json()["recovery_codes"]
    assert len(recovery) == len(set(recovery)) == 10
    assert (await client.get("/api/v1/auth/me", headers=other_auth)).status_code == 401
    async with app.state.test_session_factory() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert (
            secret not in user.mfa_secret
            and recovery[0] not in user.mfa_recovery_hashes
        )
        assert user.mfa_enabled and user.mfa_pending_secret is None
    for credential in [None, code, "000000"]:
        result = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "mfa_code": credential},
        )
        assert result.status_code == 401
    monkeypatch.setattr(identity.time, "time", lambda: current_time + 60)
    new_code = (
        identity.totp(base64.b32decode(secret)).generate(current_time + 60).decode()
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "mfa_code": new_code},
    )
    assert login.status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "mfa_code": new_code},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "mfa_code": recovery[0]},
        )
    ).status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password, "mfa_code": recovery[0]},
        )
    ).status_code == 401
    response = await client.post(
        "/api/v1/auth/mfa/disable",
        headers=auth,
        json={"current_password": password, "mfa_code": recovery[1]},
    )
    assert response.status_code == 200
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_sessions_revoke_individual_and_all_others_without_raw_tokens(client):
    email, password, auth = await account(client)
    second = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    second_auth = {"Authorization": "Bearer " + second.cookies["access_token"]}
    listed = await client.get("/api/v1/auth/sessions", headers=auth)
    assert listed.status_code == 200 and len(listed.json()) == 2
    assert (
        second.cookies["access_token"] not in listed.text
        and second.cookies["refresh_token"] not in listed.text
    )
    other = next(item for item in listed.json() if not item["current"])
    assert (
        await client.delete("/api/v1/auth/sessions/" + other["id"], headers=auth)
    ).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=second_auth)).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=auth)).status_code == 200
    third = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert (
        await client.delete("/api/v1/auth/sessions/others", headers=auth)
    ).status_code == 204
    assert (
        await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + third.cookies["access_token"]},
        )
    ).status_code == 401
    assert (await client.get("/api/v1/auth/me", headers=auth)).status_code == 200
    assert (
        await client.delete("/api/v1/auth/sessions/unknown", headers=auth)
    ).status_code == 404


@pytest.mark.asyncio
async def test_token_purpose_mfa_preservation_and_foreign_session_access(client):
    email, password, auth = await account(client)
    assert (
        await client.post("/api/v1/auth/verification/request", headers=auth)
    ).status_code == 200
    _, verification_token, _ = await mail_token()
    assert (
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": verification_token, "new_password": password},
        )
    ).status_code == 400
    # A password-reset link must not disable an already enabled factor.
    async with app.state.test_session_factory.begin() as db:
        user = await db.scalar(select(User).where(User.email == email))
        user.mfa_enabled = True
        user.mfa_secret = (
            identity.cipher()
            .encrypt(base64.b32encode(secrets.token_bytes(20)))
            .decode()
        )
    assert (
        await client.post("/api/v1/auth/forgot-password", json={"email": email})
    ).status_code == 200
    async with app.state.test_session_factory() as db:
        rows = (await db.scalars(select(IdentityMail))).all()
        reset_payload = next(
            json.loads(identity.decrypt(row.encrypted_payload))
            for row in rows
            if "password reset"
            in json.loads(identity.decrypt(row.encrypted_payload))["subject"]
        )
        token = re.search(r"#token=([A-Za-z0-9_-]+)", reset_payload["body"]).group(1)
    new_password = secrets.token_urlsafe(24) + "Aa1!"
    assert (
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": new_password},
        )
    ).status_code == 200
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": new_password}
    )
    assert (
        response.status_code == 401
        and response.json()["detail"]["code"] == "mfa_required"
    )
    _, _, first = await account(client)
    sessions = (await client.get("/api/v1/auth/sessions", headers=first)).json()
    _, _, foreign = await account(client)
    assert (
        await client.delete(
            "/api/v1/auth/sessions/" + sessions[0]["id"], headers=foreign
        )
    ).status_code == 404


@pytest.mark.asyncio
async def test_expired_enrollment_and_utf8_password_bound(client):
    email, password, auth = await account(client)
    response = await client.post(
        "/api/v1/auth/mfa/enroll", headers=auth, json={"current_password": password}
    )
    code = (
        identity.totp(base64.b32decode(response.json()["secret"]))
        .generate(time.time())
        .decode()
    )
    async with app.state.test_session_factory.begin() as db:
        user = await db.scalar(select(User).where(User.email == email))
        user.mfa_pending_expires_at = identity.now() - timedelta(seconds=1)
    assert (
        await client.post("/api/v1/auth/mfa/confirm", headers=auth, json={"code": code})
    ).status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/change-password",
            headers=auth,
            json={"current_password": password, "new_password": "Aa1!" + "é" * 40},
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    ).status_code == 200
