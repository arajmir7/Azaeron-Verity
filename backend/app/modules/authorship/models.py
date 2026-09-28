"""AZAERON authorship intelligence models."""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Integer, Float, JSON, Enum
from enum import Enum as PyEnum

from app.core.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.documents.models import Document
from app.modules.governance.models import AnalysisLineageMixin


class AuthorshipProfile(Base):
    __tablename__ = "authorship_profiles"

    organization_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    baseline_document_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    stylometric_features: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    vocabulary_distribution: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    punctuation_patterns: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    syntax_patterns: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="authorship_profiles")


class AuthorshipSignal(AnalysisLineageMixin, Base):
    __tablename__ = "authorship_signals"

    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("authorship_profiles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    consistency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verdict: Mapped[str] = mapped_column(
        String(40), nullable=False, default="INSUFFICIENT_DATA"
    )
    baseline_quality: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    feature_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    stylistic_deviation: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    ai_writing_signal: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )
    confidence_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    evidence_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("evidence_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stylistic_drift_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unusual_segments: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    limitations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(
        "Document", back_populates="authorship_signals"
    )
