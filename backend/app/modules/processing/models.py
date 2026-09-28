"""AZAERON document processing models."""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, ForeignKey, Text, Integer, JSON, UniqueConstraint

from app.core.database import Base
from app.modules.governance.models import AnalysisLineageMixin


class ProcessedDocument(AnalysisLineageMixin, Base):
    __tablename__ = "processed_documents"
    __table_args__ = (
        UniqueConstraint("document_version_id", name="uq_processed_documents_version"),
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parser_version: Mapped[str] = mapped_column(
        String(80), nullable=False, default="legacy-unstructured"
    )
    normalized_content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    structure_fingerprint: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    structure_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cleaned_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    paragraphs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sentences: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    sections: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sentence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paragraph_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_sentence_length: Mapped[Optional[float]] = mapped_column(nullable=True)
    avg_word_length: Mapped[Optional[float]] = mapped_column(nullable=True)
    readability_flesch: Mapped[Optional[float]] = mapped_column(nullable=True)
    readability_flesch_kincaid: Mapped[Optional[float]] = mapped_column(nullable=True)
    lexical_diversity: Mapped[Optional[float]] = mapped_column(nullable=True)
