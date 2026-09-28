"""Durable quota totals and tenant-scoped operation receipts."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UsageBucket(Base):
    __tablename__ = "usage_buckets"
    __table_args__ = (
        UniqueConstraint("organization_id", "period", "task", name="uq_usage_bucket"),
        CheckConstraint(
            "reserved >= 0 AND committed >= 0", name="ck_usage_bucket_counts"
        ),
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    period: Mapped[str] = mapped_column(String(7))
    task: Mapped[str] = mapped_column(String(40))
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    committed: Mapped[int] = mapped_column(Integer, default=0)


class UsageOperation(Base):
    __tablename__ = "usage_operations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "task", "operation_id", name="uq_usage_operation"
        ),
        CheckConstraint(
            "status IN ('RESERVED','COMMITTED','RELEASED')", name="ck_usage_status"
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0", name="ck_usage_input_tokens"
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0", name="ck_usage_output_tokens"
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_usage_duration"
        ),
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    api_key_id: Mapped[str | None] = mapped_column(String(36))
    document_id: Mapped[str | None] = mapped_column(String(36), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    request_id: Mapped[str | None] = mapped_column(String(128))
    task: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(7))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(15), default="RESERVED")
    outcome: Mapped[str | None] = mapped_column(String(40))
    chargeable: Mapped[bool] = mapped_column(Boolean, default=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    model_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_ciphertext: Mapped[str | None] = mapped_column(Text)
    response_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    response_status: Mapped[int | None] = mapped_column(Integer)
