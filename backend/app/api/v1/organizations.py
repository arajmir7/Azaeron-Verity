"""AZAERON organization API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.core.dependencies import get_current_active_user, require_role
from app.modules.auth.models import User
from app.modules.organizations.schemas import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    MemberInviteRequest,
    MemberResponse,
    InvitationResponse,
    InvitationAcceptRequest,
    WorkspaceEntitlements,
)
from app.modules.organizations.service import OrganizationService
from app.modules.organizations.models import OrganizationRole
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction

router = APIRouter(prefix="/organizations", tags=["Organizations"])


def _set_access_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/invitations/accept", response_model=OrganizationResponse)
async def accept_invitation(
    data: InvitationAcceptRequest,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.modules.organizations.invitations import InvitationService

    organization = await InvitationService(db).accept(current_user, data.token)
    token, _, _ = create_access_token(
        str(current_user.id),
        str(organization.id),
        session_version=current_user.session_version,
        token_family=current_user.current_session_family,
    )
    _set_access_cookie(response, token)
    return organization


@router.post(
    "/{org_id}/invitations", response_model=InvitationResponse, status_code=201
)
async def create_invitation(
    org_id: str,
    data: MemberInviteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.core.dependencies import require_organization_access
    from app.modules.organizations.invitations import InvitationService

    membership = await require_organization_access(org_id, current_user, db)
    return await InvitationService(db).issue(current_user, membership, data)


@router.get("/{org_id}/entitlements", response_model=WorkspaceEntitlements)
async def get_entitlements(
    org_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.core.dependencies import require_organization_access
    from app.modules.billing.entitlements import EntitlementService

    await require_organization_access(org_id, current_user, db)
    return await EntitlementService(db).describe(org_id)


@router.post(
    "", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED
)
async def create_organization(
    data: OrganizationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    org_service = OrganizationService(db)
    org = await org_service.create_organization(
        name=data.name, owner_id=str(current_user.id), description=data.description
    )
    return org


@router.get("", response_model=list[OrganizationResponse])
async def list_organizations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    org_service = OrganizationService(db)
    orgs = await org_service.get_user_organizations(str(current_user.id))
    return [o for o, _ in orgs]


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.core.dependencies import require_organization_access

    membership = await require_organization_access(org_id, current_user, db)
    return membership.organization


@router.patch("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.core.dependencies import require_organization_access

    membership = await require_organization_access(org_id, current_user, db)
    if membership.role not in [OrganizationRole.OWNER, OrganizationRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    org_service = OrganizationService(db)
    return await org_service.update_organization(org_id, data)


@router.post("/{org_id}/select", response_model=OrganizationResponse)
async def select_organization(
    org_id: str,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Set the active organization into a short-lived access token."""
    from app.core.dependencies import require_organization_access

    membership = await require_organization_access(org_id, current_user, db)
    current_user.last_active_organization_id = org_id
    await db.flush()
    access_token, _, _ = create_access_token(
        str(current_user.id),
        org_id,
        session_version=current_user.session_version,
        token_family=current_user.current_session_family,
    )
    _set_access_cookie(response, access_token)
    return membership.organization
