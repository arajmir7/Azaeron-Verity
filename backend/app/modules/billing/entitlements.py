"""Server-owned plan limits for Slice 0, without a billing-provider dependency."""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.modules.documents.models import Document
from app.modules.organizations.models import Organization, SubscriptionTier
from app.modules.organizations.schemas import EntitlementLimits, WorkspaceEntitlements


class EntitlementService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def describe(
        self, organization_id: str, *, lock: bool = False
    ) -> WorkspaceEntitlements:
        query = (
            select(Organization)
            .options(lazyload("*"))
            .where(Organization.id == organization_id, Organization.is_active.is_(True))
        )
        if lock:
            from app.modules.billing.usage import UsageService

            await UsageService(self.db).lock(organization_id)
            query = query.with_for_update(read=True).execution_options(
                populate_existing=True
            )
        organization = (await self.db.execute(query)).scalar_one_or_none()
        if organization is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        now = datetime.now(timezone.utc)
        plan = organization.subscription_tier
        expires = organization.subscription_expires_at
        if (
            expires
            and (expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc))
            <= now
        ):
            plan = SubscriptionTier.FREE
        # Paid tiers are provisioned only by trusted server administration.
        # Pricing, seats, paid usage accounting, and checkout are later slices.
        free = plan == SubscriptionTier.FREE
        limits = EntitlementLimits(
            documents_per_month=20 if free else 200,
            max_upload_bytes=(10 if free else 50) * 1024 * 1024,
            max_write_characters=60_000 if free else 200_000,
        )
        # Base.created_at is stored as a UTC timestamp without a timezone.
        # asyncpg requires a matching naive value for this column's bind type.
        start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )
        count = (
            await self.db.execute(
                select(func.count(Document.id)).where(
                    Document.organization_id == organization_id,
                    Document.created_at >= start,
                )
            )
        ).scalar_one()
        from app.modules.billing.models import UsageBucket

        accounted = await self.db.scalar(
            select(UsageBucket).where(
                UsageBucket.organization_id == organization_id,
                UsageBucket.period == now.strftime("%Y-%m"),
                UsageBucket.task == "document_upload",
            )
        )
        if accounted:
            count = max(count, accounted.committed + accounted.reserved)
        return WorkspaceEntitlements(
            organization_id=organization_id,
            plan=plan,
            features=["check", "review", "research", "write"],
            limits=limits,
            documents_this_month=count,
        )

    async def require_upload(
        self, organization_id: str, file_size: int, *, new_document: bool = True
    ) -> None:
        # Serialize quota admission without excluding the shared privacy fences
        # held by document workers. Usage reservations remain atomic.
        entitlements = await self.describe(organization_id, lock=True)
        if file_size > entitlements.limits.max_upload_bytes:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "plan_upload_limit",
                    "message": "This file exceeds your workspace plan's upload limit. Use a smaller file or contact your workspace administrator.",
                },
            )
        if (
            new_document
            and entitlements.documents_this_month
            >= entitlements.limits.documents_per_month
        ):
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "plan_document_limit",
                    "message": "Your workspace has reached its monthly document limit. Existing documents remain available; contact your workspace administrator or try again next month.",
                },
            )

    async def require_write(self, organization_id: str, character_count: int) -> None:
        entitlements = await self.describe(organization_id)
        if character_count > entitlements.limits.max_write_characters:
            raise HTTPException(
                status_code=402,
                detail={
                    "code": "plan_write_limit",
                    "message": "This draft exceeds your workspace plan's revision limit. Select a shorter passage or contact your workspace administrator.",
                },
            )
