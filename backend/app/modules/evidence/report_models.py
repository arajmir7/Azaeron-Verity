"""AZAERON integrity report models."""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Integer, Float, JSON, Enum
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class ReportStatus(str, PyEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class IntegrityReport(AnalysisLineageMixin, Base):
    __tablename__ = "integrity_reports"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), default=ReportStatus.PENDING, nullable=False
    )
    originality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    originality_confidence: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    ai_signal_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_signal_confidence: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    ai_signal_verdict: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    authorship_consistency_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    authorship_confidence: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    citation_integrity_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    source_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provenance_strength: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    writing_quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority_issues: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    report_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship("Document", back_populates="report")
