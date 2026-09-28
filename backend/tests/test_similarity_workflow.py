"""Similarity workflow contracts through real services and the authenticated API."""

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.dependencies import get_current_active_user
from app.main import app
from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentVersion, DocumentStatus
from app.modules.organizations.models import Organization, Membership, OrganizationRole
from app.modules.processing.service import DocumentProcessingService
from app.modules.processing.models import ProcessedDocument
from app.modules.similarity.models import SimilarityAnalysis, SimilarityMatch
from app.modules.similarity.review import (
    ExclusionPolicy,
    TextAnnotations,
    reduce_matches,
)
from app.modules.similarity.report import SimilarityReportService
from app.modules.similarity.service import SimilarityService
from app.modules.similarity.intelligence.contract import Candidate
from app.modules.similarity.intelligence.normalization import normalize_text
from app.modules.similarity.intelligence.verification import DeterministicVerifier


async def identity(db, suffix=""):
    org = Organization(name="Similarity test", slug=str(uuid4()))
    user = User(
        email=f"similarity-{uuid4()}{suffix}@example.invalid",
        hashed_password="fixture-only",
    )
    db.add_all([org, user])
    await db.flush()
    return org, user


async def document(db, org, user, text, *, parent=None):
    digest = hashlib.sha256(text.encode()).hexdigest()
    doc = parent or Document(
        organization_id=str(org.id),
        owner_id=str(user.id),
        filename="evidence.txt",
        original_filename="evidence.txt",
        file_size=len(text.encode()),
        mime_type="text/plain",
        extension="txt",
        sha256_fingerprint=digest,
        storage_path=f"test/{uuid4()}.txt",
        status=DocumentStatus.COMPLETED,
    )
    if not parent:
        db.add(doc)
        await db.flush()
    number = (
        int(
            (
                await db.scalar(
                    select(func.count(DocumentVersion.id)).where(
                        DocumentVersion.document_id == doc.id
                    )
                )
            )
            or 0
        )
        + 1
    )
    version = DocumentVersion(
        document_id=str(doc.id),
        version_number=number,
        storage_path=f"test/{uuid4()}.txt",
        content_hash=digest,
        sha256_fingerprint=digest,
        created_by_id=str(user.id),
        uploaded_by_id=str(user.id),
    )
    db.add(version)
    await db.flush()
    processed = await DocumentProcessingService(db).process_document(
        doc, text.encode(), str(version.id)
    )
    return doc, version, processed


def evidence(text, start, end, source="source-v1"):
    return {
        "id": str(uuid4()),
        "source_document_version_id": source,
        "source_document_id": source + "-doc",
        "source_title": source,
        "source_content_hash": "a" * 64,
        "retrieved_at": "2026-09-13T00:00:00Z",
        "document_span_start": start,
        "document_span_end": end,
    }


def test_overlap_coverage_and_exclusions_use_word_union_not_sum():
    text = "One two three four five six seven eight nine ten."
    rows = [evidence(text, 0, len(text), "a"), evidence(text, 0, len(text), "b")]
    report = reduce_matches(text, rows, ExclusionPolicy())
    assert report["summary"]["percentage"] == 100
    assert report["summary"]["matched_words"] == 10
    assert sum(s["matched_words"] for s in report["sources"]) == 20
    assert (
        reduce_matches(text, rows, ExclusionPolicy(excluded_source_version_ids=["a"]))[
            "summary"
        ]["percentage"]
        == 100
    )
    assert (
        reduce_matches(
            text, rows, ExclusionPolicy(excluded_source_version_ids=["a", "b"])
        )["summary"]["percentage"]
        == 0
    )
    assert (
        reduce_matches(text, rows, ExclusionPolicy(min_match_words=12))["summary"][
            "percentage"
        ]
        == 0
    )
    assert ExclusionPolicy(excluded_source_version_ids=["b", "a", "a"]).fingerprint(
        "run"
    ) == ExclusionPolicy(excluded_source_version_ids=["a", "b"]).fingerprint("run")


def test_match_groups_quotes_citations_and_partial_exclusions():
    sentences = [
        "Unquoted material has five shared words here.",
        "Cited material has five shared words here (Smith, 2020).",
        "“Quoted material has five shared words here.”",
        "“Cited quoted material has five shared words here” (Jones, 2021).",
    ]
    text = "\n".join(sentences) + "\n\nReferences\nSmith, J. (2020). A source title."
    annotations = TextAnnotations(text)
    expected = [
        "UNCITED_UNQUOTED",
        "MISSING_QUOTATIONS",
        "MISSING_CITATIONS",
        "CITED_QUOTED",
    ]
    for sentence, group in zip(sentences, expected):
        start = text.index(sentence)
        end = start + sentence.index("here") + 4
        start += int(sentence.startswith("“"))
        assert annotations.classify(start, end)["group"] == group
    row = evidence(text, 0, len(text))
    whole = reduce_matches(text, [row], ExclusionPolicy(exclude_bibliography=False))
    excluded = reduce_matches(
        text, [row], ExclusionPolicy(exclude_quotes=True, exclude_cited=True)
    )
    assert (
        0 < excluded["summary"]["eligible_words"] < whole["summary"]["eligible_words"]
    )
    assert excluded["summary"]["percentage"] == 100
    only_quote = "“One two three four five six.”"
    empty = reduce_matches(
        only_quote,
        [evidence(only_quote, 1, len(only_quote) - 1)],
        ExclusionPolicy(exclude_quotes=True),
    )
    assert empty["summary"]["percentage"] is None


