"""Versioned model, dataset, and analysis-run metadata.

These records deliberately describe capability maturity and provenance. They
do not turn an uncalibrated signal into a diagnostic or authorship verdict.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LifecycleStatus(str, PyEnum):
    EXPERIMENTAL = "EXPERIMENTAL"
    CANDIDATE = "CANDIDATE"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


class DatasetStatus(str, PyEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    FROZEN = "FROZEN"
    RETIRED = "RETIRED"


class AnalysisRunStatus(str, PyEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    ABSTAINED = "ABSTAINED"
    FAILED = "FAILED"


class AnalysisLineageMixin:
    """Required provenance contract shared by every analysis output."""

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)


class ModelRegistry(Base):
    __tablename__ = "model_registry"
    __table_args__ = (
        UniqueConstraint(
            "model_id", "model_version", name="uq_model_registry_identity"
        ),
    )

    model_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=LifecycleStatus.EXPERIMENTAL
    )
    metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    limitations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    provenance: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationDataset(Base):
    __tablename__ = "evaluation_datasets"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "version", name="uq_evaluation_dataset_identity"
        ),
    )

    dataset_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DatasetStatus.DRAFT
    )
    schema_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    manifest_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leakage_checks: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    provenance_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    frozen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EvaluationExample(Base):
    __tablename__ = "evaluation_examples"
    __table_args__ = (
        UniqueConstraint("dataset_id", "example_key", name="uq_evaluation_example_key"),
    )

    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    example_key: Mapped[str] = mapped_column(String(180), nullable=False)
    split: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author_key_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    domain: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    generation_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    editing_intensity: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    document_key_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    source_document_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    document_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    writing_proficiency: Mapped[Optional[str]] = mapped_column(
        String(80), nullable=True
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    status: Mapped[AnalysisRunStatus] = mapped_column(
        String(20), nullable=False, default=AnalysisRunStatus.STARTED
    )
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
