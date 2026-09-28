"""AZAERON similarity engine models."""

from datetime import datetime
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
    Enum,
    UniqueConstraint,
    DateTime,
    Index,
)
from enum import Enum as PyEnum
from pgvector.sqlalchemy import Vector

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class SimilarityType(str, PyEnum):
    EXACT = "exact"
    NEAR_DUPLICATE = "near_duplicate"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    PROBABLE_PARAPHRASE = "probable_paraphrase"
    # Retained so historical rows remain readable. New pipelines must use
    # PROBABLE_PARAPHRASE only after a validated semantic provider is active.
    PARAPHRASE = "paraphrase"


class SimilarityMatch(AnalysisLineageMixin, Base):
    __tablename__ = "similarity_matches"
    __table_args__ = (
        CheckConstraint(
            "document_span_start >= 0 AND document_span_end >= document_span_start",
            name="ck_similarity_matches_document_span",
        ),
        CheckConstraint(
            "similarity_score >= 0 AND similarity_score <= 1",
            name="ck_similarity_matches_score_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_similarity_matches_confidence_range",
        ),
        CheckConstraint(
            "retrieval_score IS NULL OR (retrieval_score >= 0 AND retrieval_score <= 1)",
            name="ck_similarity_matches_retrieval_score",
        ),
        CheckConstraint(
            "lexical_score IS NULL OR (lexical_score >= 0 AND lexical_score <= 1)",
            name="ck_similarity_matches_lexical_score",
        ),
        CheckConstraint(
            "ngram_score IS NULL OR (ngram_score >= 0 AND ngram_score <= 1)",
            name="ck_similarity_matches_ngram_score",
        ),
        CheckConstraint(
            "structural_score IS NULL OR (structural_score >= 0 AND structural_score <= 1)",
            name="ck_similarity_matches_structural_score",
        ),
        CheckConstraint(
            "verification_score IS NULL OR (verification_score >= 0 AND verification_score <= 1)",
            name="ck_similarity_matches_verification_score",
        ),
    )

    # document_id remains the historical target-document column. The explicit
    # target_document_id makes the source/target contract unambiguous for new
    # consumers and is backfilled by the retrieval-engine migration.
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_document_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    source_document_version_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    analysis_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("similarity_analyses.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("evidence_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_source_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )
    match_type: Mapped[SimilarityType] = mapped_column(
        Enum(SimilarityType), nullable=False
    )
    document_span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    document_span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    source_span_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_span_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lexical_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ngram_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    semantic_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    structural_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verification_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_reliability: Mapped[str] = mapped_column(
        String(40), nullable=False, default="EXPERIMENTAL"
    )
    candidate_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retrieval_methods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    verification_methods: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    matched_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    group_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, index=True
    )

    document: Mapped["Document"] = relationship(
        "Document", foreign_keys=[document_id], back_populates="similarity_matches"
    )


class DocumentChunk(AnalysisLineageMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(
            "chunk_index >= 0", name="ck_document_chunks_index_nonnegative"
        ),
        CheckConstraint(
            "start_char >= 0 AND end_char >= start_char", name="ck_document_chunks_span"
        ),
        UniqueConstraint(
            "document_id",
            "document_version_id",
            "index_version",
            "chunk_index",
            name="uq_document_chunks_version_index",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    normalized_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    index_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="inverted-terms-v1"
    )
    index_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE"
    )
    indexed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    structure_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    embedding_vector: Mapped[Optional[list]] = mapped_column(
        Vector(384).with_variant(JSON(), "sqlite"), nullable=True
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)


class SimilarityIndexEntry(AnalysisLineageMixin, Base):
    """Tenant-local inverted index entry for incremental candidate retrieval."""

    __tablename__ = "similarity_index_entries"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "index_version",
            "term_type",
            "term",
            name="uq_similarity_index_chunk_term",
        ),
        Index(
            "ix_similarity_index_lookup",
            "organization_id",
            "index_version",
            "term_type",
            "term",
        ),
        CheckConstraint(
            "term_type IN ('token', 'ngram', 'fingerprint')",
            name="ck_similarity_index_term_type",
        ),
        CheckConstraint(
            "term_frequency > 0", name="ck_similarity_index_term_frequency"
        ),
    )

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    term_type: Mapped[str] = mapped_column(String(20), nullable=False)
    term_frequency: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    positions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    index_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)


class SimilarityAnalysis(AnalysisLineageMixin, Base):
    """Frozen retrieval snapshot; view exclusions never mutate its evidence."""

    __tablename__ = "similarity_analyses"
    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "pipeline_version",
            "run_key",
            name="uq_similarity_analysis_version_pipeline",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_state: Mapped[str] = mapped_column(String(30), nullable=False)
    corpus_version_count: Mapped[int] = mapped_column(Integer, nullable=False)
    index_version: Mapped[str] = mapped_column(String(80), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    truncated: Mapped[bool] = mapped_column(default=False, nullable=False)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    analysis_run_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    run_key: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    snapshot_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    sealed: Mapped[bool] = mapped_column(default=False, nullable=False)
