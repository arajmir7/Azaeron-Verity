"""Cheap ranking after bounded candidate retrieval."""

from dataclasses import replace
from typing import Sequence

from app.modules.similarity.intelligence.contract import Candidate, CandidateRanker


class RetrievalRanker(CandidateRanker):
    """Stable ranker that preserves retrieval provenance."""

    name = "weighted-retrieval-ranker-v1"

    def rank(self, candidates: Sequence[Candidate], limit: int) -> Sequence[Candidate]:
        if limit <= 0:
            return ()
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.retrieval_score,
                item.retrieval_scores.get("ngram", 0.0),
                item.retrieval_scores.get("lexical", 0.0),
                item.chunk_id,
            ),
            reverse=True,
        )[:limit]
        return tuple(
            replace(candidate, rank=index + 1)
            for index, candidate in enumerate(ordered)
        )
