"""AZAERON authentication service."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.orm import selectinload, lazyload
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    create_access_token,
    create_refresh_token,
    generate_token_id,
    decode_refresh_token,
    generate_sha256_fingerprint,
)
from app.modules.auth.models import User, RefreshToken
from app.modules.auth.schemas import UserCreate, LoginRequest, OnboardingRequest
from app.modules.organizations.models import Organization
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction
from app.core.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def register_user(self, user_data: UserCreate) -> User:
        # Check for existing email
        existing = await self.get_user_by_email(user_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

        # Validate password strength
        is_valid, msg = validate_password_strength(user_data.password)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        user = User(
            email=str(user_data.email).lower().strip(),
            hashed_password=hash_password(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)

        await self.audit.log(
            AuditAction.USER_REGISTERED,
            "user",
            str(user.id),
            details={"email": user.email},
            user_id=str(user.id),
        )
        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user

    async def authenticate(self, login_data: LoginRequest) -> Optional[User]:
        user = await self.get_user_by_email(login_data.email)
        if not user or not user.is_active:
            return None
        if len(login_data.password.encode()) > 72 or not verify_password(
            login_data.password, user.hashed_password
        ):
            return None
        from app.modules.auth.identity import lock_user, require_mfa

        user = await lock_user(self.db, str(user.id))
        if not verify_password(login_data.password, user.hashed_password):
            return None
        await require_mfa(self.db, user, login_data.mfa_code)
        user.last_login_at = datetime.now(timezone.utc)
        await self.db.flush()
        return user

    async def create_token_pair(
        self,
        user: User,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        token_family: Optional[str] = None,
    ) -> dict:
        from app.modules.auth.identity import lock_user

        user = await lock_user(self.db, str(user.id))
        if token_family is None:
            active = list(
                (
                    await self.db.scalars(
                        select(RefreshToken)
                        .where(
                            RefreshToken.user_id == str(user.id),
                            RefreshToken.revoked_at.is_(None),
                            RefreshToken.expires_at > datetime.now(timezone.utc),
                        )
                        .order_by(RefreshToken.created_at.desc())
                    )
                ).all()
            )
            for old in active[99:]:
                old.revoked_at = datetime.now(timezone.utc)
        token_family = token_family or generate_token_id()
        organization_id = await self.resolve_last_organization(user)

        access_token, access_jti, access_exp = create_access_token(
            user_id=str(user.id),
            organization_id=organization_id,
            session_version=user.session_version,
            token_family=token_family,
        )

        refresh_token, refresh_jti, refresh_exp = create_refresh_token(
            user_id=str(user.id),
            token_family=token_family,
        )

        # Store refresh token
        rt = RefreshToken(
            user_id=str(user.id),
            jti=refresh_jti,
            token_family=token_family,
            hashed_token=generate_sha256_fingerprint(refresh_token.encode()),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=refresh_exp,
        )
        self.db.add(rt)
        await self.db.flush()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            # Public OAuth scheme name, not a credential.
            "token_type": "bearer",  # nosec B105
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def resolve_last_organization(self, user: User) -> str | None:
        """Restore preferences only after rechecking active membership."""
        if user.last_active_organization_id:
            membership = await self.get_membership(
                str(user.id), user.last_active_organization_id
            )
            if membership:
                return user.last_active_organization_id
        from app.modules.organizations.service import OrganizationService

        organizations = await OrganizationService(self.db).get_user_organizations(
            str(user.id)
        )
        organization_id = str(organizations[0][0].id) if organizations else None
        user.last_active_organization_id = organization_id
        await self.db.flush()
        return organization_id

    async def complete_onboarding(self, user: User, data: OnboardingRequest) -> User:
        """One personal workspace per user, including concurrent PostgreSQL retries."""
        from app.modules.organizations.service import OrganizationService
        from app.core.database import (
            apply_tenant_context,
            set_organization_context,
            set_user_context,
        )

        # populate_existing reloads a concurrent request's committed pointer
        # after the lock is acquired instead of trusting the identity map.
        user = (
            await self.db.execute(
                select(User)
                .options(lazyload("*"))
                .where(User.id == str(user.id))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        membership = (
            await self.get_membership(str(user.id), user.personal_organization_id)
            if user.personal_organization_id
            else None
        )
        if membership is None:
            name = data.workspace_name or f"{user.first_name or 'My'} workspace"
            organization = await OrganizationService(self.db).create_organization(
                name, str(user.id)
            )
            user.personal_organization_id = str(organization.id)
            membership = await self.get_membership(str(user.id), str(organization.id))
        if membership is None:
            raise HTTPException(
                status_code=409,
                detail="Personal workspace membership could not be created",
            )
        user.product_role = data.product_role.value
        user.onboarding_completed = True
        user.last_active_organization_id = membership.organization_id
        user.current_organization_id = membership.organization_id
        user.current_role = membership.role.value
        set_organization_context(membership.organization_id)
        set_user_context(str(user.id))
        await apply_tenant_context(self.db, membership.organization_id, str(user.id))
        await self.db.flush()
        await self.audit.log(
            AuditAction.USER_UPDATED,
            "user",
            str(user.id),
            user_id=str(user.id),
            organization_id=membership.organization_id,
            details={
                "event": "onboarding_completed",
                "product_role": user.product_role,
            },
        )
        return user

    async def refresh_access_token(self, refresh_token_str: str) -> dict:
        payload = decode_refresh_token(refresh_token_str)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        from app.modules.auth.identity import lock_user

        await lock_user(self.db, payload.sub)
        # Check if token exists and is valid
        # Rotation is a one-time state transition.  The row lock closes the
        # concurrent refresh race where two requests could both observe an
        # unrevoked token before either request committed its revocation.
        result = await self.db.execute(
            select(RefreshToken)
            .where(RefreshToken.jti == payload.jti)
            .with_for_update()
        )
        rt = result.scalar_one_or_none()
        if not rt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired or revoked",
            )
        if rt and rt.revoked_at is not None:
            # Refresh-token reuse means a token in the family may have been
            # stolen. Revoke the whole family, including rotated descendants.
            await self.revoke_token_family(rt.token_family)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token reuse detected",
            )
        expires_at = (
            rt.expires_at
            if rt.expires_at.tzinfo
            else rt.expires_at.replace(tzinfo=timezone.utc)
        )
        if rt.hashed_token != generate_sha256_fingerprint(
            refresh_token_str.encode()
        ) or expires_at < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired or revoked",
            )

        # Issue new pair
        user = await self.get_user_by_id(payload.sub)
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
            )

        # Rotation: a used token is revoked before a replacement is issued.
        rt.revoked_at = datetime.now(timezone.utc)
        tokens = await self.create_token_pair(
            user,
            token_family=rt.token_family,
            ip_address=rt.ip_address,
            user_agent=rt.user_agent,
        )
        new_payload = decode_refresh_token(tokens["refresh_token"])
        rt.replaced_by_jti = new_payload.jti if new_payload else None
        await self.db.flush()
        return tokens

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        # Atomic epoch advancement also invalidates already issued access JWTs.
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                session_version=User.session_version + 1,
            )
        )
        result = await self.db.execute(
            select(RefreshToken).where(
                and_(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            )
        )
        for rt in result.scalars().all():
            rt.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def revoke_token_family(self, token_family: str) -> None:
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_family == token_family,
                RefreshToken.revoked_at.is_(None),
            )
        )
        tokens = list(result.scalars().all())
        for token in tokens:
            token.revoked_at = datetime.now(timezone.utc)
        for user_id in {token.user_id for token in tokens}:
            await self.revoke_all_user_tokens(user_id)
        await self.db.flush()
        # The caller raises a 401 after a replay. Commit explicitly so the
        # request dependency's error rollback cannot undo this security event.
        await self.db.commit()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .options(lazyload("*"))
            .where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).options(lazyload("*")).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_membership(self, user_id: str, organization_id: str):
        from app.modules.organizations.models import Membership

        result = await self.db.execute(
            select(Membership)
            .options(selectinload(Membership.organization).lazyload("*"))
            .where(
                Membership.user_id == user_id,
                Membership.organization_id == organization_id,
                Membership.is_active.is_(True),
                Organization.is_active.is_(True),
            )
            .join(Organization, Organization.id == Membership.organization_id)
        )
        return result.scalar_one_or_none()

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

        user.hashed_password = hash_password(new_password)
        await self.revoke_all_user_tokens(user_id)
        await self.db.flush()

        await self.audit.log(
            AuditAction.USER_UPDATED,
            "user",
            user_id,
            details={"event": "password_changed"},
            user_id=user_id,
        )
