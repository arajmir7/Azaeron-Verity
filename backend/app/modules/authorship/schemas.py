"""API contracts for baseline-relative authorship consistency."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AuthorshipProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    baseline_document_ids: list[str] = Field(..., min_length=1, max_length=100)


class AuthorshipProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: Optional[str]
    baseline_document_ids: Optional[list]
    baseline_quality: Optional[str] = None
    baseline_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuthorshipSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    profile_id: Optional[str]
    verdict: str
    baseline_quality: Optional[str]
    consistency_score: Optional[float]
    confidence: Optional[float]
    confidence_type: Optional[str]
    stylistic_deviation: Optional[dict[str, Any]]
    ai_writing_signal: Optional[dict[str, Any]]
    feature_data: Optional[dict[str, Any]]
    evidence_id: Optional[str]
    explanation: Optional[str]
    limitations: Optional[str]
    pipeline_version: str
    model_version: Optional[str]
    document_version_id: str
    created_at: datetime
