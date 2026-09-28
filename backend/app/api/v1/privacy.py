"""Session-authorized erasure, with a display-once status receipt."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import auth_rate_limiter, get_current_user
from app.modules.auth.models import User
from app.modules.privacy.models import ErasureRequest
from app.modules.privacy.service import receipt_digest, request_erasure

router = APIRouter(prefix="/privacy", tags=["Privacy"])


class ErasureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["account", "organization", "document"]
    target_id: UUID
    current_password: str = Field(min_length=1, max_length=100)
    mfa_code: str | None = Field(default=None, max_length=100)
    confirmation: Literal["ERASE"]


class ErasureAccepted(BaseModel):
    id: str
    status: str
    receipt: str | None
    message: str


class ErasureStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    scope: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    last_error: str | None


@router.post(
    "/erasures",
    status_code=202,
    response_model=ErasureAccepted,
    dependencies=[Depends(auth_rate_limiter)],
)
async def create_erasure(
    data: ErasureCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return await request_erasure(
        db, user, data.scope, str(data.target_id), data.current_password, data.mfa_code
    )


@router.get("/erasures", response_model=list[ErasureStatus])
async def list_erasures(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return list(
        (
            await db.scalars(
                select(ErasureRequest)
                .where(ErasureRequest.requester_id == str(user.id))
                .order_by(ErasureRequest.created_at.desc())
                .limit(100)
            )
        ).all()
    )


@router.get("/erasures/{request_id}", response_model=ErasureStatus)
async def erasure_receipt(
    request_id: UUID,
    response: Response,
    receipt: str = Header(alias="X-Erasure-Receipt", min_length=40, max_length=100),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    result = await db.scalar(
        text("SELECT app.privacy_receipt(:id,:digest)"),
        {"id": str(request_id), "digest": receipt_digest(receipt)},
    )
    if not result:
        raise HTTPException(404, "Erasure receipt not found")
    return result
