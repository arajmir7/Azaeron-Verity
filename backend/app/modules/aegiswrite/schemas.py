"""AZAERON WRITE request and response contracts."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.aegiswrite.models import EditType


class ProtectedTextRequest(BaseModel):
    operation_id: UUID | None = None
    text: str = Field(min_length=1, max_length=250_000)
    locked_spans: list[tuple[int, int]] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def validate_locked_spans(self):
        if any(
            not 0 <= start < end <= len(self.text) for start, end in self.locked_spans
        ):
            raise ValueError("Locked span is outside the submitted text")
        return self


class AegisEditRequest(ProtectedTextRequest):
    document_id: str
    document_version_id: str | None = None
    text: str = Field(min_length=1, max_length=250_000)
    span_start: int = Field(default=0, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    edit_types: list[EditType] = Field(
        default_factory=lambda: [
            EditType.GRAMMAR,
            EditType.CLARITY,
            EditType.CONCISION,
            EditType.TONE,
            EditType.STRUCTURE,
            EditType.COHERENCE,
        ],
        min_length=1,
    )
    preserve_voice: bool = True

    model_config = ConfigDict(extra="forbid")


class AegisEditResponse(BaseModel):
    id: str
    edit_type: EditType
    dimension: str
    original: str
    revision: str
    change_reason: str
    span_start: int
    span_end: int
    applied: bool
    ai_generated: bool
    document_id: str
    document_version_id: str
    preserve_voice: bool
    engine_version: str
    created_at: datetime


class AegisEditApplyRequest(BaseModel):
    edit_id: str
    apply: bool

    model_config = ConfigDict(extra="forbid")


class AegisRefineRequest(ProtectedTextRequest):
    document_id: str
    document_version_id: str | None = None
    text: str = Field(min_length=1, max_length=250_000)
    edit_types: list[EditType] = Field(
        default_factory=lambda: [
            EditType.GRAMMAR,
            EditType.CLARITY,
            EditType.CONCISION,
            EditType.TONE,
            EditType.STRUCTURE,
            EditType.COHERENCE,
        ],
        min_length=1,
    )
    preserve_voice: bool = True

    model_config = ConfigDict(extra="forbid")


class AegisChangeResponse(BaseModel):
    id: str
    dimension: str
    original: str
    revision: str
    change_reason: str
    span_start: int
    span_end: int
    applied: bool


class AegisRefineResponse(BaseModel):
    document_id: str
    document_version_id: str
    original_text: str
    revised_text: str
    changes: list[AegisChangeResponse]
    disclaimer: str


class AegisHistoryResponse(BaseModel):
    document_id: str
    document_version_id: str | None
    items: list[AegisEditResponse]