def test_token_verification_preserves_unicode_offsets_and_separate_blocks():
    source = "alpha beta gamma delta epsilon. Unrelated separator. river basin ecology supports seasonal migration."
    target = "🙂 Ａlpha beta gamma delta epsilon. Distinct interlude. river basin ecology supports seasonal migration."
    candidate = Candidate(
        "chunk",
        "source",
        40,
        40 + len(source),
        source,
        normalize_text(source),
        0.8,
        ("lexical",),
        {},
        1,
    )
    results = DeterministicVerifier().verify_all(target, candidate)
    assert len(results) == 2
    assert target[results[0].target_span[0] : results[0].target_span[1]].startswith(
        "Ａlpha"
    )
    for result in results:
        a, b = result.target_span
        c, d = result.source_span
        assert normalize_text(target[a:b]) == normalize_text(source[c - 40 : d - 40])
    assert (
        DeterministicVerifier().verify(
            "aaaa bbbb cccc dddd eeee",
            Candidate(
                "other",
                "other",
                0,
                24,
                "xxxx yyyy zzzz wwww vvvv",
                "xxxx yyyy zzzz wwww vvvv",
                1,
                (),
                {},
                1,
            ),
        )
        is None
    )


async def test_similarity_version_snapshot_provenance_idempotency_and_pagination(
    db_session, client
):
    org, user = await identity(db_session)
    shared = "River basins support diverse habitats and seasonal migration patterns across connected ecosystems"
    source, source_version, source_processed = await document(
        db_session, org, user, shared + ".\nAnother source paragraph remains unchanged."
    )
    await SimilarityService(db_session).analyze_similarity(
        str(source.id), source_processed
    )
    target_text = f"“{shared}” (Smith, 2020).\n\n{shared}.\n\nReferences\nSmith, J. (2020). Ecology."
    target, version, processed = await document(db_session, org, user, target_text)
    assert processed.paragraph_count == 3
    assert "\n\nReferences\n" in processed.cleaned_text
    service = SimilarityService(db_session)
    first = await service.analyze_similarity(str(target.id), processed)
    again = await service.analyze_similarity(str(target.id), processed)
    assert first and [m.id for m in first] == [m.id for m in again]
    assert len(first) >= 2
    for match in first:
        assert match.source_document_version_id == source_version.id
        assert (
            processed.cleaned_text[match.document_span_start : match.document_span_end]
            == match.matched_text
        )
        assert (
            source_processed.cleaned_text[
                match.source_span_start : match.source_span_end
            ]
            == match.source_text
        )
        assert match.evidence_id
        assert (
            match.metadata_json["source_content_hash"]
            == source_version.sha256_fingerprint
        )
    user.current_organization_id = str(org.id)
    app.dependency_overrides[get_current_active_user] = lambda: user
    await db_session.commit()
    db_session.add(
        Membership(
            user_id=str(user.id),
            organization_id=str(org.id),
            role=OrganizationRole.OWNER,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    prefix = f"/api/v1/similarity/documents/{target.id}"
    params = {"document_version_id": version.id, "page_size": 1}
    page1 = await client.get(prefix + "/analysis", params=params)
    assert page1.status_code == 200, page1.text
    report = page1.json()
    rerun = await client.post(
        prefix + "/analysis", params={"document_version_id": version.id}
    )
    assert rerun.status_code == 200
    assert rerun.json()["analysis_id"] == report["analysis_id"]
    assert report["corpus"][0]["state"] == "PRIVATE_WORKSPACE"
    assert report["corpus"][1]["searched"] is False
    assert report["corpus"][2]["state"] == "UNAVAILABLE"
    assert report["summary"]["percentage"] > 0
    assert len(report["matches"]["items"]) == 1
    page2 = (
        await client.get(prefix + "/analysis", params={**params, "page": 2})
    ).json()
    assert page2["matches"]["items"][0]["id"] != report["matches"]["items"][0]["id"]
    assert page2["summary"] == report["summary"]
    match_id = report["matches"]["items"][0]["id"]
    detail = await client.get(prefix + f"/matches/{match_id}", params=params)
    assert detail.status_code == 200
    assert detail.json()["evidence_node_id"]
    assert (
        await client.get(prefix + "/analysis", params={**params, "page_size": 101})
    ).status_code == 422
    _, v2, p2 = await document(
        db_session,
        org,
        user,
        "A new independent revision discusses distinct geology and sediment measurements without matching phrases.",
        parent=target,
    )
    await service.analyze_similarity(str(target.id), p2)
    assert (
        await db_session.scalar(
            select(func.count(ProcessedDocument.id)).where(
                ProcessedDocument.document_id == target.id
            )
        )
        == 2
    )
    await db_session.commit()
    latest = (await client.get(prefix + "/analysis")).json()
    assert latest["document_version_id"] == v2.id
    assert latest["summary"]["percentage"] == 0
    assert (
        await client.get(
            prefix + f"/matches/{match_id}", params={"document_version_id": v2.id}
        )
    ).status_code == 404
    historical = (await client.get(prefix + "/analysis", params=params)).json()
    assert historical["summary"] == report["summary"]
    assert historical["exclusions_hash"] == report["exclusions_hash"]
    foreign_org, foreign_user = await identity(db_session, "foreign")
    foreign_doc, foreign_version, _ = await document(
        db_session, foreign_org, foreign_user, shared
    )
    await db_session.commit()
    assert (
        await client.get(f"/api/v1/similarity/documents/{foreign_doc.id}/analysis")
    ).status_code == 404
    assert (
        await client.get(
            prefix + "/analysis", params={"document_version_id": foreign_version.id}
        )
    ).status_code == 404
    foreign_user.current_organization_id = str(org.id)
    db_session.add(
        Membership(
            user_id=str(foreign_user.id),
            organization_id=str(org.id),
            role=OrganizationRole.AUDITOR,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db_session.commit()
    app.dependency_overrides[get_current_active_user] = lambda: foreign_user
    assert (await client.get(prefix + "/analysis")).status_code == 200
    assert (await client.post(prefix + "/analysis")).status_code == 403


async def test_missing_corpus_is_unavailable_and_stays_frozen(db_session):
    org, user = await identity(db_session)
    doc, version, processed = await document(
        db_session,
        org,
        user,
        "An isolated original text has enough words to create a meaningful similarity snapshot.",
    )
    report = SimilarityReportService(db_session)
    untested = await report.build(
        str(doc.id), str(org.id), str(version.id), ExclusionPolicy()
    )
    assert untested.analysis_state == "NOT_ANALYZED"
    assert untested.summary.percentage is None
    await SimilarityService(db_session).analyze_similarity(str(doc.id), processed)
    empty = await report.build(
        str(doc.id), str(org.id), str(version.id), ExclusionPolicy()
    )
    assert empty.analysis_state == "READY"
    assert empty.corpus[0]["state"] == "UNAVAILABLE"
    assert empty.summary.percentage is None
    assert await db_session.scalar(select(func.count(SimilarityAnalysis.id))) == 1
    source, _, source_processed = await document(
        db_session, org, user, processed.cleaned_text + " Additional source context."
    )
    await SimilarityService(db_session).analyze_similarity(
        str(source.id), source_processed
    )
    await SimilarityService(db_session).analyze_similarity(str(doc.id), processed)
    frozen = await report.build(
        str(doc.id), str(org.id), str(version.id), ExclusionPolicy()
    )
    assert frozen.analysis_id == empty.analysis_id
    assert frozen.corpus[0]["indexed_versions"] == 0
    assert frozen.summary.percentage is None
    assert frozen.exclusions_hash == empty.exclusions_hash


async def test_search_bounds_are_disclosed_instead_of_claiming_exhaustive_coverage(
    db_session, monkeypatch
):
    org, user = await identity(db_session)
    shared = "River basins support diverse habitats and seasonal migration patterns across connected ecosystems."
    source, _, source_processed = await document(db_session, org, user, shared)
    await SimilarityService(db_session).analyze_similarity(
        str(source.id), source_processed
    )
    target, version, processed = await document(
        db_session,
        org,
        user,
        "An unrelated field survey discusses sediment chemistry and laboratory measurements. "
        * 20
        + shared,
    )
    monkeypatch.setattr("app.modules.similarity.service.MAX_TARGET_CHUNKS", 1)
    await SimilarityService(db_session).analyze_similarity(str(target.id), processed)
    report = await SimilarityReportService(db_session).build(
        str(target.id), str(org.id), str(version.id), ExclusionPolicy()
    )
    assert report.analysis_state == "BOUNDED"
    assert report.summary.percentage == 0
    assert any("lower bound" in limitation for limitation in report.limitations)


async def test_similarity_api_requires_authentication(client):
    for path in ("analysis", "matches", "matches/finding?document_version_id=version"):
        assert (
            await client.get("/api/v1/similarity/documents/document/" + path)
        ).status_code == 401
