"""AZAERON audit logging models."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, DateTime, Enum, JSON
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.auth.models import User


class AuditAction(str, PyEnum):
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    USER_REGISTERED = "user_registered"
    USER_UPDATED = "user_updated"
    ORG_CREATED = "org_created"
    ORG_UPDATED = "org_updated"
    ORG_MEMBER_INVITED = "org_member_invited"
    ORG_MEMBER_JOINED = "org_member_joined"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_PROCESSED = "document_processed"
    JOB_CREATED = "job_created"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    SETTINGS_CHANGED = "settings_changed"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    EXPORT_REQUESTED = "export_requested"
    DATA_DELETED = "data_deleted"
    ASSIGNMENT_CREATED = "assignment_created"
    SUBMISSION_CREATED = "submission_created"
    GRADE_ASSIGNED = "grade_assigned"
    REPORT_VIEWED = "report_viewed"
    DETECTION_RUN = "detection_run"
    WRITING_SUGGESTIONS = "writing_suggestions"
    WRITING_REFINEMENT = "writing_refinement"
    WRITING_EDIT_APPLIED = "writing_edit_applied"
    WRITING_EDIT_REJECTED = "writing_edit_rejected"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction), nullable=False, index=True
    )
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audit_logs")
