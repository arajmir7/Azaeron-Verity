"""Bounded hybrid retrieval within tenant RLS using existing PostgreSQL indexes."""

from collections import defaultdict
from datetime import datetime
from dataclasses import replace
from typing import TypedDict
from sqlalchemy import select, func, text as sql_text, or_
from app.modules.documents.models import Document, DocumentStatus
from app.modules.similarity.models import DocumentChunk, SimilarityIndexEntry
from app.modules.similarity.intelligence.contract import Candidate
from app.modules.similarity.intelligence.normalization import tokenize, token_ngrams
from app.modules.similarity.intelligence.chunks import INDEX_VERSION, fingerprint_bands


class RetrievalStats(TypedDict):
    retrieval_queries: int
    candidate_rows: int
    verified_pairs: int
    pairwise_document_scans: int
    methods: dict[str, int]


class HybridRetriever:
    name = "lexical-phrase-minhash-vector-rrf-v2"

    def __init__(self, db, provider):
        self.db, self.provider = db, provider
        self.cutoff: datetime | None = None
        self.limit_reached = False
        self.stats: RetrievalStats = {
            "retrieval_queries": 0,
            "candidate_rows": 0,
            "verified_pairs": 0,
            "pairwise_document_scans": 0,
            "methods": {},
        }

    async def retrieve(
        self,
        *,
        organization_id,
        target_document_id,
        normalized_text,
        limit,
        vector=None
    ):
        tokens = tokenize(normalized_text)
        methods = {
            "token": tuple(dict.fromkeys(tokens))[:100],
            "ngram": tuple(dict.fromkeys(token_ngrams(tokens)))[:160],
            "fingerprint": fingerprint_bands(tokens),
        }
        lists = {}
        scopes = [
            DocumentChunk.organization_id == organization_id,
            Document.organization_id == organization_id,
            DocumentChunk.document_id != target_document_id,
            Document.status != DocumentStatus.ARCHIVED,
            DocumentChunk.index_status == "ACTIVE",
            DocumentChunk.index_version == INDEX_VERSION,
        ]
        if self.cutoff:
            scopes.append(DocumentChunk.indexed_at <= self.cutoff)
        for method, terms in methods.items():
            if not terms:
                continue
            score = func.count(func.distinct(SimilarityIndexEntry.term))
            rows = (
                await self.db.execute(
                    select(SimilarityIndexEntry.chunk_id, score.label("hits"))
                    .join(
                        DocumentChunk, DocumentChunk.id == SimilarityIndexEntry.chunk_id
                    )
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        *scopes,
                        SimilarityIndexEntry.organization_id == organization_id,
                        SimilarityIndexEntry.index_version == INDEX_VERSION,
                        SimilarityIndexEntry.term_type == method,
                        SimilarityIndexEntry.term.in_(terms)
                    )
                    .group_by(SimilarityIndexEntry.chunk_id)
                    .order_by(score.desc(), SimilarityIndexEntry.chunk_id)
                    .limit(limit + 1)
                )
            ).all()
            self.stats["retrieval_queries"] += 1
            self.limit_reached |= len(rows) > limit
            lists[method] = [
                (str(key), min(1.0, float(hits) / len(terms)))
                for key, hits in rows[:limit]
            ]
        if (
            vector is not None
            and self.provider.available
            and self.db.bind.dialect.name == "postgresql"
        ):
            # Filtered HNSW can under-return: preserve that limitation in snapshots.
            # No corpus-wide vector materialization or Python pairwise fallback.
            await self.db.execute(sql_text("SET LOCAL hnsw.ef_search = 100"))
            distance = DocumentChunk.embedding_vector.cosine_distance(vector)
            rows = (
                await self.db.execute(
                    select(DocumentChunk.id, distance.label("distance"))
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        *scopes,
                        DocumentChunk.embedding_vector.is_not(None),
                        DocumentChunk.embedding_model == self.provider.model_id
                    )
                    .order_by(distance)
                    .limit(limit)
                )
            ).all()
            lists["vector"] = [
                (str(key), max(0.0, min(1.0, 1 - float(value)))) for key, value in rows
            ]
            self.stats["retrieval_queries"] += 1
            self.limit_reached |= len(rows) >= limit
        scores: dict[str, dict[str, float]] = defaultdict(dict)
        fused: dict[str, float] = defaultdict(float)
        aliases = {
            # Retrieval channel label, not a password.
            "token": "lexical",  # nosec B105
            "ngram": "phrase",
            "fingerprint": "minhash",
            "vector": "vector",
        }
        for method, rows in lists.items():
            self.stats["methods"][aliases[method]] = self.stats["methods"].get(
                aliases[method], 0
            ) + len(rows)
            for rank, (key, rank_score) in enumerate(rows, 1):
                scores[key][aliases[method]] = rank_score
                fused[key] += 1 / (60 + rank)
        self.stats["candidate_rows"] += sum(map(len, lists.values()))
        keys = sorted(scores, key=lambda key: (-fused[key], key))[:limit]
        self.limit_reached |= len(scores) > limit
        if not keys:
            return ()
        chunks = (
            (
                await self.db.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.organization_id == organization_id,
                        DocumentChunk.id.in_(keys),
                    )
                )
            )
            .scalars()
            .all()
        )
        result = []
        for chunk in chunks:
            key = str(chunk.id)
            result.append(
                Candidate(
                    key,
                    str(chunk.document_id),
                    chunk.start_char,
                    chunk.end_char,
                    chunk.text,
                    chunk.normalized_text or "",
                    min(1.0, fused[key] * 61 / max(1, len(lists))),
                    tuple(sorted(scores[key])),
                    scores[key],
                    0,
                    str(chunk.document_version_id),
                    structure=chunk.structure_json or {},
                    embedding=(
                        list(chunk.embedding_vector)
                        if chunk.embedding_vector is not None
                        else None
                    ),
                )
            )
        return tuple(sorted(result, key=lambda c: (-c.retrieval_score, c.chunk_id)))
