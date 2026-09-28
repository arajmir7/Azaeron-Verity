"""Explicit permissions for existing organization roles."""

from enum import Enum

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Membership, OrganizationRole


class Permission(str, Enum):
    DOCUMENT_WRITE = "documents:write"
    EDITORIAL_WRITE = "text:refine"
    JOB_CANCEL = "jobs:cancel"


WRITERS = frozenset(
    {
        OrganizationRole.OWNER,
        OrganizationRole.ADMIN,
        OrganizationRole.FACULTY,
        OrganizationRole.RESEARCHER,
        OrganizationRole.STUDENT,
    }
)
ROLE_PERMISSIONS = {
    role: frozenset(Permission) if role in WRITERS else frozenset()
    for role in OrganizationRole
}


async def require_member_permission(
    db: AsyncSession, organization_id: str, user_id: str, permission: Permission
) -> Membership:
    """Check durable membership for service calls, independent of route guards."""
    member = (
        await db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if not member or permission not in ROLE_PERMISSIONS.get(member.role, frozenset()):
        raise HTTPException(
            status_code=403, detail="Insufficient permission for this action"
        )
    return member


def require_permission(user, permission: Permission) -> None:
    # The role is assigned by get_current_user after an active-membership check.
    if not user.current_organization_id:
        raise HTTPException(status_code=400, detail="No active organization selected")
    if permission not in ROLE_PERMISSIONS.get(user.current_role, frozenset()):
        raise HTTPException(
            status_code=403, detail="Insufficient permission for this action"
        )
