"""Email verification, MFA and per-device session controls."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, auth_rate_limiter
from app.modules.auth.models import RefreshToken, User
from app.modules.auth import identity

router = APIRouter(prefix="/auth", tags=["Identity"])


class TokenConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=30, max_length=100)


class PasswordProof(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=100)


class MFAProof(PasswordProof):
    mfa_code: str = Field(min_length=1, max_length=100)


class MFACode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SessionMetadata(BaseModel):
    id: str
    current: bool
    created_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None


@router.post("/verification/request", dependencies=[Depends(auth_rate_limiter)])
async def request_verification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await identity.request_email(db, user.email, "verify_email")
    return {"message": "If verification is needed, a link will be sent to your email."}


@router.post("/verification/confirm", dependencies=[Depends(auth_rate_limiter)])
async def confirm_verification(
    data: TokenConfirm, db: AsyncSession = Depends(get_db, scope="function")
):
    await identity.consume_email(db, data.token, "verify_email")
    return {"message": "Email verified."}


@router.post("/mfa/enroll", dependencies=[Depends(auth_rate_limiter)])
async def enroll(
    data: PasswordProof,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    return await identity.begin_mfa(db, user, data.current_password)


@router.post("/mfa/confirm", dependencies=[Depends(auth_rate_limiter)])
async def confirm(
    data: MFACode,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    response.headers["Cache-Control"] = "no-store"
    codes = await identity.confirm_mfa(db, user, data.code)
    return {
        "recovery_codes": codes,
        "message": "MFA enabled. Other sessions were revoked. Save these recovery codes now.",
    }


@router.post("/mfa/recovery", dependencies=[Depends(auth_rate_limiter)])
async def regenerate_recovery(
    data: MFAProof,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user = await identity.lock_user(db, str(user.id))
    identity.check_password(user, data.current_password)
    if not user.mfa_enabled:
        raise HTTPException(409, "MFA is not enabled")
    await identity.require_mfa(db, user, data.mfa_code)
    codes = identity.recovery_codes(user)
    await identity.security_event(db, user, "mfa_recovery_codes_replaced")
    response.headers["Cache-Control"] = "no-store"
    return {"recovery_codes": codes}


@router.post("/mfa/disable", dependencies=[Depends(auth_rate_limiter)])
async def disable(
    data: MFAProof,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user = await identity.lock_user(db, str(user.id))
    identity.check_password(user, data.current_password)
    if not user.mfa_enabled:
        raise HTTPException(409, "MFA is not enabled")
    await identity.require_mfa(db, user, data.mfa_code)
    user.mfa_enabled = False
    user.mfa_secret = user.mfa_pending_secret = user.mfa_recovery_hashes = None
    user.mfa_pending_expires_at = None
    user.mfa_last_counter = -1
    await identity.revoke_other_sessions(db, user)
    await identity.security_event(db, user, "mfa_disabled")
    return {"message": "MFA disabled. Other sessions were revoked."}


@router.get("/sessions", response_model=list[SessionMetadata])
async def sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    records = (
        await db.scalars(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == str(user.id),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > identity.now(),
            )
            .order_by(RefreshToken.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        SessionMetadata(
            id=record.token_family,
            current=record.token_family == user.current_session_family,
            created_at=record.created_at,
            expires_at=record.expires_at,
            ip_address=record.ip_address,
            user_agent=record.user_agent,
        )
        for record in records
    ]


@router.delete("/sessions/others", status_code=204)
async def revoke_others(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user = await identity.lock_user(db, str(user.id))
    await identity.revoke_other_sessions(db, user)
    await identity.security_event(db, user, "other_sessions_revoked")


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    user = await identity.lock_user(db, str(user.id))
    existing = await db.scalar(
        select(RefreshToken.id)
        .where(
            RefreshToken.user_id == str(user.id),
            RefreshToken.token_family == session_id,
        )
        .limit(1)
    )
    if existing is None:
        raise HTTPException(404, "Session not found")
    await db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == str(user.id),
            RefreshToken.token_family == session_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=identity.now())
    )
    await identity.security_event(db, user, "session_revoked")
