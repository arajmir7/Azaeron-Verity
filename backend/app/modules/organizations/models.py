"""AZAERON organization models."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, ForeignKey, Text, Enum, DateTime, Integer
from enum import Enum as PyEnum

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User, ApiKey
    from app.modules.documents.models import Document
    from app.modules.assignments.models import Assignment


class OrganizationRole(str, PyEnum):
    OWNER = "owner"
    ADMIN = "admin"
    FACULTY = "faculty"
    RESEARCHER = "researcher"
    STUDENT = "student"
    REVIEWER = "reviewer"
    AUDITOR = "auditor"


class SubscriptionTier(str, PyEnum):
    FREE = "free"
    STUDENT = "student"
    PRO = "pro"
    FACULTY = "faculty"
    INSTITUTION = "institution"
    ENTERPRISE = "enterprise"


class Organization(Base):
    __tablename__ = "organizations"

    erasure_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier), default=SubscriptionTier.FREE, nullable=False
    )
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    usage_documents_month: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    usage_storage_mb: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_api_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    memberships: Mapped[List["Membership"]] = relationship(
        "Membership", back_populates="organization", lazy="selectin"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="organization", lazy="selectin"
    )
    assignments: Mapped[List["Assignment"]] = relationship(
        "Assignment", back_populates="organization", lazy="selectin"
    )
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey", back_populates="organization", lazy="selectin"
    )


class Membership(Base):
    __tablename__ = "memberships"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[OrganizationRole] = mapped_column(
        Enum(OrganizationRole), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    user: Mapped["User"] = relationship(
        "User", back_populates="memberships", foreign_keys=[user_id]
    )
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="memberships"
    )
