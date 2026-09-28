"""Tenant totals and the caller's bounded operation metadata; no cached text."""

from fastapi import APIRouter, Depends, Query
from datetime import datetime
from typing import Literal
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_active_organization
from app.modules.auth.models import User
from app.modules.billing.models import UsageOperation
from app.modules.billing.usage import UsageService

router = APIRouter(tags=["Usage"])


class UsageLimit(BaseModel):
    task: str
    limit: int
    reserved: int
    committed: int


class ModelUsage(BaseModel):
    model_id: str
    model_revision: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class OperationUsage(BaseModel):
    operation_id: str
    request_id: str | None
    task: str
    status: Literal["RESERVED", "COMMITTED", "RELEASED"]
    outcome: str | None
    chargeable: bool
    billable: bool
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    model_calls: list[ModelUsage]
    created_at: datetime
    completed_at: datetime | None


class UsageResponse(BaseModel):
    period: str
    unit: Literal["operations"]
    billing_enabled: bool
    limits: list[UsageLimit]
    recent_operations: list[OperationUsage]


@router.get("/usage", response_model=UsageResponse)
async def usage(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    result = await UsageService(db).summary(organization_id)
    query = select(UsageOperation).where(
        UsageOperation.organization_id == organization_id,
        UsageOperation.user_id == str(user.id),
    )
    if user.current_api_key_id:
        query = query.where(UsageOperation.api_key_id == user.current_api_key_id)
    records = (
        await db.scalars(
            query.order_by(UsageOperation.created_at.desc(), UsageOperation.id).limit(
                limit
            )
        )
    ).all()
    fields = (
        "operation_id",
        "request_id",
        "task",
        "status",
        "outcome",
        "chargeable",
        "billable",
        "input_tokens",
        "output_tokens",
        "duration_ms",
        "model_calls",
        "created_at",
        "completed_at",
    )
    result["recent_operations"] = [
        {name: getattr(record, name) for name in fields} for record in records
    ]
    return result
