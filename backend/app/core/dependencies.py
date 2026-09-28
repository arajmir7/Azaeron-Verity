"""AZAERON FastAPI dependencies."""

from datetime import datetime, timezone
from typing import Optional
import time
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    get_db,
    set_organization_context,
    set_user_context,
    apply_tenant_context,
)
from app.core.config import settings
from app.core.security import decode_access_token, TokenPayload
from app.modules.auth.service import AuthService
from app.modules.auth.models import User, RefreshToken
from app.modules.organizations.models import Membership, OrganizationRole
from app.core.observability import record_redis

security_bearer = HTTPBearer(auto_error=False)
security_api_key = APIKeyHeader(
    name="X-API-Key", auto_error=False, scheme_name="AzaeronAPIKey"
)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    api_key: Optional[str] = Depends(security_api_key),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> User:
    if request.headers.get("x-api-key") is not None:
        from app.modules.auth.api_keys import authenticate_api_key

        if request.headers.get("authorization") is not None:
            raise HTTPException(401, "Ambiguous authentication credentials")
        return await authenticate_api_key(db, request, api_key or "")
    token = None
    if credentials:
        token = credentials.credentials
    elif request.headers.get("authorization") is not None:
        # Never let an invalid explicit credential fall back to a browser cookie.
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(payload.sub)

    if (
        not user
        or not user.is_active
        or payload.session_version != user.session_version
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    active_session = (
        await db.scalar(
            select(RefreshToken.id)
            .where(
                RefreshToken.user_id == str(user.id),
                RefreshToken.token_family == payload.family,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .limit(1)
        )
        if payload.family
        else None
    )
    if not active_session:
        raise HTTPException(401, "Session expired or revoked")
    user.current_session_family = payload.family
    user.current_organization_id = None
    user.current_role = None
    user.current_api_key_id = None
    db.info["api_key_id"] = None
    user.current_api_scopes = ()
    set_organization_context(None)
    set_user_context(payload.sub)
    await apply_tenant_context(db, None, payload.sub)
    if payload.org_id:
        membership = await auth_service.get_membership(payload.sub, payload.org_id)
        if membership:
            set_organization_context(payload.org_id)
            set_user_context(payload.sub)
            await apply_tenant_context(db, payload.org_id, payload.sub)
            user.current_organization_id = payload.org_id
            user.current_role = membership.role

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


def require_active_organization(
    current_user: User = Depends(get_current_active_user),
) -> str:
    """Return the server-authorized tenant from the access token.

    A missing workspace is a client-state validation failure, not an
    authorization failure.  Route handlers must never accept an organization
    ID supplied by the browser as a substitute for this value.
    """
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "active_organization_required",
                "message": "Select an organization before accessing tenant-owned resources.",
            },
        )
    return current_user.current_organization_id


async def require_organization_access(
    org_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> Membership:
    auth_service = AuthService(db)
    membership = await auth_service.get_membership(str(current_user.id), org_id)

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found or access denied",
        )

    set_organization_context(org_id)
    set_user_context(str(current_user.id))
    await apply_tenant_context(db, org_id, str(current_user.id))
    return membership


def require_role(allowed_roles: list[OrganizationRole]):
    async def role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if (
            not hasattr(current_user, "current_role")
            or current_user.current_role not in allowed_roles
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return current_user

    return role_checker


class RateLimiter:
    def __init__(self, requests: int = 100, window: int = 60):
        self.requests = requests
        self.window = window
        self._fallback: dict[str, tuple[int, float]] = {}

    async def __call__(self, request: Request):
        key = f"rate-limit:{request.client.host if request.client else 'unknown'}:{request.url.path}"
        await self.check_key(key)

    async def check_key(self, key: str):
        from redis.asyncio import Redis
        from app.core.config import settings

        redis = Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        )
        try:
            count = await redis.eval(
                "local count = redis.call('INCR', KEYS[1]); "
                "if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; return count",
                1,
                key,
                self.window,
            )
            record_redis("rate_limit", "success")
            if count > self.requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(self.window)},
                )
        except HTTPException:
            raise
        except Exception:
            if settings.ENVIRONMENT == "production":
                record_redis("rate_limit", "unavailable")
                raise HTTPException(
                    status_code=503,
                    detail="Rate limiting is temporarily unavailable",
                    headers={"Retry-After": "5"},
                )
            record_redis("rate_limit", "fallback")
            # Retain bounded, process-local protection when Redis is recovering.
            now = time.monotonic()
            count, reset = self._fallback.get(key, (0, now + self.window))
            if now >= reset:
                count, reset = 0, now + self.window
            count += 1
            self._fallback[key] = (count, reset)
            if len(self._fallback) > 10_000:
                self._fallback = {
                    k: value for k, value in self._fallback.items() if value[1] > now
                }
                if len(self._fallback) > 10_000:
                    self._fallback.pop(next(iter(self._fallback)))
            if count > self.requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(max(1, int(reset - now)))},
                )
        finally:
            await redis.aclose()


rate_limiter = RateLimiter(
    requests=settings.RATE_LIMIT_REQUESTS,
    window=settings.RATE_LIMIT_WINDOW_SECONDS,
)
# Authentication endpoints need a substantially tighter per-IP limit than
# ordinary authenticated reads.  This does not replace credential lockout or
# an identity-provider policy, but it prevents cheap online brute force at the
# application edge.
auth_rate_limiter = RateLimiter(requests=10, window=60)
editorial_rate_limiter = RateLimiter(requests=30, window=60)
api_key_rate_limiter = RateLimiter(requests=60, window=60)
api_tenant_rate_limiter = RateLimiter(requests=300, window=60)

identity_rate_limiter = RateLimiter(requests=3, window=600)
mfa_rate_limiter = RateLimiter(requests=10, window=300)
