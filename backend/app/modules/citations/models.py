"""AZAERON source-aware citation intelligence models."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    ForeignKey,
    Text,
    Integer,
    Float,
    JSON,
    Boolean,
    Enum,
    CheckConstraint,
    DateTime,
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class CitationStatus(str, PyEnum):
    VALID = "valid"
    BROKEN = "broken"
    SUSPICIOUS = "suspicious"
    UNVERIFIED = "unverified"
    FABRICATED = "fabricated"


class SupportStatus(str, PyEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    UNVERIFIABLE = "UNVERIFIABLE"


class Citation(AnalysisLineageMixin, Base):
    __tablename__ = "citations"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("claims.id", ondelete="SET NULL"), nullable=True
    )
    reference_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citation_references.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citation_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("evidence_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    citation_key: Mapped[Optional[str]] = mapped_column(
        String(180), nullable=True, index=True
    )
    citation_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    authors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[CitationStatus] = mapped_column(
        Enum(CitationStatus), default=CitationStatus.UNVERIFIED, nullable=False
    )
    support_status: Mapped[SupportStatus] = mapped_column(
        Enum(SupportStatus), nullable=False, default=SupportStatus.UNVERIFIABLE
    )
    retrieval_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)

    document: Mapped["Document"] = relationship("Document", back_populates="citations")
    claim: Mapped[Optional["Claim"]] = relationship("Claim", back_populates="citations")


class Claim(AnalysisLineageMixin, Base):
    __tablename__ = "claims"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    has_citation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    citation_supports_claim: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True
    )
    support_status: Mapped[SupportStatus] = mapped_column(
        Enum(SupportStatus), nullable=False, default=SupportStatus.UNVERIFIABLE
    )
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("evidence_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    citations: Mapped[list["Citation"]] = relationship(
        "Citation", back_populates="claim"
    )


class Reference(AnalysisLineageMixin, Base):
    """A bibliography/reference entry as it appeared in the document."""

    __tablename__ = "citation_references"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citation_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reference_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class Source(AnalysisLineageMixin, Base):
    """A preserved source identity and retrieved metadata, never invented."""

    __tablename__ = "citation_sources"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    source_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieval_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieval_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="NOT_ATTEMPTED"
    )
    abstract_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retrieved_payload_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)


class CitationFinding(AnalysisLineageMixin, Base):
    """Auditable finding linking claim, citation/reference/source when present."""

    __tablename__ = "citation_findings"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_citation_findings_confidence",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), nullable=True, index=True
    )
    citation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reference_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citation_references.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("citation_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("evidence_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    finding_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    support_status: Mapped[SupportStatus] = mapped_column(
        Enum(SupportStatus), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
