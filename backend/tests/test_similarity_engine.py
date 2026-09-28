from types import SimpleNamespace

from sqlalchemy import func, select
from app.modules.documents.models import Document, DocumentStatus

from app.modules.similarity.intelligence.benchmark import benchmark_retrieval
from app.modules.similarity.intelligence.contract import Candidate
from app.modules.similarity.intelligence.normalization import normalize_text
from app.modules.similarity.intelligence.verification import DeterministicVerifier
from app.modules.similarity.models import (
    DocumentChunk,
    SimilarityIndexEntry,
    SimilarityType,
)
from app.modules.similarity.service import InvertedTermRetriever, SimilarityService


def _candidate(text: str) -> Candidate:
    return Candidate(
        chunk_id="source-chunk",
        document_id="source-document",
        start_char=40,
        end_char=40 + len(text),
        text=text,
        normalized_text=normalize_text(text),
        retrieval_score=0.8,
        retrieval_methods=("lexical-inverted-index",),
        retrieval_scores={"lexical": 0.8, "ngram": 0.7},
        rank=1,
    )


def test_verifier_emits_concrete_match_without_plagiarism_claim():
    text = "The river basin supports diverse habitats and seasonal migration patterns."
    result = DeterministicVerifier().verify(text, _candidate(text))

    assert result is not None
    assert result.match_type is SimilarityType.EXACT
    assert result.target_span == (0, len(text))
    assert result.source_span == (40, 40 + len(text))
    assert any(
        "not a plagiarism" in limitation.lower() for limitation in result.limitations
    )


def test_unavailable_semantic_provider_does_not_emit_probable_paraphrase():
    result = DeterministicVerifier().verify(
        "A completely different sentence about a topic.",
        _candidate("An unrelated sentence with a different topic."),
    )

    assert result is None


def test_benchmark_records_bounds_and_resource_dimensions():
    benchmark = benchmark_retrieval(
        lambda query, limit: tuple(query for _ in range(min(limit, 2))),
        ["one", "two", "three"],
        corpus_chunks=100_000,
        candidate_bound=10,
    )

    assert benchmark.corpus_chunks == 100_000
    assert benchmark.candidate_bound == 10
    assert benchmark.queries == 3
    assert benchmark.elapsed_ms >= 0
    assert benchmark.peak_memory_bytes > 0
    assert benchmark.throughput_queries_per_second > 0


async def test_inverted_retriever_is_bounded_and_tenant_scoped(db_session):
    # Retrieval now also checks that the indexed document is accessible and
    # not archived. Seed real document rows instead of dangling index entries.
    for doc_id, org_id in (("source-document", "org-a"), ("other-document", "org-b")):
        db_session.add(
            Document(
                id=doc_id,
                organization_id=org_id,
                owner_id="owner",
                filename="source.txt",
                original_filename="source.txt",
                file_size=23,
                mime_type="text/plain",
                extension="txt",
                sha256_fingerprint="a" * 64,
                storage_path=f"test/{doc_id}",
                status=DocumentStatus.COMPLETED,
            )
        )
    await db_session.flush()
    source_chunk = DocumentChunk(
        document_id="source-document",
        organization_id="org-a",
        document_version_id="source-version",
        pipeline_version="similarity-retrieval-v2",
        model_version="chunker-v2",
        chunk_index=0,
        text="shared retrieval signal",
        normalized_text="shared retrieval signal",
        start_char=0,
        end_char=23,
        token_count=3,
        index_version="inverted-terms-v1",
        index_status="ACTIVE",
    )
    other_tenant_chunk = DocumentChunk(
        document_id="other-document",
        organization_id="org-b",
        document_version_id="other-version",
        pipeline_version="similarity-retrieval-v2",
        model_version="chunker-v2",
        chunk_index=0,
        text="shared retrieval signal",
        normalized_text="shared retrieval signal",
        start_char=0,
        end_char=23,
        token_count=3,
        index_version="inverted-terms-v1",
        index_status="ACTIVE",
    )
    db_session.add_all([source_chunk, other_tenant_chunk])
    await db_session.flush()
    db_session.add_all(
        [
            SimilarityIndexEntry(
                organization_id="org-a",
                document_version_id="source-version",
                pipeline_version="similarity-retrieval-v2",
                model_version="inverted-terms-v1",
                chunk_id=source_chunk.id,
                document_id=source_chunk.document_id,
                term="shared",
                term_type="token",
                term_frequency=1.0,
                index_version="inverted-terms-v1",
            ),
            SimilarityIndexEntry(
                organization_id="org-b",
                document_version_id="other-version",
                pipeline_version="similarity-retrieval-v2",
                model_version="inverted-terms-v1",
                chunk_id=other_tenant_chunk.id,
                document_id=other_tenant_chunk.document_id,
                term="shared",
                term_type="token",
                term_frequency=1.0,
                index_version="inverted-terms-v1",
            ),
        ]
    )
    await db_session.flush()

    candidates = await InvertedTermRetriever(db_session).retrieve(
        organization_id="org-a",
        target_document_id="target-document",
        normalized_text="shared signal",
        limit=1,
    )

    assert len(candidates) == 1
    assert candidates[0].document_id == "source-document"
    assert 0 < candidates[0].retrieval_score <= 1
    assert candidates[0].retrieval_scores["lexical"] > 0


async def test_similarity_index_redelivery_keeps_unchanged_terms(db_session):
    processed = SimpleNamespace(
        organization_id="org-idempotent",
        document_version_id="version-idempotent",
        pipeline_version="document-processing-v2",
    )
    text = (
        "Immutable document evidence remains reproducible across retries. " * 30
    ).strip()
    service = SimilarityService(db_session)

    await service._store_chunks("document-idempotent", text, processed)
    first_chunk_count = await db_session.scalar(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == "document-idempotent"
        )
    )
    first_entry_count = await db_session.scalar(
        select(func.count(SimilarityIndexEntry.id)).where(
            SimilarityIndexEntry.document_id == "document-idempotent"
        )
    )

    await service._store_chunks("document-idempotent", text, processed)
    second_chunk_count = await db_session.scalar(
        select(func.count(DocumentChunk.id)).where(
            DocumentChunk.document_id == "document-idempotent"
        )
    )
    second_entry_count = await db_session.scalar(
        select(func.count(SimilarityIndexEntry.id)).where(
            SimilarityIndexEntry.document_id == "document-idempotent"
        )
    )

    assert first_chunk_count == second_chunk_count
    assert first_entry_count == second_entry_count
    assert first_entry_count > 0
