"""AZAERON authentication models."""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    Boolean,
    ForeignKey,
    Text,
    DateTime,
    Integer,
    CheckConstraint,
)

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.organizations.models import Membership, Organization
    from app.modules.documents.models import Document
    from app.modules.audit.models import AuditLog
    from app.modules.authorship.models import AuthorshipProfile


class User(Base):
    __tablename__ = "users"
    __allow_unmapped__ = True
    __table_args__ = (
        CheckConstraint("session_version >= 0", name="ck_users_session_version"),
    )

    erasure_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    session_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mfa_pending_secret: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    mfa_pending_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mfa_last_counter: Mapped[int] = mapped_column(
        Integer, default=-1, server_default="-1", nullable=False
    )
    mfa_recovery_hashes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Product persona only: authorization remains on Membership.role.
    product_role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    personal_organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    last_active_organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )

    memberships: Mapped[List["Membership"]] = relationship(
        "Membership",
        back_populates="user",
        foreign_keys="Membership.user_id",
        lazy="selectin",
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", lazy="selectin"
    )
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="owner", lazy="selectin"
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog", back_populates="user", lazy="selectin"
    )
    authorship_profiles: Mapped[List["AuthorshipProfile"]] = relationship(
        "AuthorshipProfile", back_populates="user", lazy="selectin"
    )
    api_keys: Mapped[List["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", lazy="selectin"
    )

    # Request-scoped attributes; never persist these onto a user row.
    current_organization_id: Optional[str] = None
    current_role: Optional[str] = None
    current_api_key_id: Optional[str] = None
    current_api_scopes: tuple[str, ...] = ()
    current_session_family: Optional[str] = None

    @property
    def home_path(self) -> str:
        if self.product_role == "researcher":
            return "/citations"
        if self.product_role in {"teacher", "professor", "reviewer", "institution"}:
            return "/documents"
        return "/check"

    @property
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jti: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    hashed_token: Mapped[str] = mapped_column(String(255), nullable=False)
    token_family: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_jti: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


class ApiKey(Base):
    __tablename__ = "api_keys"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    hashed_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credential_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_from_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="api_keys")
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="api_keys"
    )
