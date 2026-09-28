import hashlib
import uuid

from httpx import AsyncClient

from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.evidence.models import CanonicalEvidenceNodeType, EvidenceNodeType
from app.modules.evidence.report_service import EvidenceFirstReportService
from app.modules.evidence.service import EvidenceService
from app.modules.organizations.models import Organization


async def _document_fixture(db_session, prefix: str):
    organization_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    fingerprint = hashlib.sha256(f"{prefix}:{document_id}".encode()).hexdigest()
    db_session.add_all(
        [
            Organization(
                id=organization_id,
                name=f"{prefix} org",
                slug=f"{prefix}-{organization_id[:8]}",
            ),
            User(
                id=user_id,
                email=f"{prefix}-{organization_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            Document(
                id=document_id,
                organization_id=organization_id,
                owner_id=user_id,
                filename="report.txt",
                original_filename="report.txt",
                file_size=32,
                mime_type="text/plain",
                extension=".txt",
                sha256_fingerprint=fingerprint,
                storage_path=f"uploads/{document_id}/v1.txt",
                status=DocumentStatus.PROCESSING,
            ),
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                storage_path=f"uploads/{document_id}/v1.txt",
                sha256_fingerprint=fingerprint,
                content_hash=fingerprint,
                created_by_id=user_id,
                uploaded_by_id=user_id,
                lifecycle_state="DRAFT",
                change_summary="Initial version",
            ),
        ]
    )
    await db_session.flush()
    return organization_id, document_id, version_id


async def test_evidence_first_report_has_seven_dimensions_and_exact_highlight(
    db_session,
):
    organization_id, document_id, version_id = await _document_fixture(
        db_session, "report"
    )
    service = EvidenceService(db_session)
    signal = await service.add_node(
        document_id=document_id,
        document_version_id=version_id,
        node_type=EvidenceNodeType.DETECTION,
        canonical_type=CanonicalEvidenceNodeType.AI_SIGNAL,
        entity_id="signal-1",
        entity_type="ai_signal",
        source_id="signal-1",
        finding_type="ai_signal",
        title="AI signal",
        description="Observed statistical signal.",
        confidence=0.61,
        model_id="test-model",
        model_version="test-v1",
        pipeline_version="test-pipeline",
    )
    await service.add_finding(
        document_id=document_id,
        document_version_id=version_id,
        entity_id="finding-1",
        source_id="signal-1",
        title="Signal finding",
        explanation="The signal is traceable to its originating model output.",
        finding_type="ai_signal",
        derived_from=[str(signal.node_id)],
        confidence=0.61,
        span_start=2,
        span_end=12,
        span_text="exact span",
        model_id="test-model",
        model_version="test-v1",
        pipeline_version="test-pipeline",
        metadata={"segment_type": "sentence"},
    )

    report = await EvidenceFirstReportService(db_session).build(
        document_id, organization_id, version_id
    )
    dimensions = {item.key: item for item in report.dimensions}

    assert report.report_status == "PRODUCTION"
    assert set(dimensions) == {
        "originality",
        "similarity",
        "ai_writing_signals",
        "authorship_consistency",
        "citation_integrity",
        "source_quality",
        "provenance",
    }
    assert dimensions["ai_writing_signals"].status == "EXPERIMENTAL"
    assert dimensions["ai_writing_signals"].confidence == 0.61
    assert dimensions["ai_writing_signals"].confidence_reliability == "EXPERIMENTAL"
    assert dimensions["similarity"].status == "INSUFFICIENT_EVIDENCE"
    assert dimensions["provenance"].status == "PRODUCTION"
    assert len(report.highlights) == 1
    assert report.highlights[0].span_text == "exact span"
    assert report.highlights[0].span_start == 2
    assert report.highlights[0].segment_type == "sentence"
    assert not hasattr(report, "score")


async def test_evidence_first_report_does_not_invent_confidence(db_session):
    organization_id, document_id, version_id = await _document_fixture(
        db_session, "empty-report"
    )

    report = await EvidenceFirstReportService(db_session).build(
        document_id, organization_id, version_id
    )
    dimensions = {item.key: item for item in report.dimensions}

    assert dimensions["ai_writing_signals"].status == "INSUFFICIENT_EVIDENCE"
    assert dimensions["ai_writing_signals"].confidence is None
    assert dimensions["ai_writing_signals"].confidence_reliability == "UNAVAILABLE"
    assert dimensions["similarity"].confidence is None
    assert report.highlights == []


async def test_evidence_first_report_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/reports/documents/document")
    assert response.status_code == 401
