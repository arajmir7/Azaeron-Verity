"""Tenant-bound random API credentials. Only SHA-256 digests are persisted."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Literal, get_args
from uuid import UUID, uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    apply_tenant_context,
    set_organization_context,
    set_user_context,
)
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.auth.models import ApiKey, User
from app.modules.auth.service import AuthService
from app.modules.organizations.models import Organization, OrganizationRole

Scope = Literal[
    "text:analyze",
    "text:refine",
    "text:verify",
    "documents:read",
    "documents:write",
    "usage:read",
    "ai:chat",
]
SCOPES = frozenset(get_args(Scope))


class KeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f\x7f]+$")
    scopes: list[Scope] = Field(min_length=1, max_length=7)
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def unique_scopes(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicate scopes")
        return sorted(value)

    @field_validator("expires_at")
    @classmethod
    def future_expiry(cls, value):
        if value is not None and (
            value.tzinfo is None
            or not datetime.now(timezone.utc)
            < value
            <= datetime.now(timezone.utc) + timedelta(days=365)
        ):
            raise ValueError(
                "Expiry must be timezone-aware and within the next 365 days"
            )
        return value.astimezone(timezone.utc) if value is not None else None


class KeyMetadata(BaseModel):
    id: str
    name: str
    key_prefix: str
    user_id: str
    organization_id: str
    scopes: list[Scope]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    is_active: bool
    rotated_from_id: str | None


class CreatedKey(BaseModel):
    key: KeyMetadata
    secret: str


def metadata(key: ApiKey) -> KeyMetadata:
    return KeyMetadata(
        **{
            name: getattr(key, name)
            for name in KeyMetadata.model_fields
            if name != "scopes"
        },
        scopes=json.loads(key.scopes or "[]"),
    )


def scope_for_route(method: str, path: str) -> str | None:
    """Closed allowlist of public operations, shared by authentication and OpenAPI."""
    if method == "POST":
        own = {
            "/api/v1/ai/chat": "ai:chat",
            "/api/v1/ai/chat/stream": "ai:chat",
            "/api/v1/humanize": "text:refine",
            "/api/v1/detect": "text:analyze",
            "/api/v1/plagiarism/check": "documents:write",
        }
        if path in own:
            return own[path]
    if method == "POST" and path in {
        "/api/v1/text/analyze",
        "/api/v1/text/refine",
        "/api/v1/text/verify",
    }:
        return "text:" + path.rsplit("/", 1)[1]
    if path == "/api/v1/usage" and method == "GET":
        return "usage:read"
    if path == "/api/v1/models" and method == "GET":
        return "text:analyze"
    if path == "/api/v1/documents" or path.startswith("/api/v1/documents/"):
        return (
            "documents:read"
            if method == "GET"
            else (
                "documents:write"
                if method in {"POST", "PATCH", "PUT", "DELETE"}
                else None
            )
        )
    if path == "/api/v1/jobs" or path.startswith("/api/v1/jobs/"):
        return (
            "documents:read"
            if method == "GET"
            else (
                "documents:write"
                if method == "POST" and path.endswith("/cancel")
                else None
            )
        )
    return None


async def require_key_manager(db: AsyncSession, user: User) -> str:
    if user.current_api_key_id:
        raise HTTPException(403, "API keys cannot manage credentials")
    org_id = user.current_organization_id
    if not org_id:
        raise HTTPException(400, "Select an organization")
    membership = await AuthService(db).get_membership(str(user.id), org_id)
    if not membership or membership.role not in {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
    }:
        raise HTTPException(403, "Organization administrator required")
    return org_id


async def create_key(
    db: AsyncSession, user: User, data: KeyCreate, rotated_from: ApiKey | None = None
) -> CreatedKey:
    org_id = await require_key_manager(db, user)
    await db.execute(
        select(Organization.id)
        .where(Organization.id == org_id)
        .with_for_update(read=True)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        from sqlalchemy import text

        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "api-key-cap:" + org_id},
        )
    count = await db.scalar(
        select(func.count())
        .select_from(ApiKey)
        .where(ApiKey.organization_id == org_id, ApiKey.is_active.is_(True))
    )
    if count is not None and count >= 50:
        raise HTTPException(409, "Active API-key limit reached")
    key_id = str(uuid4())
    secret = f"avk.{org_id}.{key_id}.{secrets.token_urlsafe(32)}"
    record = ApiKey(
        id=key_id,
        user_id=str(user.id),
        organization_id=org_id,
        name=data.name,
        key_prefix="avk_" + key_id[:4],
        hashed_key=hashlib.sha256(secret.encode()).hexdigest(),
        scopes=json.dumps(data.scopes),
        expires_at=data.expires_at,
        credential_version=1,
        rotated_from_id=str(rotated_from.id) if rotated_from else None,
    )
    db.add(record)
    await db.flush()
    await AuditService(db).log(
        AuditAction.API_KEY_CREATED,
        "api_key",
        key_id,
        details={"scopes": data.scopes, "rotated_from_id": record.rotated_from_id},
        user_id=str(user.id),
        organization_id=org_id,
    )
    return CreatedKey(key=metadata(record), secret=secret)


async def revoke_key(db: AsyncSession, user: User, key: ApiKey) -> None:
    if key.is_active:
        key.is_active = False
        key.revoked_at = datetime.now(timezone.utc)
        await AuditService(db).log(
            AuditAction.API_KEY_REVOKED,
            "api_key",
            str(key.id),
            user_id=str(user.id),
            organization_id=key.organization_id,
        )
        await db.flush()


async def authenticate_api_key(db: AsyncSession, request: Request, secret: str) -> User:
    from app.core.dependencies import api_key_rate_limiter, api_tenant_rate_limiter

    invalid = HTTPException(
        401, "Invalid or expired API key", headers={"WWW-Authenticate": "AzaeronAPIKey"}
    )
    try:
        prefix, org_id, key_id, entropy = secret.split(".")
        if (
            prefix != "avk"
            or str(UUID(org_id)) != org_id
            or str(UUID(key_id)) != key_id
            or len(entropy) != 43
        ):
            raise ValueError
    except ValueError:
        raise invalid from None
    # The untrusted tenant locator only permits credential lookup. It grants no
    # user context and cannot authenticate without the complete matching secret.
    await apply_tenant_context(db, org_id, None)
    key = await db.scalar(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == org_id,
            ApiKey.credential_version == 1,
        )
    )
    digest = hashlib.sha256(secret.encode()).hexdigest()
    expected = key.hashed_key if key else "0" * 64
    if (
        not hmac.compare_digest(digest, expected)
        or not key
        or not key.is_active
        or key.revoked_at is not None
    ):
        raise invalid
    now = datetime.now(timezone.utc)
    if key.expires_at and key.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise invalid
    service = AuthService(db)
    user = await service.get_user_by_id(key.user_id)
    member = await service.get_membership(key.user_id, org_id)
    if not user or not user.is_active or not member:
        raise invalid
    try:
        scopes = json.loads(key.scopes or "[]")
        if (
            not isinstance(scopes, list)
            or not scopes
            or any(scope not in SCOPES for scope in scopes)
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise invalid from None
    required = scope_for_route(request.method, request.url.path)
    if required is None or required not in scopes:
        raise HTTPException(403, "API-key scope does not permit this operation")
    await api_key_rate_limiter.check_key(f"api-key-rate:{key_id}")
    await api_tenant_rate_limiter.check_key(f"api-tenant-rate:{org_id}")
    # Release the credential row before a long-running operation. Revocation
    # takes effect on subsequent authentication, not already admitted work.
    touched = await db.execute(
        update(ApiKey)
        .where(
            ApiKey.id == key_id, ApiKey.is_active.is_(True), ApiKey.revoked_at.is_(None)
        )
        .values(last_used_at=now)
    )
    if touched.rowcount != 1:
        raise invalid
    await db.commit()
    set_organization_context(org_id)
    set_user_context(str(user.id))
    await apply_tenant_context(db, org_id, str(user.id))
    user.current_organization_id = org_id
    user.current_role = member.role
    user.current_api_key_id = key_id
    db.info["api_key_id"] = key_id
    user.current_api_scopes = tuple(scopes)
    request.state.api_key_id = key_id
    return user
