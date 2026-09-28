"""Composable retrieval, ranking, and verification primitives for similarity."""

from app.modules.similarity.intelligence.contract import (
    Candidate,
    CandidateRetriever,
    SimilarityInference,
    VerificationResult,
)
from app.modules.similarity.intelligence.normalization import (
    NormalizedChunk,
    chunk_text,
    normalize_text,
    token_ngrams,
    tokenize,
)
from app.modules.similarity.intelligence.verification import DeterministicVerifier

__all__ = [
    "Candidate",
    "CandidateRetriever",
    "DeterministicVerifier",
    "NormalizedChunk",
    "SimilarityInference",
    "VerificationResult",
    "chunk_text",
    "normalize_text",
    "token_ngrams",
    "tokenize",
]
