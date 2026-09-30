"""Tenant and actor scoped agent records; no model output is executable."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgentScope:
    __mapper_args__ = {"eager_defaults": True}
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )


def parent_scope(table: str, column: str):
    return ForeignKeyConstraint(
        ["organization_id", "user_id", column],
        [f"{table}.organization_id", f"{table}.user_id", f"{table}.id"],
        ondelete="CASCADE",
    )


class Conversation(AgentScope, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "id"),)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")


class VoiceProfile(AgentScope, Base):
    __tablename__ = "ai_voice_profiles"
    name: Mapped[str] = mapped_column(String(100))
    samples: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    style: Mapped[dict[str, float]] = mapped_column(JSON)
    policy_revision: Mapped[str] = mapped_column(String(80))


class Message(AgentScope, Base):
    __tablename__ = "ai_messages"
    __table_args__ = (
        parent_scope("ai_conversations", "conversation_id"),
        UniqueConstraint("organization_id", "user_id", "id"),
        UniqueConstraint("conversation_id", "sequence"),
        CheckConstraint(
            "role IN ('user','assistant','tool')", name="ck_ai_message_role"
        ),
    )
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    # Immutable prompts are appended, never silently edited or overwritten.
    replaces_message_id: Mapped[str | None] = mapped_column(String(36))


class AgentRun(AgentScope, Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        parent_scope("ai_conversations", "conversation_id"),
        parent_scope("ai_messages", "message_id"),
        UniqueConstraint("organization_id", "user_id", "id"),
        UniqueConstraint("organization_id", "user_id", "operation_id"),
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED','UNAVAILABLE','CANCELLED')",
            name="ck_ai_run_status",
        ),
    )
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    message_id: Mapped[str] = mapped_column(String(36))
    operation_id: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    error_code: Mapped[str | None] = mapped_column(String(80))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    model_evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_operation_id: Mapped[str] = mapped_column(String(36))
    session_family: Mapped[str] = mapped_column(String(36))
    session_version: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ToolCall(AgentScope, Base):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (
        parent_scope("ai_runs", "run_id"),
        UniqueConstraint("organization_id", "user_id", "id"),
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(48))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))


class ToolResult(AgentScope, Base):
    __tablename__ = "ai_tool_results"
    __table_args__ = (
        parent_scope("ai_tool_calls", "tool_call_id"),
        UniqueConstraint("tool_call_id"),
    )
    tool_call_id: Mapped[str] = mapped_column(String(36))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)


class DocumentAttachment(AgentScope, Base):
    __tablename__ = "ai_document_attachments"
    __table_args__ = (
        parent_scope("ai_conversations", "conversation_id"),
        UniqueConstraint("conversation_id", "document_version_id"),
    )
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    input_sha256: Mapped[str] = mapped_column(String(64))


class AgentEvent(AgentScope, Base):
    __tablename__ = "ai_events"
    __table_args__ = (
        parent_scope("ai_runs", "run_id"),
        UniqueConstraint("run_id", "sequence"),
    )
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ActionReceipt(AgentScope, Base):
    __tablename__ = "ai_action_receipts"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "operation_id"),
        CheckConstraint(
            "decision IN ('PENDING','ACCEPTED','REJECTED')",
            name="ck_ai_receipt_decision",
        ),
        CheckConstraint(
            "(decision='ACCEPTED' AND result_version_id IS NOT NULL AND result_sha256 IS NOT NULL) OR (decision<>'ACCEPTED' AND result_version_id IS NULL AND result_sha256 IS NULL)",
            name="ck_ai_receipt_result",
        ),
    )
    # Evidence survives conversation deletion; privacy erasure removes derivatives.
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    operation_id: Mapped[str] = mapped_column(String(36))
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    input_sha256: Mapped[str] = mapped_column(String(64))
    candidate_sha256: Mapped[str] = mapped_column(String(64))
    candidate_text: Mapped[str] = mapped_column(Text)
    candidate_diff: Mapped[str] = mapped_column(Text)
    model_evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    policy_revision: Mapped[str] = mapped_column(String(80))
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    protected_spans: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    verification: Mapped[dict[str, Any]] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(16), default="PENDING")
    result_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE")
    )
    result_sha256: Mapped[str | None] = mapped_column(String(64))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    similarity_before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    similarity_after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
