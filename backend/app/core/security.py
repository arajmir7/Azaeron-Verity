"""AZAERON security utilities."""

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import jwt
from jwt import InvalidTokenError as JWTError
import bcrypt
from pydantic import BaseModel, Field, ValidationError
import secrets
import hashlib

from app.core.config import settings


class TokenPayload(BaseModel):
    sub: str
    org_id: Optional[str] = None
    jti: str
    type: str
    family: Optional[str] = None
    exp: datetime
    iat: datetime
    session_version: int = Field(default=0, ge=0)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Stable aliases used by services.  Keep one implementation for hashing.
hash_password = get_password_hash


def create_access_token(
    user_id: str,
    organization_id: Optional[str] = None,
    *,
    session_version: int = 0,
    token_family: Optional[str] = None,
) -> Tuple[str, str, datetime]:
    jti = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "org_id": str(organization_id) if organization_id else None,
        "jti": jti,
        "type": "access",
        "session_version": session_version,
        "family": token_family,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256"), jti, expire


def create_refresh_token(
    user_id: str, token_family: Optional[str] = None
) -> Tuple[str, str, datetime]:
    jti = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "family": token_family or generate_token_id(),
        "exp": expire,
        "iat": now,
    }

    token = jwt.encode(payload, settings.REFRESH_SECRET_KEY, algorithm="HS256")
    return token, jti, expire


def decode_access_token(token: str) -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None


def decode_refresh_token(token: str) -> Optional[TokenPayload]:
    try:
        payload = jwt.decode(token, settings.REFRESH_SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        return TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None


def generate_sha256_fingerprint(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def generate_secure_id() -> str:
    return secrets.token_urlsafe(16)


generate_token_id = generate_secure_id


def validate_password_strength(password: str) -> Tuple[bool, str]:
    if len(password.encode("utf-8")) > 72:
        return False, "Password must contain at most 72 UTF-8 bytes"
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return (
            False,
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters",
        )

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(not c.isalnum() for c in password)

    if not (has_upper and has_lower and has_digit and has_special):
        return (
            False,
            "Password must contain uppercase, lowercase, digit, and special character",
        )

    return True, "Password is strong"
