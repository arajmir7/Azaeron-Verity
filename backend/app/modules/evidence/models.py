"""AZAERON evidence graph models."""

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
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class EvidenceNodeType(str, PyEnum):
    DOCUMENT = "document"
    CLAIM = "claim"
    CITATION = "citation"
    SOURCE = "source"
    SIMILARITY = "similarity"
    AUTHORSHIP = "authorship"
    PROVENANCE = "provenance"
    DETECTION = "detection"
    REVISION = "revision"


class CanonicalEvidenceNodeType(str, PyEnum):
    """Stable graph vocabulary exposed to evidence consumers."""

    DOCUMENT = "DOCUMENT"
    DOCUMENT_VERSION = "DOCUMENT_VERSION"
    CLAIM = "CLAIM"
    CITATION = "CITATION"
    SOURCE = "SOURCE"
    SIMILARITY_MATCH = "SIMILARITY_MATCH"
    AI_SIGNAL = "AI_SIGNAL"
    AUTHORSHIP_SIGNAL = "AUTHORSHIP_SIGNAL"
    PROVENANCE_EVENT = "PROVENANCE_EVENT"
    FINDING = "FINDING"
    REPORT = "REPORT"


class EvidenceEdgeType(str, PyEnum):
    CONTAINS = "CONTAINS"
    VERSION_OF = "VERSION_OF"
    CITES = "CITES"
    SUPPORTED_BY = "SUPPORTED_BY"
    SIMILAR_TO = "SIMILAR_TO"
    HAS_SIGNAL = "HAS_SIGNAL"
    DERIVED_FROM = "DERIVED_FROM"
    GENERATED_FINDING = "GENERATED_FINDING"


class EvidenceNode(AnalysisLineageMixin, Base):
    __tablename__ = "evidence_nodes"
    __table_args__ = (
        UniqueConstraint("node_id", name="uq_evidence_nodes_node_id"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_evidence_nodes_confidence_range",
        ),
        CheckConstraint(
            "span_start IS NULL OR (span_start >= 0 AND span_end >= span_start)",
            name="ck_evidence_nodes_span",
        ),
        CheckConstraint(
            "length(node_id) > 0", name="ck_evidence_nodes_node_id_nonempty"
        ),
        CheckConstraint(
            "length(entity_id) > 0", name="ck_evidence_nodes_entity_id_nonempty"
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="evidence"
    )
    source_id: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    model_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    node_type: Mapped[EvidenceNodeType] = mapped_column(
        Enum(EvidenceNodeType), nullable=False
    )
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    canonical_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=CanonicalEvidenceNodeType.FINDING.value,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(
        String(60), nullable=False, default="evidence"
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    span_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    span_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    span_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="evidence_nodes"
    )


class EvidenceEdge(Base):
    __tablename__ = "evidence_edges"

    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('CONTAINS', 'VERSION_OF', 'CITES', 'SUPPORTED_BY', 'SIMILAR_TO', 'HAS_SIGNAL', 'DERIVED_FROM', 'GENERATED_FINDING')",
            name="ck_evidence_edges_type",
        ),
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

    source_node_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        ForeignKey("evidence_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
