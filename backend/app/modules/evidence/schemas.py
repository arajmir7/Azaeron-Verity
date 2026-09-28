"""AZAERON evidence and report schemas."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict

from app.modules.evidence.models import EvidenceNodeType


class EvidenceNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: str
    node_type: EvidenceNodeType
    node_id: str
    canonical_type: str
    entity_id: str
    entity_type: str
    document_id: str
    organization_id: Optional[str] = None
    document_version_id: Optional[str] = None
    finding_type: str = "evidence"
    source_id: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    pipeline_version: Optional[str] = None
    title: str
    description: Optional[str] = None
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    span_text: Optional[str] = None
    confidence: float
    severity: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class EvidenceEdgeResponse(BaseModel):
    document_id: str
    document_version_id: str
    model_config = ConfigDict(from_attributes=True)
    organization_id: Optional[str] = None
    source_node_id: str
    target_node_id: str
    edge_type: str
    weight: float
    description: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class EvidenceGraphResponse(BaseModel):
    schema_version: str = "evidence-graph-v2"
    document_id: Optional[str] = None
    document_version_id: Optional[str] = None
    complete: bool = True
    orphan_finding_node_ids: list[str] = []
    nodes: list[EvidenceNodeResponse]
    edges: list[EvidenceEdgeResponse]
    limitations: list[str] = []


class IntegrityDimension(BaseModel):
    name: str
    score: Optional[float] = None
    confidence: Optional[str] = None
    verdict: Optional[str] = None
    evidence: list[str] = []
    limitations: list[str] = []
    recommended_action: Optional[str] = None


class IntegrityReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    status: str
    document_health: Optional[str] = None
    dimensions: list[IntegrityDimension] = []
    priority_issues: list[dict] = []
    evidence_summary: Optional[str] = None
    created_at: datetime


class ReportEvidence(BaseModel):
    evidence_node_id: str
    canonical_type: str
    title: str
    explanation: str
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    span_text: Optional[str] = None
    confidence: Optional[float] = None
    confidence_reliability: str = "UNAVAILABLE"
    source_ids: list[str] = []
    source_titles: list[str] = []
    claim_ids: list[str] = []
    citation_ids: list[str] = []


class ReportHighlight(ReportEvidence):
    dimension: str
    segment_type: str = "span"
    status: str


class ReportDimension(BaseModel):
    key: str
    label: str
    status: str
    summary: str
    confidence: Optional[float] = None
    confidence_reliability: str = "UNAVAILABLE"
    evidence: list[ReportEvidence] = []
    limitations: list[str] = []
    recommended_action: str


class EvidenceFirstReportResponse(BaseModel):
    schema_version: str = "evidence-first-report-v1"
    report_status: str = "PRODUCTION"
    document_id: str
    document_version_id: Optional[str] = None
    generated_at: datetime
    dimensions: list[ReportDimension]
    highlights: list[ReportHighlight] = []
    limitations: list[str] = []
    graph: EvidenceGraphResponse
