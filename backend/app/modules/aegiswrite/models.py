"""AZAERON AegisWrite editing assistant models."""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    String,
    ForeignKey,
    Text,
    DateTime,
    Integer,
    JSON,
    Boolean,
    Enum,
    CheckConstraint,
)
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.documents.models import Document, DocumentVersion


class EditType(str, PyEnum):
    GRAMMAR = "grammar"
    CLARITY = "clarity"
    CONCISION = "concision"
    TONE = "tone"
    STRUCTURE = "structure"
    CITATION = "citation"
    VOCABULARY = "vocabulary"
    COHERENCE = "coherence"


class AegisEdit(Base):
    __tablename__ = "aegis_edits"
    __table_args__ = (
        CheckConstraint(
            "span_start >= 0 AND span_end >= span_start",
            name="ck_aegis_edits_span_valid",
        ),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    parent_edit_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("aegis_edits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    edit_type: Mapped[EditType] = mapped_column(Enum(EditType), nullable=False)
    dimension: Mapped[str] = mapped_column(
        String(50), nullable=False, default="clarity"
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    span_start: Mapped[int] = mapped_column(Integer, nullable=False)
    span_end: Mapped[int] = mapped_column(Integer, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preserve_voice: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    engine_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="editorial-rules-v1"
    )
    source_text_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    document: Mapped["Document"] = relationship("Document")
    document_version: Mapped["DocumentVersion"] = relationship("DocumentVersion")
    parent_edit: Mapped[Optional["AegisEdit"]] = relationship(
        "AegisEdit", remote_side="AegisEdit.id"
    )
