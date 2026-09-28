"""Session-only organization API-key lifecycle."""

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.modules.auth.models import ApiKey, User
from app.modules.auth.api_keys import (
    CreatedKey,
    KeyCreate,
    KeyMetadata,
    create_key,
    metadata,
    require_key_manager,
    revoke_key,
)
from app.modules.organizations.models import Organization

router = APIRouter(prefix="/api-keys", tags=["API keys"])


@router.post("", response_model=CreatedKey, status_code=201)
async def create(
    data: KeyCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return await create_key(db, user, data)


@router.get("", response_model=list[KeyMetadata])
async def listing(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    org_id = await require_key_manager(db, user)
    rows = await db.scalars(
        select(ApiKey)
        .where(ApiKey.organization_id == org_id, ApiKey.credential_version == 1)
        .order_by(ApiKey.created_at.desc(), ApiKey.id)
        .offset(offset)
        .limit(limit)
    )
    return [metadata(row) for row in rows]


async def locked_key(db: AsyncSession, user: User, key_id: UUID) -> ApiKey:
    org_id = await require_key_manager(db, user)
    await db.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )
    key = await db.scalar(
        select(ApiKey)
        .where(
            ApiKey.id == str(key_id),
            ApiKey.organization_id == org_id,
            ApiKey.credential_version == 1,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not key:
        raise HTTPException(404, "API key not found")
    return key


@router.delete("/{key_id}", status_code=204)
async def revoke(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    key = await locked_key(db, user, key_id)
    await revoke_key(db, user, key)


@router.post("/{key_id}/rotate", response_model=CreatedKey, status_code=201)
async def rotate(
    key_id: UUID,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    key = await locked_key(db, user, key_id)
    if not key.is_active:
        raise HTTPException(409, "API key was already revoked or rotated")
    expiry = key.expires_at.replace(tzinfo=timezone.utc) if key.expires_at else None
    if expiry is not None and expiry <= datetime.now(timezone.utc):
        raise HTTPException(409, "Expired API keys cannot be rotated")
    data = KeyCreate(name=key.name, scopes=metadata(key).scopes, expires_at=expiry)
    await revoke_key(db, user, key)
    response.headers["Cache-Control"] = "no-store"
    return await create_key(db, user, data, rotated_from=key)
