"""Contracts shared by the originality retrieval pipeline.

Retrieval is intentionally not verification.  A candidate score is never
returned as a plagiarism decision and every verified finding carries the
limitations of the available providers.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from app.modules.similarity.models import SimilarityType


@dataclass(frozen=True)
class Candidate:
    """A bounded candidate emitted by an index-backed retriever."""

    chunk_id: str
    document_id: str
    start_char: int
    end_char: int
    text: str
    normalized_text: str
    retrieval_score: float
    retrieval_methods: tuple[str, ...]
    retrieval_scores: Mapping[str, float]
    rank: int
    document_version_id: str = ""
    structure: Mapping[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass(frozen=True)
class VerificationResult:
    """Evidence from an independent verifier, not an authorship conclusion."""

    match_type: SimilarityType
    target_span: tuple[int, int]
    source_span: tuple[int, int]
    scores: Mapping[str, float]
    confidence: float
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]
    verification_methods: tuple[str, ...]
    coverage_spans: tuple[tuple[int, int, int, int], ...] | None = None


@dataclass(frozen=True)
class SimilarityInference:
    """Immutable metadata for one similarity pipeline invocation."""

    organization_id: str
    target_document_id: str
    target_document_version_id: str
    pipeline_version: str
    model_version: str
    index_version: str
    inference_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CandidateRetriever(Protocol):
    """Provider boundary for lexical, n-gram, LSH, BM25, or vector search."""

    name: str

    async def retrieve(
        self,
        *,
        organization_id: str,
        target_document_id: str,
        normalized_text: str,
        limit: int,
    ) -> Sequence[Candidate]:
        """Return at most ``limit`` candidates without pairwise corpus work."""


class CandidateRanker(Protocol):
    """Rank candidates using retrieval signals before expensive verification."""

    def rank(
        self, candidates: Sequence[Candidate], limit: int
    ) -> Sequence[Candidate]: ...


class CandidateVerifier(Protocol):
    """Verify a candidate and abstain when an available signal is insufficient."""

    name: str

    def verify(
        self, target_text: str, candidate: Candidate
    ) -> VerificationResult | None: ...
