"""AZAERON document provenance models."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Enum
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class ProvenanceEventType(str, PyEnum):
    CREATED = "created"
    UPLOADED = "uploaded"
    EDITED = "edited"
    AI_ASSISTED = "ai_assisted"
    CITATION_ADDED = "citation_added"
    REVISION = "revision"
    EXPORTED = "exported"
    SIGNED = "signed"
    ANALYSIS_RUN = "analysis_run"


class ProvenanceEvent(AnalysisLineageMixin, Base):
    __tablename__ = "provenance_events"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[ProvenanceEventType] = mapped_column(
        Enum(ProvenanceEventType), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    analysis_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sha256_before: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sha256_after: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="provenance_events"
    )


class ProvenanceReport(AnalysisLineageMixin, Base):
    __tablename__ = "provenance_reports"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    signed_by_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    report_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)


class ProvenanceExport(AnalysisLineageMixin, Base):
    """Immutable, tenant-authorized export snapshot of provenance history."""

    __tablename__ = "provenance_exports"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exported_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    export_format: Mapped[str] = mapped_column(
        String(20), nullable=False, default="json"
    )
    export_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
