"""AZAERON assignment and submission models."""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    ForeignKey,
    Text,
    Integer,
    Float,
    DateTime,
    JSON,
    Boolean,
    Enum,
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.organizations.models import Organization
    from app.modules.documents.models import Document


class AssignmentStatus(str, PyEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    ARCHIVED = "archived"


class Assignment(Base):
    __tablename__ = "assignments"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus), default=AssignmentStatus.DRAFT, nullable=False
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    max_file_size_mb: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    allowed_extensions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rubric: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="assignments"
    )
    submissions: Mapped[List["Submission"]] = relationship(
        "Submission", back_populates="assignment", lazy="selectin"
    )


class SubmissionStatus(str, PyEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    REVIEWED = "reviewed"
    GRADED = "graded"
    RETURNED = "returned"


class Submission(Base):
    __tablename__ = "submissions"

    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.DRAFT, nullable=False
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    late_submission: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    grade: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    graded_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    graded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assignment: Mapped["Assignment"] = relationship(
        "Assignment", back_populates="submissions"
    )
    document: Mapped[Optional["Document"]] = relationship(
        "Document", foreign_keys=[document_id], back_populates="submissions"
    )
