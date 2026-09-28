"""Single-use identity and standard TOTP/recovery flows over existing sessions."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken as InvalidCiphertext
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.twofactor import InvalidToken
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, validate_password_strength, verify_password
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.auth.identity_models import IdentityMail, IdentityToken
from app.modules.auth.models import RefreshToken, User


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def cipher() -> Fernet:
    key = settings.IDENTITY_ENCRYPTION_KEY
    if not key:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(503, "Identity encryption is not configured")
        key = base64.urlsafe_b64encode(
            hashlib.sha256(
                (settings.SECRET_KEY + ":identity-development-only").encode()
            ).digest()
        ).decode()
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "Identity encryption is not configured") from None


def validate_identity_startup() -> None:
    cipher()
    url = urlsplit(settings.EMAIL_PUBLIC_URL)
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("Identity mail requires a configured public origin")
    if settings.ENVIRONMENT == "production" and (
        url.scheme != "https" or not settings.SMTP_STARTTLS
    ):
        raise ValueError("Production identity requires HTTPS and SMTP TLS")


def decrypt(value: str) -> str:
    try:
        return cipher().decrypt(value.encode()).decode()
    except (InvalidCiphertext, UnicodeError):
        raise HTTPException(
            503, "Identity encryption key cannot decrypt the record"
        ) from None


async def lock_user(db: AsyncSession, user_id: str) -> User:
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not user or not user.is_active:
        raise HTTPException(401, "Account unavailable")
    return user


async def security_event(db: AsyncSession, user: User, event: str) -> None:
    await AuditService(db).log(
        AuditAction.USER_UPDATED,
        "user",
        str(user.id),
        details={"event": event},
        user_id=str(user.id),
    )


async def request_email(db: AsyncSession, email: str, purpose: str) -> None:
    from app.core.dependencies import identity_rate_limiter

    if not settings.EMAIL_ENABLED:
        raise HTTPException(503, "Identity email delivery is not configured")
    if purpose not in {"verify_email", "reset_password"}:
        raise ValueError("Unsupported identity purpose")
    normalized = email.lower().strip()
    await identity_rate_limiter.check_key(
        "identity-mail:"
        + hashlib.sha256(normalized.encode()).hexdigest()
        + ":"
        + purpose
    )
    user = await db.scalar(
        select(User).where(User.email == normalized).with_for_update()
    )
    if not user or not user.is_active or purpose == "verify_email" and user.is_verified:
        return
    await db.execute(
        update(IdentityToken)
        .where(
            IdentityToken.user_id == str(user.id),
            IdentityToken.purpose == purpose,
            IdentityToken.used_at.is_(None),
        )
        .values(used_at=now())
    )
    secret = secrets.token_urlsafe(32)
    deadline = now() + timedelta(minutes=30 if purpose == "reset_password" else 60)
    db.add(
        IdentityToken(
            user_id=str(user.id),
            purpose=purpose,
            digest=hashlib.sha256(secret.encode()).hexdigest(),
            expires_at=deadline,
        )
    )
    route = "reset-password" if purpose == "reset_password" else "verify-email"
    # URL fragments are not sent in HTTP requests, referrers or access logs.
    link = settings.EMAIL_PUBLIC_URL.rstrip("/") + "/" + route + "#token=" + secret
    payload = {
        "to": user.email,
        "subject": (
            "Azaeron password reset"
            if purpose == "reset_password"
            else "Verify your Azaeron email"
        ),
        "body": f"Open this single-use link within {30 if purpose == 'reset_password' else 60} minutes:\n\n{link}\n\nIf you did not request this, ignore this email.",
    }
    db.add(
        IdentityMail(
            user_id=str(user.id),
            encrypted_payload=cipher().encrypt(json.dumps(payload).encode()).decode(),
            expires_at=deadline,
            next_attempt_at=now(),
        )
    )
    await security_event(db, user, purpose + "_requested")
    await db.flush()


async def consume_email(
    db: AsyncSession, secret: str, purpose: str, new_password: str | None = None
) -> None:
    from app.modules.auth.service import AuthService

    invalid = HTTPException(400, "Invalid or expired link")
    if not 30 <= len(secret) <= 100:
        raise invalid
    digest = hashlib.sha256(secret.encode()).hexdigest()
    locator = await db.scalar(
        select(IdentityToken.user_id).where(
            IdentityToken.digest == digest, IdentityToken.purpose == purpose
        )
    )
    if locator is None:
        raise invalid
    user = await lock_user(db, locator)
    token = await db.scalar(
        select(IdentityToken)
        .where(IdentityToken.digest == digest, IdentityToken.purpose == purpose)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        token is None
        or token.used_at
        or aware(token.expires_at) <= now()
        or not hmac.compare_digest(token.digest, digest)
    ):
        raise invalid
    if purpose == "reset_password":
        valid, message = validate_password_strength(new_password or "")
        if not valid:
            raise HTTPException(400, message)
        user.hashed_password = hash_password(new_password or "")
        await AuthService(db).revoke_all_user_tokens(str(user.id))
    elif purpose == "verify_email":
        user.is_verified = True
    else:
        raise invalid
    token.used_at = now()
    await security_event(db, user, purpose + "_completed")
    await db.flush()


def totp(secret: bytes) -> TOTP:
    # RFC 6238 through the existing cryptography dependency, not a bespoke OTP.
    # SHA-1 is the interoperable TOTP HMAC algorithm, not a password/hash digest.
    return TOTP(secret, 6, hashes.SHA1(), 30)  # nosec B303


def accepted_counter(secret: bytes, code: str, last_counter: int) -> int | None:
    current = int(time.time() // 30)
    for counter in (current, current - 1, current + 1):
        if counter <= last_counter:
            continue
        try:
            totp(secret).verify(code.encode(), counter * 30)
            return counter
        except InvalidToken:
            pass
    return None


async def require_mfa(db: AsyncSession, user: User, code: str | None) -> None:
    from app.core.dependencies import mfa_rate_limiter

    if not user.mfa_enabled:
        return
    await mfa_rate_limiter.check_key("identity-mfa:" + str(user.id))
    if not code:
        raise HTTPException(
            401,
            {
                "code": "mfa_required",
                "message": "Enter your authenticator or recovery code",
            },
        )
    if not user.mfa_secret:
        raise HTTPException(503, "MFA recovery requires operator intervention")
    counter = accepted_counter(
        base64.b32decode(decrypt(user.mfa_secret)), code, user.mfa_last_counter
    )
    if counter is not None:
        user.mfa_last_counter = counter
        await db.flush()
        return
    digest = hashlib.sha256(code.encode()).hexdigest()
    recovery = json.loads(user.mfa_recovery_hashes or "[]")
    matched = next(
        (value for value in recovery if hmac.compare_digest(value, digest)), None
    )
    if matched:
        recovery.remove(matched)
        user.mfa_recovery_hashes = json.dumps(recovery)
        await security_event(db, user, "mfa_recovery_code_used")
        await db.flush()
        return
    raise HTTPException(
        401,
        {
            "code": "mfa_invalid",
            "message": "Invalid or already used authenticator/recovery code",
        },
    )


def check_password(user: User, password: str) -> None:
    if len(password.encode()) > 72 or not verify_password(
        password, user.hashed_password
    ):
        raise HTTPException(401, "Invalid current password")


async def begin_mfa(db: AsyncSession, user: User, password: str) -> dict:
    user = await lock_user(db, str(user.id))
    check_password(user, password)
    if user.mfa_enabled:
        raise HTTPException(409, "MFA is already enabled")
    secret = secrets.token_bytes(20)
    user.mfa_pending_secret = cipher().encrypt(base64.b32encode(secret)).decode()
    user.mfa_pending_expires_at = now() + timedelta(minutes=10)
    await security_event(db, user, "mfa_enrollment_started")
    return {
        "secret": base64.b32encode(secret).decode(),
        "provisioning_uri": totp(secret).get_provisioning_uri(
            user.email, "Azaeron Verity"
        ),
        "expires_at": user.mfa_pending_expires_at,
    }


def recovery_codes(user: User) -> list[str]:
    codes = [secrets.token_urlsafe(16) for _ in range(10)]
    user.mfa_recovery_hashes = json.dumps(
        [hashlib.sha256(code.encode()).hexdigest() for code in codes]
    )
    return codes


async def revoke_other_sessions(db: AsyncSession, user: User) -> None:
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == str(user.id),
            RefreshToken.token_family != user.current_session_family,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now())
    )


async def confirm_mfa(db: AsyncSession, user: User, code: str) -> list[str]:
    from app.core.dependencies import mfa_rate_limiter

    user = await lock_user(db, str(user.id))
    await mfa_rate_limiter.check_key("identity-mfa:" + str(user.id))
    if (
        user.mfa_enabled
        or not user.mfa_pending_secret
        or not user.mfa_pending_expires_at
        or aware(user.mfa_pending_expires_at) <= now()
    ):
        raise HTTPException(400, "MFA enrollment expired or unavailable")
    counter = accepted_counter(
        base64.b32decode(decrypt(user.mfa_pending_secret)), code, -1
    )
    if counter is None:
        raise HTTPException(400, "Invalid authenticator code")
    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_pending_expires_at = None
    user.mfa_enabled = True
    user.mfa_last_counter = counter
    codes = recovery_codes(user)
    await revoke_other_sessions(db, user)
    await security_event(db, user, "mfa_enabled")
    return codes
