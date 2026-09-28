"""AZAERON authentication schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
import re

from app.core.config import settings


class ProductRole(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    PROFESSOR = "professor"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    INSTITUTION = "institution"


class OnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_role: ProductRole
    workspace_name: str | None = Field(None, min_length=1, max_length=100)

    @field_validator("workspace_name")
    @classmethod
    def valid_workspace_name(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value:
                raise ValueError("Enter a workspace name")
        return value


class UserBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(
                f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters"
            )
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    product_role: ProductRole | None = None
    onboarding_completed: bool = False
    home_path: str = "/check"


class UserProfile(UserResponse):
    organizations: list = Field(default_factory=list)
    active_organization_id: Optional[str] = None
    mfa_enabled: bool = False


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = Field(None, max_length=100)


class TokenResponse(BaseModel):
    # Browser tokens are delivered through HttpOnly cookies. These optional
    # fields remain for response compatibility and are deliberately empty.
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH)
    mfa_code: str | None = Field(None, max_length=100)


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: Optional[str] = None
    expires_days: Optional[int] = None


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    key_prefix: str
    scopes: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    is_active: bool
