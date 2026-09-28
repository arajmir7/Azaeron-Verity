"""AZAERON auth API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.dependencies import auth_rate_limiter, get_current_user
from app.core.logging import get_logger
from app.modules.auth.schemas import (
    UserCreate,
    UserResponse,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    ChangePasswordRequest,
    UserProfile,
    OnboardingRequest,
)
from app.modules.auth.models import User
from app.modules.auth.service import AuthService
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _set_auth_cookies(response: Response, tokens: dict) -> None:
    response.set_cookie(
        "access_token",
        tokens["access_token"],
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        tokens["refresh_token"],
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limiter)],
)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    auth_service = AuthService(db)
    user = await auth_service.register_user(user_data)
    return user


@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limiter)]
)
async def login(
    login_data: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    auth_service = AuthService(db)
    user = await auth_service.authenticate(login_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    tokens = await auth_service.create_token_pair(
        user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512],
    )
    _set_auth_cookies(response, tokens)
    audit = AuditService(db)
    await audit.log(
        AuditAction.USER_LOGIN,
        "user",
        str(user.id),
        user_id=str(user.id),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:512],
    )
    return TokenResponse(
        access_token=None,
        refresh_token=None,
        token_type=tokens["token_type"],
        expires_in=tokens["expires_in"],
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/refresh", response_model=TokenResponse, dependencies=[Depends(auth_rate_limiter)]
)
async def refresh(
    refresh_data: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db, scope="function"),
):
    auth_service = AuthService(db)
    token = refresh_data.refresh_token or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required"
        )
    tokens = await auth_service.refresh_access_token(token)
    _set_auth_cookies(response, tokens)
    from app.core.security import decode_access_token

    payload = decode_access_token(tokens["access_token"])
    user = await auth_service.get_user_by_id(payload.sub) if payload else None
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenResponse(
        access_token=None,
        refresh_token=None,
        token_type=tokens["token_type"],
        expires_in=tokens["expires_in"],
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    auth_service = AuthService(db)
    await auth_service.revoke_all_user_tokens(str(current_user.id))
    response.delete_cookie(key="access_token", path="/", domain=settings.COOKIE_DOMAIN)
    response.delete_cookie(key="refresh_token", path="/", domain=settings.COOKIE_DOMAIN)
    audit = AuditService(db)
    await audit.log(
        AuditAction.USER_LOGOUT,
        "user",
        str(current_user.id),
        user_id=str(current_user.id),
    )
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await _user_profile(current_user, db)


async def _user_profile(current_user: User, db: AsyncSession) -> UserProfile:
    from app.modules.organizations.service import OrganizationService

    org_service = OrganizationService(db)
    orgs = await org_service.get_user_organizations(str(current_user.id))
    profile = UserProfile.model_validate(current_user)
    profile.organizations = [
        {
            "id": str(m.id),
            "organization_id": str(o.id),
            "organization_name": o.name,
            "organization_slug": o.slug,
            "role": m.role,
            "is_active": m.is_active,
            "joined_at": m.joined_at,
            "subscription_tier": o.subscription_tier,
        }
        for o, m in orgs
    ]
    # This ID is informational only. Tenant-scoped routes derive their active
    # organization from the signed access token and re-check membership.
    profile.active_organization_id = current_user.current_organization_id
    return profile


@router.post("/onboarding", response_model=UserProfile)
async def complete_onboarding(
    data: OnboardingRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user = await AuthService(db).complete_onboarding(current_user, data)
    from app.core.security import create_access_token
    from app.api.v1.organizations import _set_access_cookie

    access_token, _, _ = create_access_token(
        str(user.id),
        user.current_organization_id,
        session_version=user.session_version,
        token_family=current_user.current_session_family,
    )
    _set_access_cookie(response, access_token)
    return await _user_profile(user, db)


@router.post("/change-password", dependencies=[Depends(auth_rate_limiter)])
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.modules.auth.identity import lock_user, require_mfa

    current_user = await lock_user(db, str(current_user.id))
    await require_mfa(db, current_user, data.mfa_code)
    auth_service = AuthService(db)
    await auth_service.change_password(
        str(current_user.id), data.current_password, data.new_password
    )
    return {"message": "Password changed successfully. Please log in again."}


@router.post("/forgot-password", dependencies=[Depends(auth_rate_limiter)])
async def forgot_password(
    data: PasswordResetRequest, db: AsyncSession = Depends(get_db, scope="function")
):
    from app.modules.auth.identity import request_email

    await request_email(db, str(data.email), "reset_password")
    return {"message": "If this account exists, a password reset link will be sent."}


@router.post("/reset-password", dependencies=[Depends(auth_rate_limiter)])
async def reset_password(
    data: PasswordResetConfirm, db: AsyncSession = Depends(get_db, scope="function")
):
    from app.modules.auth.identity import consume_email

    await consume_email(db, data.token, "reset_password", data.new_password)
    return {"message": "Password reset. Sign in again; existing MFA remains required."}
