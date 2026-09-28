"""Auditable citation intelligence API schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.modules.citations.models import CitationStatus, SupportStatus


class CitationLineageResponse(BaseModel):
    organization_id: str
    document_id: str
    document_version_id: str


class SourceResponse(CitationLineageResponse):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: Optional[str]
    authors: Optional[list[str]]
    publisher: Optional[str]
    doi: Optional[str]
    url: Optional[str]
    retrieval_timestamp: Optional[datetime]
    retrieval_status: str
    retrieved_payload_hash: Optional[str]


class ReferenceResponse(CitationLineageResponse):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: Optional[str]
    reference_key: str
    raw_text: str
    authors: Optional[list[str]]
    title: Optional[str]
    year: Optional[int]
    doi: Optional[str]
    url: Optional[str]
    publisher: Optional[str]
    metadata_json: Optional[dict[str, Any]]


class CitationResponse(CitationLineageResponse):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: Optional[str]
    reference_id: Optional[str]
    source_id: Optional[str]
    evidence_id: Optional[str]
    raw_text: str
    citation_key: Optional[str]
    status: CitationStatus
    support_status: SupportStatus
    retrieval_timestamp: Optional[datetime]
    verification_data: Optional[dict[str, Any]]
    span_start: int
    span_end: int


class CitationFindingResponse(CitationLineageResponse):
    model_config = ConfigDict(from_attributes=True)

    id: str
    claim_id: Optional[str]
    citation_id: Optional[str]
    reference_id: Optional[str]
    source_id: Optional[str]
    evidence_id: Optional[str]
    finding_type: str
    support_status: SupportStatus
    message: str
    evidence_json: Optional[dict[str, Any]]
    confidence: float
    pipeline_version: str
    model_version: Optional[str]
    created_at: datetime


class CitationAnalysisResponse(BaseModel):
    document_id: str
    document_version_id: str
    findings: list[CitationFindingResponse]
    citations: list[CitationResponse]
    references: list[ReferenceResponse]
    sources: list[SourceResponse]
    limitations: list[str]
