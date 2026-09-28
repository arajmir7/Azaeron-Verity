"""Expiring invitations. Delivery is deliberately left to the inviting user."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import apply_tenant_context
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.organizations.models import Membership, Organization, OrganizationRole
from app.modules.organizations.schemas import InvitationResponse, MemberInviteRequest

INVITATION_TTL_SECONDS = 7 * 86400
INVITING_ROLES = {OrganizationRole.OWNER, OrganizationRole.ADMIN}


class InvitationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.signer = URLSafeTimedSerializer(
            settings.SECRET_KEY, salt="workspace-invitation-v1"
        )

    async def issue(
        self, user: User, membership: Membership, data: MemberInviteRequest
    ) -> InvitationResponse:
        if membership.role not in INVITING_ROLES or data.role in INVITING_ROLES:
            raise HTTPException(
                status_code=403,
                detail="Only workspace administrators can invite non-administrator members",
            )
        token = self.signer.dumps(
            {
                "organization_id": membership.organization_id,
                "inviter_id": str(user.id),
                "email": str(data.email).lower(),
                "role": data.role.value,
            }
        )
        await AuditService(self.db).log(
            AuditAction.USER_UPDATED,
            "organization",
            membership.organization_id,
            user_id=str(user.id),
            organization_id=membership.organization_id,
            details={"event": "invitation_created", "role": data.role.value},
        )
        return InvitationResponse(
            token=token,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=INVITATION_TTL_SECONDS),
            organization_name=membership.organization.name,
        )

    async def accept(self, user: User, token: str) -> Organization:
        try:
            payload = self.signer.loads(token, max_age=INVITATION_TTL_SECONDS)
            role = OrganizationRole(payload["role"])
            organization_id = payload["organization_id"]
            inviter_id = payload["inviter_id"]
            email = payload["email"]
        except (
            BadSignature,
            SignatureExpired,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise HTTPException(
                status_code=400, detail="Invitation is invalid or expired"
            ) from error
        if email != user.email.lower() or role in INVITING_ROLES:
            raise HTTPException(
                status_code=403, detail="Invitation is not valid for this account"
            )
        inviter = await AuthService(self.db).get_membership(inviter_id, organization_id)
        if inviter is None or inviter.role not in INVITING_ROLES:
            raise HTTPException(
                status_code=403, detail="Invitation is no longer available"
            )
        # Serialize accept retries for this user. A revoked membership must
        # never be reactivated by replaying an older signed invitation.
        await self.db.execute(
            select(User.id).where(User.id == str(user.id)).with_for_update()
        )
        membership = (
            await self.db.execute(
                select(Membership).where(
                    Membership.user_id == str(user.id),
                    Membership.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if membership is not None and not membership.is_active:
            raise HTTPException(
                status_code=403, detail="Workspace membership has been revoked"
            )
        await apply_tenant_context(self.db, organization_id, str(user.id))
        if membership is None:
            self.db.add(
                Membership(
                    user_id=str(user.id),
                    organization_id=organization_id,
                    role=role,
                    is_active=True,
                    joined_at=datetime.now(timezone.utc),
                    invited_by_id=inviter_id,
                )
            )
            await AuditService(self.db).log(
                AuditAction.USER_UPDATED,
                "organization",
                organization_id,
                organization_id=organization_id,
                user_id=str(user.id),
                details={"event": "invitation_accepted", "role": role.value},
            )
        user.last_active_organization_id = organization_id
        await self.db.flush()
        return inviter.organization
