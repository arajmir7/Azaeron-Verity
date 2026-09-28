"""AZAERON audit logging service."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text, func

from app.modules.audit.models import AuditLog, AuditAction
from app.modules.audit.schemas import (
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogResponse,
)


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> AuditLog:
        if (
            organization_id is None
            and user_id
            and self.db.bind
            and self.db.bind.dialect.name == "postgresql"
        ):
            # Account events have a user boundary even without a workspace.
            # Keep the caller's active workspace setting intact.
            await self.db.execute(
                text("SELECT set_config('app.current_user_id', :value, true)"),
                {"value": user_id},
            )
        if request_id is None:
            try:
                from app.core.request_context import request_id_ctx

                request_id = request_id_ctx.get()
            except ImportError:
                pass
        log_entry = AuditLog(
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
        )
        self.db.add(log_entry)
        await self.db.flush()
        return log_entry

    async def get_logs(
        self,
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogListResponse:
        query = select(AuditLog).order_by(desc(AuditLog.timestamp))
        if organization_id:
            query = query.where(AuditLog.organization_id == organization_id)
        if user_id:
            query = query.where(AuditLog.user_id == user_id)
        if action:
            query = query.where(AuditLog.action == action)

        total = await self.db.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)

        return AuditLogListResponse(
            items=[AuditLogResponse.model_validate(row) for row in result.scalars()],
            total=total or 0,
            page=page,
            page_size=page_size,
        )
