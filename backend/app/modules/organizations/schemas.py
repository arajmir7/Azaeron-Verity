"""AZAERON organization schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr, ConfigDict

from app.modules.organizations.models import OrganizationRole, SubscriptionTier


class OrganizationBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class OrganizationResponse(OrganizationBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    is_active: bool
    subscription_tier: SubscriptionTier
    created_at: datetime
    updated_at: datetime


class OrganizationMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    organization_name: str
    organization_slug: str
    role: OrganizationRole
    is_active: bool
    joined_at: datetime


class MemberInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: OrganizationRole = OrganizationRole.STUDENT


class InvitationResponse(BaseModel):
    token: str
    expires_at: datetime
    organization_name: str


class InvitationAcceptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=4096)


class EntitlementLimits(BaseModel):
    documents_per_month: int
    max_upload_bytes: int
    max_write_characters: int


class WorkspaceEntitlements(BaseModel):
    organization_id: str
    plan: SubscriptionTier
    features: list[str]
    limits: EntitlementLimits
    documents_this_month: int


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    email: str
    full_name: str
    role: OrganizationRole
    is_active: bool
    joined_at: datetime


class UsageStatsResponse(BaseModel):
    documents_month: int
    storage_mb: int
    api_calls: int
    subscription_tier: SubscriptionTier
