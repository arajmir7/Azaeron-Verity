"""Scalable originality retrieval service.

The service is deliberately staged:

document -> chunks -> normalized/indexed terms -> bounded candidates -> rank
-> deterministic verification -> evidence-linked matches

It never compares every document pair. Candidate generation is an indexed
SQL aggregation over terms belonging to the target chunk, and verification is
performed only for the bounded ranked set.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from typing import List, Sequence
import uuid

from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.documents.models import Document, DocumentVersion, DocumentStatus
from app.modules.evidence.models import EvidenceNodeType
from app.modules.evidence.service import EvidenceService
from app.modules.processing.models import ProcessedDocument
from app.modules.documents.target import require_processed_target
from app.modules.similarity.intelligence.contract import Candidate, VerificationResult
from app.modules.similarity.intelligence.normalization import (
    NORMALIZATION_VERSION,
    NormalizedChunk,
    chunk_text,
    normalize_text,
    token_ngrams,
    tokenize,
)
from app.modules.similarity.intelligence.ranking import RetrievalRanker
from app.modules.similarity.review import TextAnnotations, RULES_VERSION
from app.modules.similarity.intelligence.verification import DeterministicVerifier
from app.modules.similarity.models import (
    DocumentChunk,
    SimilarityIndexEntry,
    SimilarityMatch,
    SimilarityAnalysis,
)

logger = get_logger(__name__)

INDEX_VERSION = "hybrid-structured-index-v2"
PIPELINE_VERSION = "similarity-engine-v2"
MODEL_VERSION = "span-alignment-v3"
MAX_RETRIEVAL_CANDIDATES = 200
MAX_VERIFICATION_CANDIDATES = 25
MAX_MATCHES = 2000
MAX_TARGET_CHUNKS = 400


class InvertedTermRetriever:
    """Candidate retrieval over a tenant-scoped persistent inverted index."""

    name = "lexical-ngram-inverted-index-v1"

    def __init__(self, db: AsyncSession):
        self.db = db
        self.limit_reached = False
        self.cutoff: datetime | None = None

    async def retrieve(
        self,
        *,
        organization_id: str,
        target_document_id: str,
        normalized_text: str,
        limit: int,
    ) -> Sequence[Candidate]:
        if limit <= 0:
            return ()
        sequence = tokenize(normalized_text)
        tokens = tuple(dict.fromkeys(sequence))[:80]
        ngrams = tuple(dict.fromkeys(token_ngrams(sequence)))[:120]
        if not tokens and not ngrams:
            return ()

        terms_clause = or_(
            (SimilarityIndexEntry.term_type == "token")
            & SimilarityIndexEntry.term.in_(tokens),
            (SimilarityIndexEntry.term_type == "ngram")
            & SimilarityIndexEntry.term.in_(ngrams),
        )
        result = await self.db.execute(
            select(
                SimilarityIndexEntry.chunk_id,
                SimilarityIndexEntry.document_id,
                SimilarityIndexEntry.term_type,
                func.count(func.distinct(SimilarityIndexEntry.term)).label(
                    "matched_terms"
                ),
            )
            .join(DocumentChunk, DocumentChunk.id == SimilarityIndexEntry.chunk_id)
            .join(Document, Document.id == SimilarityIndexEntry.document_id)
            .where(
                Document.organization_id == organization_id,
                Document.status != DocumentStatus.ARCHIVED,
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.index_status == "ACTIVE",
                (
                    or_(
                        DocumentChunk.indexed_at.is_(None),
                        DocumentChunk.indexed_at <= self.cutoff,
                    )
                    if self.cutoff
                    else true()
                ),
                SimilarityIndexEntry.organization_id == organization_id,
                SimilarityIndexEntry.document_id != target_document_id,
                SimilarityIndexEntry.index_version == "inverted-terms-v1",
                terms_clause,
            )
            .group_by(
                SimilarityIndexEntry.chunk_id,
                SimilarityIndexEntry.document_id,
                SimilarityIndexEntry.term_type,
            )
            .order_by(
                func.count(func.distinct(SimilarityIndexEntry.term)).desc(),
                SimilarityIndexEntry.chunk_id,
                SimilarityIndexEntry.term_type,
            )
            .limit(max(limit * 4, limit))
        )

        scores: dict[str, dict[str, float | str]] = {}
        rows = result.all()
        self.limit_reached |= len(rows) >= max(limit * 4, limit)
        for chunk_id, document_id, term_type, matched_terms in rows:
            entry = scores.setdefault(
                str(chunk_id),
                {"document_id": str(document_id), "lexical": 0.0, "ngram": 0.0},
            )
            denominator = len(tokens) if term_type == "token" else len(ngrams)
            entry["lexical" if term_type == "token" else "ngram"] = min(
                1.0, float(matched_terms) / max(1, denominator)
            )

        if not scores:
            return ()
        chunk_result = await self.db.execute(
            select(DocumentChunk).where(
                DocumentChunk.id.in_(tuple(scores.keys())),
                DocumentChunk.organization_id == organization_id,
                DocumentChunk.index_status == "ACTIVE",
            )
        )
        chunks = {str(chunk.id): chunk for chunk in chunk_result.scalars().all()}
        candidates: list[Candidate] = []
        for chunk_id, score_data in scores.items():
            chunk = chunks.get(chunk_id)
            if chunk is None:
                continue
            lexical = float(score_data["lexical"])
            ngram = float(score_data["ngram"])
            retrieval_score = min(1.0, 0.60 * lexical + 0.40 * ngram)
            methods = (
                ("lexical-inverted-index",)
                if ngram == 0
                else ("lexical-inverted-index", "ngram-inverted-index")
            )
            candidates.append(
                Candidate(
                    chunk_id=chunk_id,
                    document_id=str(chunk.document_id),
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    text=chunk.text,
                    normalized_text=chunk.normalized_text or normalize_text(chunk.text),
                    retrieval_score=retrieval_score,
                    retrieval_methods=methods,
                    retrieval_scores={"lexical": lexical, "ngram": ngram},
                    rank=0,
                    document_version_id=str(chunk.document_version_id),
                )
            )
        self.limit_reached |= len(candidates) >= limit
        return tuple(
            sorted(
                candidates,
                key=lambda candidate: (-candidate.retrieval_score, candidate.chunk_id),
            )[:limit]
        )


class SimilarityService:
    """Structured hybrid retrieval with immutable evidence per analysis run."""

    def __init__(self, db):
        from app.modules.similarity.providers import embedding_provider
        from app.modules.similarity.retrieval import HybridRetriever
        from app.modules.similarity.intelligence.verification import SpanVerifierV2

        self.db = db
        self.provider = embedding_provider()
        self.retriever = HybridRetriever(db, self.provider)
        self.ranker = RetrievalRanker()
        self.verifier = SpanVerifierV2(self.provider)

    async def analyze_similarity(self, document_id, processed, analysis_run_id=None):
        from app.modules.documents.target import AnalysisTarget
        from app.modules.governance.models import AnalysisRun, AnalysisRunStatus
        from app.modules.jobs.models import Job, JobType, JobStatus
        from app.modules.similarity.providers import source_metadata
        from app.modules.similarity.intelligence.chunks import CHUNK_VERSION
        from app.modules.similarity.models import SimilarityType
        from app.modules.processing.structure import digest

        require_processed_target(document_id, processed)
        org, version_id = str(processed.organization_id), str(
            processed.document_version_id
        )
        target = await AnalysisTarget.resolve(
            self.db, org, document_id, version_id, lock=True
        )
        run_key = analysis_run_id or "default"
        prior = (
            await self.db.execute(
                select(SimilarityAnalysis).where(
                    SimilarityAnalysis.organization_id == org,
                    SimilarityAnalysis.document_version_id == version_id,
                    SimilarityAnalysis.pipeline_version == PIPELINE_VERSION,
                    SimilarityAnalysis.run_key == run_key,
                )
            )
        ).scalar_one_or_none()
        if prior:
            if not prior.sealed:
                raise ValueError(
                    "Incomplete similarity snapshot requires transaction recovery"
                )
            return list(
                (
                    await self.db.execute(
                        select(SimilarityMatch)
                        .where(
                            SimilarityMatch.organization_id == org,
                            SimilarityMatch.analysis_id == prior.id,
                        )
                        .order_by(
                            SimilarityMatch.document_span_start, SimilarityMatch.id
                        )
                    )
                ).scalars()
            )
        identifier = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL, f"{org}:{version_id}:{PIPELINE_VERSION}:{run_key}"
            )
        )
        owned_job = None
        if analysis_run_id:
            run = (
                await self.db.execute(
                    select(AnalysisRun).where(
                        AnalysisRun.id == analysis_run_id,
                        AnalysisRun.organization_id == org,
                        AnalysisRun.document_id == document_id,
                        AnalysisRun.document_version_id == version_id,
                    )
                )
            ).scalar_one_or_none()
            if run is None:
                raise ValueError(
                    "Similarity analysis run does not match its immutable target"
                )
        else:
            owned_job = Job(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, identifier + ":job")),
                organization_id=org,
                document_id=document_id,
                document_version_id=version_id,
                job_type=JobType.SIMILARITY_ANALYSIS,
                status=JobStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                input_data={
                    "document_version_id": version_id,
                    "storage_key": target.version.storage_path,
                },
            )
            self.db.add(owned_job)
            await self.db.flush()
            run = AnalysisRun(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, identifier + ":run")),
                organization_id=org,
                document_id=document_id,
                document_version_id=version_id,
                job_id=str(owned_job.id),
                model_id="similarity-retrieval-pipeline",
                model_version=MODEL_VERSION,
                pipeline_version=PIPELINE_VERSION,
                status=AnalysisRunStatus.STARTED,
                input_fingerprint=target.version.sha256_fingerprint,
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(run)
            await self.db.flush()
        text = processed.cleaned_text or ""
        chunks = await self._store_chunks(document_id, text, processed)
        cutoff = datetime.now(timezone.utc)
        self.retriever.cutoff = cutoff
        scope = (
            DocumentChunk.organization_id == org,
            Document.organization_id == org,
            DocumentChunk.document_id != document_id,
            DocumentChunk.index_version == INDEX_VERSION,
            DocumentChunk.index_status == "ACTIVE",
            DocumentChunk.indexed_at <= cutoff,
            Document.status != DocumentStatus.ARCHIVED,
        )
        corpus_count = int(
            await self.db.scalar(
                select(func.count(func.distinct(DocumentChunk.document_version_id)))
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(*scope)
            )
            or 0
        )
        vector_count = (
            int(
                await self.db.scalar(
                    select(func.count(DocumentChunk.id))
                    .join(Document, Document.id == DocumentChunk.document_id)
                    .where(
                        *scope,
                        DocumentChunk.embedding_model == self.provider.model_id,
                        DocumentChunk.embedding_vector.is_not(None),
                    )
                )
            )
            or 0
        )
        analysis = SimilarityAnalysis(
            id=identifier,
            organization_id=org,
            document_id=document_id,
            document_version_id=version_id,
            analysis_run_id=str(run.id),
            run_key=run_key,
            pipeline_version=PIPELINE_VERSION,
            model_version=MODEL_VERSION,
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            corpus_state="PRIVATE_WORKSPACE" if corpus_count else "UNAVAILABLE",
            corpus_version_count=corpus_count,
            index_version=INDEX_VERSION,
            completed_at=cutoff,
            sealed=False,
            truncated=len(chunks) > MAX_TARGET_CHUNKS,
            metadata_json={},
        )
        self.db.add(analysis)
        await self.db.flush()
        records: dict[tuple, tuple] = {}
        candidates_seen = set()
        target_vectors = (
            self.provider.encode([c.text for c in chunks[:MAX_TARGET_CHUNKS]])
            if self.provider.available
            else []
        )
        for i, chunk in enumerate(chunks[:MAX_TARGET_CHUNKS]):
            candidates = await self.retriever.retrieve(
                organization_id=org,
                target_document_id=document_id,
                normalized_text=chunk.normalized_text,
                limit=MAX_RETRIEVAL_CANDIDATES,
                vector=target_vectors[i] if target_vectors else None,
            )
            analysis.truncated |= (
                len(candidates) > MAX_VERIFICATION_CANDIDATES
                or self.retriever.limit_reached
            )
            for candidate in self.ranker.rank(candidates, MAX_VERIFICATION_CANDIDATES):
                candidates_seen.add(candidate.chunk_id)
                self.retriever.stats["verified_pairs"] += 1
                for finding in self.verifier.verify_all(
                    chunk.text, candidate, chunk.structure
                ):
                    ta, tb = (
                        chunk.start_char + offset for offset in finding.target_span
                    )
                    sa, sb = finding.source_span
                    key = (
                        candidate.document_version_id,
                        ta,
                        tb,
                        sa,
                        sb,
                        finding.match_type.value,
                    )
                    coverage = (
                        [
                            (chunk.start_char + a, chunk.start_char + b, c, d)
                            for a, b, c, d in finding.coverage_spans
                        ]
                        if finding.coverage_spans is not None
                        else [(ta, tb, sa, sb)]
                    )
                    records.setdefault(key, (candidate, finding, coverage))
            if len(records) >= MAX_MATCHES * 3:
                analysis.truncated = True
                break
        # A component groups overlapping target passages across all sources.
        # Exact records remain individually addressable for source-side traceability.
        selected = sorted(
            records.items(),
            key=lambda item: (
                item[0][1],
                item[0][2],
                item[0][0],
                item[0][3],
                item[0][5],
            ),
        )[:MAX_MATCHES]
        analysis.truncated |= len(records) > MAX_MATCHES
        groups: list[dict] = []
        for key, record in selected:
            if groups and key[1] < groups[-1]["end"]:
                groups[-1]["end"] = max(groups[-1]["end"], key[2])
                groups[-1]["records"].append((key, record))
            else:
                groups.append(
                    {"start": key[1], "end": key[2], "records": [(key, record)]}
                )
        sources = {}
        matches = []
        group_records = []
        annotations = TextAnnotations(text)
        for group in groups:
            group_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{identifier}:group:{group['start']}:{group['end']}",
                )
            )
            member_ids = []
            for key, (candidate, finding, coverage) in group["records"]:
                source_version_id, ta, tb, sa, sb, _ = key
                if source_version_id not in sources:
                    row = (
                        await self.db.execute(
                            select(Document, DocumentVersion, ProcessedDocument)
                            .join(
                                DocumentVersion,
                                DocumentVersion.document_id == Document.id,
                            )
                            .join(
                                ProcessedDocument,
                                ProcessedDocument.document_version_id
                                == DocumentVersion.id,
                            )
                            .where(
                                Document.organization_id == org,
                                ProcessedDocument.organization_id == org,
                                DocumentVersion.id == source_version_id,
                            )
                        )
                    ).one_or_none()
                    if row is None:
                        raise ValueError(
                            "Retrieved source no longer has exact version evidence"
                        )
                    sources[source_version_id] = row
                source_doc, source_version, source_processed = sources[
                    source_version_id
                ]
                source_text = source_processed.cleaned_text or ""
                if not (0 <= ta < tb <= len(text) and 0 <= sa < sb <= len(source_text)):
                    raise ValueError(
                        "Similarity evidence span is outside its immutable text"
                    )
                for a, b, c, d in coverage:
                    if normalize_text(text[a:b]) != normalize_text(source_text[c:d]):
                        raise ValueError(
                            "Verified token coverage does not resolve to both immutable strings"
                        )
                mid = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{identifier}:{source_version_id}:{ta}:{tb}:{sa}:{sb}:{finding.match_type.value}",
                    )
                )
                review = annotations.classify(ta, tb)
                if finding.match_type in {
                    SimilarityType.SEMANTIC,
                    SimilarityType.STRUCTURAL,
                    SimilarityType.LEXICAL,
                }:
                    review["flags"] = []
                provenance = source_metadata(
                    source_doc, source_version, source_processed, cutoff.isoformat()
                )
                match = SimilarityMatch(
                    id=mid,
                    analysis_id=identifier,
                    group_id=group_id,
                    organization_id=org,
                    document_id=document_id,
                    target_document_id=document_id,
                    document_version_id=version_id,
                    source_document_id=str(source_doc.id),
                    source_document_version_id=source_version_id,
                    pipeline_version=PIPELINE_VERSION,
                    model_version=MODEL_VERSION,
                    match_type=finding.match_type,
                    document_span_start=ta,
                    document_span_end=tb,
                    source_span_start=sa,
                    source_span_end=sb,
                    similarity_score=finding.scores["verification"],
                    retrieval_score=finding.scores["retrieval"],
                    lexical_score=finding.scores["lexical"],
                    ngram_score=finding.scores["ngram"],
                    structural_score=finding.scores["structural"],
                    semantic_score=finding.scores.get("semantic"),
                    verification_score=finding.scores["verification"],
                    confidence=0.0,
                    confidence_reliability="UNAVAILABLE",
                    candidate_rank=candidate.rank,
                    retrieval_methods=list(candidate.retrieval_methods),
                    verification_methods=list(finding.verification_methods),
                    matched_text=text[ta:tb],
                    source_text=source_text[sa:sb],
                    context_before=text[max(0, ta - 120) : ta],
                    context_after=text[tb : tb + 120],
                    metadata_json={
                        "source_title": provenance["title"],
                        "source_category": "WORKSPACE_DOCUMENT",
                        "corpus_state": "PRIVATE_WORKSPACE",
                        "source_id": source_version_id,
                        "source_metadata": provenance,
                        "source_content_hash": source_version.sha256_fingerprint,
                        "source_text_hash": hashlib.sha256(
                            source_text.encode()
                        ).hexdigest(),
                        "source_uploaded_at": source_version.uploaded_at.isoformat(),
                        "retrieved_at": cutoff.isoformat(),
                        "source_context_before": source_text[max(0, sa - 120) : sa],
                        "source_context_after": source_text[sb : sb + 120],
                        "target_content_hash": target.version.sha256_fingerprint,
                        "target_text_hash": analysis.text_hash,
                        "text_basis": "processed.cleaned_text",
                        "target_parser_version": processed.parser_version,
                        "source_parser_version": source_processed.parser_version,
                        "target_structure_fingerprint": processed.structure_fingerprint,
                        "source_structure_fingerprint": source_processed.structure_fingerprint,
                        "target_chunk_id": candidate.chunk_id if False else None,
                        "source_chunk_id": candidate.chunk_id,
                        "coverage_spans": [
                            {"target": [a, b], "source": [c, d]}
                            for a, b, c, d in coverage
                        ],
                        "verification_state": (
                            "EXPERIMENTAL"
                            if finding.match_type == SimilarityType.SEMANTIC
                            else "VERIFIED_ALIGNMENT"
                        ),
                        "score_components": dict(finding.scores),
                        "retrieval_scores": dict(candidate.retrieval_scores),
                        "review": review,
                        "review_rules_version": RULES_VERSION,
                        "limitations": list(finding.limitations),
                        "embedding_model": (
                            self.provider.model_id
                            if finding.match_type == SimilarityType.SEMANTIC
                            else None
                        ),
                    },
                )
                self.db.add(match)
                matches.append(match)
                member_ids.append(mid)
            group_records.append(
                {
                    "id": group_id,
                    "target_span": [group["start"], group["end"]],
                    "match_ids": member_ids,
                }
            )
        await self.db.flush()
        await self._link_match_evidence(document_id, processed, matches)
        capabilities = {
            "EXACT": "AVAILABLE",
            "NEAR_DUPLICATE": "AVAILABLE",
            "LEXICAL": "AVAILABLE",
            "SEMANTIC": (
                "EXPERIMENTAL"
                if self.provider.available and self.db.bind.dialect.name == "postgresql"
                else "UNAVAILABLE"
            ),
            "STRUCTURAL": "UNAVAILABLE",
            "PROBABLE_PARAPHRASE": "UNAVAILABLE",
        }
        payload = {
            "analysis_run_id": str(run.id),
            "text_basis": "processed.cleaned_text",
            "processing_version": processed.pipeline_version,
            "parser_version": processed.parser_version,
            "structure_fingerprint": processed.structure_fingerprint,
            "retrieval_cutoff": cutoff.isoformat(),
            "chunk_version": CHUNK_VERSION,
            "target_chunks": len(chunks),
            "target_chunk_limit": MAX_TARGET_CHUNKS,
            "retrieval_limit": MAX_RETRIEVAL_CANDIDATES,
            "verification_limit": MAX_VERIFICATION_CANDIDATES,
            "match_limit": MAX_MATCHES,
            "candidate_chunks": len(candidates_seen),
            "candidate_ids": sorted(candidates_seen),
            "candidate_snapshot_hash": digest(sorted(candidates_seen)),
            "match_groups": group_records,
            "embedding_provider": self.provider.state(),
            "vector_indexed_chunks": vector_count,
            "capabilities": capabilities,
            "external_full_text": {"state": "UNAVAILABLE", "searched": False},
            "work": self.retriever.stats,
            "source_versions": sorted(sources),
            "match_manifest": [
                {
                    "id": m.id,
                    "type": m.match_type.value,
                    "source": m.source_document_version_id,
                    "target_span": [m.document_span_start, m.document_span_end],
                    "source_span": [m.source_span_start, m.source_span_end],
                    "scores": (m.metadata_json or {})["score_components"],
                    "evidence_id": m.evidence_id,
                }
                for m in matches
            ],
        }
        analysis.snapshot_fingerprint = digest(payload)
        analysis.metadata_json = payload
        analysis.completed_at = datetime.now(timezone.utc)
        analysis.sealed = True
        if owned_job:
            owned_job.status = JobStatus.COMPLETED
            owned_job.completed_at = analysis.completed_at
            owned_job.progress_percent = 100
            owned_job.result_data = {
                "analysis_id": identifier,
                "document_version_id": version_id,
                "snapshot_fingerprint": analysis.snapshot_fingerprint,
            }
            run.status = AnalysisRunStatus.COMPLETED
            run.completed_at = analysis.completed_at
            run.metadata_json = {
                "similarity_analysis_id": identifier,
                "snapshot_fingerprint": analysis.snapshot_fingerprint,
                "parser_version": processed.parser_version,
                "structure_fingerprint": processed.structure_fingerprint,
            }
        await self.db.flush()
        return matches

    async def _link_match_evidence(self, document_id, processed, matches):
        for match in matches:
            node = await EvidenceService(self.db).add_node(
                document_id=document_id,
                node_type=EvidenceNodeType.SIMILARITY,
                title=f'{match.match_type.value.replace("_"," ").capitalize()} similarity evidence',
                description="The recorded source and target spans carry independent alignment or experimental semantic evidence. Similarity is not a plagiarism determination.",
                span_start=match.document_span_start,
                span_end=match.document_span_end,
                span_text=match.matched_text,
                confidence=0.0,
                metadata={
                    **match.metadata_json,
                    "target_span": [match.document_span_start, match.document_span_end],
                    "source_span": [match.source_span_start, match.source_span_end],
                    "source_document_id": match.source_document_id,
                    "source_document_version_id": match.source_document_version_id,
                    "match_type": match.match_type.value,
                    "group_id": match.group_id,
                    "analysis_id": match.analysis_id,
                    "plagiarism_assessment": "NOT_ASSESSED",
                },
                document_version_id=str(processed.document_version_id),
                finding_type="similarity_match",
                source_id=str(match.id),
                model_id="similarity-retrieval-pipeline",
                model_version=MODEL_VERSION,
                pipeline_version=PIPELINE_VERSION,
            )
            match.evidence_id = str(node.id)
        await self.db.flush()

    async def _store_chunks(self, document_id, text, processed):
        from app.modules.similarity.intelligence.chunks import (
            structured_chunks,
            fingerprint_bands,
            CHUNK_VERSION,
        )

        chunks = structured_chunks(text, getattr(processed, "structure_json", None))
        org, version_id = str(processed.organization_id), str(
            processed.document_version_id
        )
        existing = (
            (
                await self.db.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.organization_id == org,
                        DocumentChunk.document_version_id == version_id,
                        DocumentChunk.document_id == document_id,
                        DocumentChunk.index_version == INDEX_VERSION,
                    )
                )
            )
            .scalars()
            .all()
        )
        if existing:
            if len(existing) != len(chunks) or any(
                c.text != chunks[c.chunk_index].text for c in existing
            ):
                raise ValueError(
                    "Existing structured index differs from immutable parser output"
                )
            return chunks
        # New index revision coexists with old chunks; no historical index rewrite.
        vectors = (
            self.provider.encode([c.text for c in chunks])
            if self.provider.available and chunks
            else []
        )
        rows = []
        for data in chunks:
            row = DocumentChunk(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"{org}:{version_id}:{INDEX_VERSION}:{data.chunk_index}",
                    )
                ),
                organization_id=org,
                document_id=document_id,
                document_version_id=version_id,
                pipeline_version=PIPELINE_VERSION,
                model_version=CHUNK_VERSION,
                chunk_index=data.chunk_index,
                text=data.text,
                start_char=data.start_char,
                end_char=data.end_char,
                token_count=len(data.tokens),
                normalized_text=data.normalized_text,
                content_hash=hashlib.sha256(data.text.encode()).hexdigest(),
                index_version=INDEX_VERSION,
                index_status="ACTIVE",
                indexed_at=datetime.now(timezone.utc),
                structure_json=data.structure,
                embedding_vector=vectors[data.chunk_index] if vectors else None,
                embedding_model=self.provider.model_id if vectors else None,
            )
            rows.append(row)
        self.db.add_all(rows)
        await self.db.flush()
        entries = []
        for row, data in zip(rows, chunks):
            for kind, terms in [
                ("token", data.tokens),
                ("ngram", data.ngrams),
                ("fingerprint", fingerprint_bands(data.tokens)),
            ]:
                for term, count in Counter(terms).items():
                    if len(term) > 300:
                        continue
                    entries.append(
                        SimilarityIndexEntry(
                            organization_id=org,
                            document_id=document_id,
                            document_version_id=version_id,
                            pipeline_version=PIPELINE_VERSION,
                            model_version=INDEX_VERSION,
                            chunk_id=str(row.id),
                            index_version=INDEX_VERSION,
                            term_type=kind,
                            term=term,
                            term_frequency=count / max(1, len(terms)),
                        )
                    )
        self.db.add_all(entries)
        await self.db.flush()
        return chunks
