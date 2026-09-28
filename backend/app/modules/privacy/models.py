"""Minimal erasure tombstones; no customer text or email is retained here."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ErasureRequest(Base):
    __tablename__ = "privacy_erasures"
    __table_args__ = (UniqueConstraint("scope", "target_id", name="uq_erasure_target"),)

    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(36), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(36))
    receipt_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    organization_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    object_keys: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prefixes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    not_before: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(40))
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON)
