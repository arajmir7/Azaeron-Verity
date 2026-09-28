"""Versioned provenance timeline and export contracts."""

from typing import Any, Optional
from pydantic import BaseModel


class ProvenanceVersionResponse(BaseModel):
    id: str
    document_id: str
    version_number: int
    content_hash: str
    sha256_fingerprint: str
    created_by_id: Optional[str]
    uploaded_by_id: Optional[str]
    created_at: Optional[str]
    uploaded_at: Optional[str]
    storage_object: str
    previous_version_id: Optional[str]
    lifecycle_state: str
    change_summary: Optional[str]
    edit_type: Optional[str]


class ProvenanceAnalysisRunResponse(BaseModel):
    id: str
    document_version_id: str
    job_id: Optional[str]
    model_id: str
    model_version: str
    pipeline_version: str
    dataset_version: Optional[str]
    status: str
    abstained: bool
    input_fingerprint: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    metadata: dict[str, Any]


class ProvenanceEventResponse(BaseModel):
    id: str
    event_type: str
    document_version_id: str
    analysis_run_id: Optional[str]
    user_id: Optional[str]
    event_timestamp: Optional[str]
    description: Optional[str]
    sha256_before: Optional[str]
    sha256_after: Optional[str]
    metadata: dict[str, Any]
    pipeline_version: str
    model_version: Optional[str]


class ProvenanceDocumentResponse(BaseModel):
    id: str
    organization_id: str
    status: str
    content_hash: str
    storage_object: str
    created_at: Optional[str]
    uploaded_at: Optional[str]


class ProvenanceTimelineResponse(BaseModel):
    schema_version: str
    document: ProvenanceDocumentResponse
    versions: list[ProvenanceVersionResponse]
    analysis_runs: list[ProvenanceAnalysisRunResponse]
    provenance_events: list[ProvenanceEventResponse]
    limitations: list[str]
