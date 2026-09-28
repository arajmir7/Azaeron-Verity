"""AZAERON organization service."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload
from sqlalchemy import select, and_, func
from fastapi import HTTPException, status
import re
from uuid import uuid4

from app.modules.organizations.models import Organization, Membership, OrganizationRole
from app.modules.organizations.schemas import OrganizationCreate, OrganizationUpdate
from app.modules.auth.models import User
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction
from app.core.database import (
    apply_tenant_context,
    set_organization_context,
    set_user_context,
)


class OrganizationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    def _generate_slug(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug[:255]

    async def create_organization(
        self, name: str, owner_id: str, description: Optional[str] = None
    ) -> Organization:
        # Common personal-workspace names must not race on a read-then-insert
        # slug loop during simultaneous signups.
        slug = f"{self._generate_slug(name)[:220] or 'workspace'}-{uuid4().hex}"

        org = Organization(
            name=name, slug=slug, description=description, is_active=True
        )
        self.db.add(org)
        await self.db.flush()
        await self.db.refresh(org)

        membership = Membership(
            user_id=owner_id,
            organization_id=str(org.id),
            role=OrganizationRole.OWNER,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
        self.db.add(membership)
        await self.db.flush()

        # The organization does not exist until this transaction creates it,
        # so an authenticated create request cannot carry an org-scoped RLS
        # setting beforehand. Bind the new tenant before writing its audit
        # event and before any further tenant-owned work in this transaction.
        set_organization_context(str(org.id))
        set_user_context(owner_id)
        await apply_tenant_context(self.db, str(org.id), owner_id)

        await self.audit.log(
            AuditAction.ORG_CREATED,
            "organization",
            str(org.id),
            details={"name": name, "slug": slug},
            user_id=owner_id,
            organization_id=str(org.id),
        )
        return org

    async def get_by_id(self, org_id: str) -> Optional[Organization]:
        result = await self.db.execute(
            select(Organization).options(lazyload("*")).where(Organization.id == org_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        result = await self.db.execute(
            select(Organization).options(lazyload("*")).where(Organization.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_user_organizations(self, user_id: str):
        result = await self.db.execute(
            select(Organization, Membership)
            .options(lazyload("*"))
            .join(Membership, Membership.organization_id == Organization.id)
            .where(
                and_(
                    Membership.user_id == user_id,
                    Membership.is_active,
                    Organization.is_active,
                )
            )
            .order_by(Organization.created_at.desc())
        )
        return result.all()

    async def update_organization(
        self, org_id: str, update_data: OrganizationUpdate
    ) -> Organization:
        org = await self.get_by_id(org_id)
        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found"
            )
        if update_data.name is not None:
            org.name = update_data.name
        if update_data.description is not None:
            org.description = update_data.description
        if update_data.is_active is not None:
            org.is_active = update_data.is_active
        await self.db.flush()
        await self.db.refresh(org)
        return org
