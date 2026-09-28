"""API schemas for evidence-backed similarity findings."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.modules.similarity.models import SimilarityType


class SimilarityMatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_version_id: str
    source_document_version_id: str | None = None
    source_document_id: Optional[str]
    target_document_id: str
    evidence_id: Optional[str]
    match_type: SimilarityType
    document_span_start: int
    document_span_end: int
    source_span_start: Optional[int]
    source_span_end: Optional[int]
    similarity_score: float
    retrieval_score: Optional[float]
    lexical_score: Optional[float]
    ngram_score: Optional[float]
    semantic_score: Optional[float]
    structural_score: Optional[float]
    verification_score: Optional[float]
    confidence: float
    confidence_reliability: str
    candidate_rank: Optional[int]
    retrieval_methods: Optional[list[str]]
    verification_methods: Optional[list[str]]
    matched_text: Optional[str]
    source_text: Optional[str]
    metadata_json: Optional[dict[str, Any]]
    pipeline_version: str
    model_version: Optional[str]
    created_at: datetime


class SimilarityMatchListResponse(BaseModel):
    matches: list[SimilarityMatchResponse]
    total: int
    document_version_id: str
    page: int = 1
    page_size: int = 50
    similarity_is_not_plagiarism: bool = True
    limitations: list[str]


class SimilaritySummary(BaseModel):
    total_words: int
    eligible_words: int
    excluded_words: int
    matched_words: int
    percentage: float | None
    included_match_count: int
    recorded_match_count: int


class SimilarityReviewMatch(BaseModel):
    id: str
    evidence_id: str | None
    evidence_node_id: str | None
    source_document_id: str
    source_document_version_id: str
    document_version_id: str
    source_title: str
    source_category: str
    corpus_state: str
    source_content_hash: str
    source_text_hash: str
    target_content_hash: str
    target_text_hash: str
    retrieved_at: str
    source_uploaded_at: str
    match_type: str
    document_span_start: int
    document_span_end: int
    source_span_start: int
    source_span_end: int
    matched_text: str
    source_text: str
    context_before: str
    context_after: str
    source_context_before: str
    source_context_after: str
    quotation_status: str
    citation_status: str
    group: str
    flags: list[dict[str, str]]
    matched_words: int
    included_words: int
    excluded: bool
    exclusion_reasons: list[str]


class SimilarityMatchPage(BaseModel):
    items: list[SimilarityReviewMatch]
    total: int
    page: int
    page_size: int


class SimilaritySourcePage(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class SimilarityWorkflowResponse(BaseModel):
    document_id: str
    document_version_id: str
    version_number: int
    analysis_id: str | None
    analysis_state: str
    analyzed_at: datetime | None
    pipeline_version: str
    text_hash: str
    content_hash: str
    text_basis: str = "processed.cleaned_text"
    corpus: list[dict[str, Any]]
    summary: SimilaritySummary
    groups: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    exclusions: dict[str, Any]
    exclusions_hash: str
    matches: SimilarityMatchPage
    sources: SimilaritySourcePage
    interpretation: str
    calculation: str
    limitations: list[str]
