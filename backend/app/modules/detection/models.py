"""AZAERON AI detection models."""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    CheckConstraint,
    String,
    ForeignKey,
    Text,
    Integer,
    Float,
    JSON,
    Boolean,
    Enum,
    UniqueConstraint,
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class DetectionVerdict(str, PyEnum):
    HUMAN = "human"
    AI_GENERATED = "ai_generated"
    # Kept for backward compatibility with historical rows created before
    # the six-state intelligence contract was introduced.
    AI = "ai"
    MIXED = "mixed"
    AI_ASSISTED = "ai_assisted"
    UNCERTAIN = "uncertain"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class DetectionResult(AnalysisLineageMixin, Base):
    __tablename__ = "detection_results"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_detection_results_confidence_range",
        ),
        CheckConstraint(
            "human_probability >= 0 AND human_probability <= 1",
            name="ck_detection_results_human_probability_range",
        ),
        CheckConstraint(
            "ai_probability >= 0 AND ai_probability <= 1",
            name="ck_detection_results_ai_probability_range",
        ),
        CheckConstraint(
            "mixed_probability >= 0 AND mixed_probability <= 1",
            name="ck_detection_results_mixed_probability_range",
        ),
        CheckConstraint(
            "uncertain_probability >= 0 AND uncertain_probability <= 1",
            name="ck_detection_results_uncertain_probability_range",
        ),
        UniqueConstraint(
            "document_id", "job_id", name="uq_detection_results_document_job"
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analysis_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    overall_verdict: Mapped[DetectionVerdict] = mapped_column(
        Enum(DetectionVerdict), nullable=False
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calibration_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    human_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mixed_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    uncertain_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    release_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="EXPERIMENTAL"
    )
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    feature_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    feature_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="feature-extraction-v1"
    )
    calibrator_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    uncertainty_method: Mapped[Optional[str]] = mapped_column(
        String(120), nullable=True
    )
    confidence_reliability: Mapped[str] = mapped_column(
        String(40), nullable=False, default="UNAVAILABLE"
    )
    inference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    inference_metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    evidence_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    abstention_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="detection_results"
    )
    segments: Mapped[list["DetectionSegment"]] = relationship(
        "DetectionSegment",
        back_populates="detection_result",
        lazy="selectin",
        order_by="(DetectionSegment.segment_index, DetectionSegment.segment_type, DetectionSegment.id)",
    )


class DetectionSegment(Base):
    __tablename__ = "detection_segments"
    __table_args__ = (
        CheckConstraint(
            "span_start >= 0 AND span_end >= span_start",
            name="ck_detection_segments_span",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_detection_segments_confidence_range",
        ),
        UniqueConstraint(
            "detection_result_id",
            "segment_type",
            "segment_index",
            name="uq_detection_segments_result_segment",
        ),
    )

    detection_result_id: Mapped[str] = mapped_column(
        ForeignKey("detection_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    segment_type: Mapped[str] = mapped_column(String(20), nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[DetectionVerdict] = mapped_column(
        Enum(DetectionVerdict), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    perplexity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    burstiness: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    feature_scores: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    detection_result: Mapped["DetectionResult"] = relationship(
        "DetectionResult", back_populates="segments"
    )
