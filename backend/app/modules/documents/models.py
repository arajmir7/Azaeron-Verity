"""AZAERON document models."""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    CheckConstraint,
    String,
    Boolean,
    ForeignKey,
    Text,
    Integer,
    DateTime,
    Enum,
    UniqueConstraint,
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.organizations.models import Organization
    from app.modules.auth.models import User
    from app.modules.jobs.models import Job
    from app.modules.similarity.models import SimilarityMatch
    from app.modules.citations.models import Citation
    from app.modules.detection.models import DetectionResult
    from app.modules.authorship.models import AuthorshipSignal
    from app.modules.provenance.models import ProvenanceEvent
    from app.modules.evidence.models import EvidenceNode
    from app.modules.evidence.report_models import IntegrityReport
    from app.modules.assignments.models import Submission


class DocumentStatus(str, PyEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class DocumentVersionLifecycle(str, PyEnum):
    DRAFT = "DRAFT"
    REVISION = "REVISION"
    FINAL = "FINAL"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="ck_documents_file_size_positive"),
        CheckConstraint(
            "length(sha256_fingerprint) = 64", name="ck_documents_sha256_length"
        ),
        UniqueConstraint("storage_path", name="uq_documents_storage_path"),
    )

    erasure_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assignment_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submission_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    sha256_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="documents"
    )
    owner: Mapped["User"] = relationship("User", back_populates="documents")
    versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="document", lazy="selectin"
    )
    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="document", lazy="selectin"
    )
    similarity_matches: Mapped[List["SimilarityMatch"]] = relationship(
        "SimilarityMatch",
        back_populates="document",
        foreign_keys="SimilarityMatch.document_id",
        lazy="selectin",
    )
    citations: Mapped[List["Citation"]] = relationship(
        "Citation", back_populates="document", lazy="selectin"
    )
    detection_results: Mapped[List["DetectionResult"]] = relationship(
        "DetectionResult", back_populates="document", lazy="selectin"
    )
    authorship_signals: Mapped[List["AuthorshipSignal"]] = relationship(
        "AuthorshipSignal", back_populates="document", lazy="selectin"
    )
    provenance_events: Mapped[List["ProvenanceEvent"]] = relationship(
        "ProvenanceEvent", back_populates="document", lazy="selectin"
    )
    evidence_nodes: Mapped[List["EvidenceNode"]] = relationship(
        "EvidenceNode", back_populates="document", lazy="selectin"
    )
    report: Mapped[Optional["IntegrityReport"]] = relationship(
        "IntegrityReport", back_populates="document", uselist=False
    )
    submissions: Mapped[List["Submission"]] = relationship(
        "Submission", back_populates="document", foreign_keys="Submission.document_id"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number > 0", name="ck_document_versions_number_positive"
        ),
        UniqueConstraint(
            "document_id", "version_number", name="uq_document_versions_document_number"
        ),
        UniqueConstraint(
            "document_id", "operation_id", name="uq_document_versions_operation"
        ),
        CheckConstraint(
            "(operation_id IS NULL AND operation_fingerprint IS NULL) OR (operation_id IS NOT NULL AND operation_fingerprint IS NOT NULL AND length(operation_fingerprint) = 64)",
            name="ck_document_versions_operation",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    operation_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    uploaded_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sha256_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    previous_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lifecycle_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentVersionLifecycle.DRAFT.value
    )
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edit_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="versions")
