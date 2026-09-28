import hashlib
import uuid

import pytest
from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.evidence.models import (
    CanonicalEvidenceNodeType,
    EvidenceEdgeType,
    EvidenceNodeType,
)
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
                filename="evidence.txt",
                original_filename="evidence.txt",
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
    return organization_id, user_id, document_id, version_id


async def test_graph_materialization_provides_roots_and_traceable_findings(db_session):
    organization_id, user_id, document_id, version_id = await _document_fixture(
        db_session, "graph"
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
    finding = await service.add_finding(
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
    )

    graph = await service.materialize_document_graph(
        document_id, organization_id, version_id
    )

    assert graph.complete is True
    assert graph.orphan_finding_node_ids == []
    assert {node.canonical_type for node in graph.nodes} >= {
        CanonicalEvidenceNodeType.DOCUMENT.value,
        CanonicalEvidenceNodeType.DOCUMENT_VERSION.value,
        CanonicalEvidenceNodeType.AI_SIGNAL.value,
        CanonicalEvidenceNodeType.FINDING.value,
    }
    finding_response = next(
        node for node in graph.nodes if node.entity_id == str(finding.entity_id)
    )
    assert finding_response.span_text == "exact span"
    assert finding_response.document_id == document_id
    assert finding_response.document_version_id == version_id
    assert any(
        edge.source_node_id == signal.node_id
        and edge.target_node_id == finding.node_id
        and edge.edge_type == EvidenceEdgeType.GENERATED_FINDING.value
        for edge in graph.edges
    )


async def test_graph_rejects_orphan_and_cross_tenant_edges(db_session):
    org_a, _, doc_a, version_a = await _document_fixture(db_session, "tenant-a")
    org_b, _, doc_b, version_b = await _document_fixture(db_session, "tenant-b")
    service = EvidenceService(db_session)
    node_a = await service.add_node(
        document_id=doc_a,
        document_version_id=version_a,
        node_type=EvidenceNodeType.DOCUMENT,
        canonical_type=CanonicalEvidenceNodeType.DOCUMENT,
        entity_id=doc_a,
        source_id=doc_a,
        title="A",
        description="A",
        confidence=1.0,
    )
    node_b = await service.add_node(
        document_id=doc_b,
        document_version_id=version_b,
        node_type=EvidenceNodeType.DOCUMENT,
        canonical_type=CanonicalEvidenceNodeType.DOCUMENT,
        entity_id=doc_b,
        source_id=doc_b,
        title="B",
        description="B",
        confidence=1.0,
    )

    with pytest.raises(ValueError, match="derived"):
        await service.add_finding(
            document_id=doc_a,
            document_version_id=version_a,
            title="orphan",
            explanation="orphan",
            finding_type="test",
            entity_id="orphan",
            derived_from=[],
            confidence=0.0,
        )
    with pytest.raises(ValueError, match="explanation"):
        await service.add_node(
            document_id=doc_a,
            document_version_id=version_a,
            node_type=EvidenceNodeType.DOCUMENT,
            canonical_type=CanonicalEvidenceNodeType.DOCUMENT,
            entity_id="no-explanation",
            title="Invalid",
            description="",
        )
    with pytest.raises(ValueError, match="cross organizations"):
        await service.add_edge(
            str(node_a.node_id),
            str(node_b.node_id),
            EvidenceEdgeType.CONTAINS,
            organization_id=org_a,
        )

    assert await db_session.scalar(
        select(type(node_a)).where(type(node_a).id == node_a.id)
    )


async def test_materialization_replay_has_bounded_reads_and_preserves_all_nodes(
    db_session,
):
    from sqlalchemy import event

    org, _, doc, version = await _document_fixture(db_session, "bounded")
    service = EvidenceService(db_session)
    for index in range(50):
        await service.add_node(
            document_id=doc,
            document_version_id=version,
            node_type=EvidenceNodeType.DETECTION,
            entity_id=f"signal-{index}",
            title="Fixture signal",
            description="Observed fixture",
            confidence=0.5,
        )
    reads = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(db_session.bind.sync_engine, "before_cursor_execute", capture)
    try:
        first = await service.materialize_document_graph(doc, org, version)
        initial_reads = len(reads)
        reads.clear()
        replay = await service.materialize_document_graph(doc, org, version)
        assert len(first.nodes) == 52
        assert first.model_dump() == replay.model_dump()
        assert initial_reads <= 40
        assert len(reads) <= 40
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", capture)


async def test_document_and_audit_lists_count_filtered_rows_without_graph_loading(
    db_session,
):
    from sqlalchemy import event
    from app.modules.documents.service import DocumentService
    from app.modules.audit.service import AuditService
    from app.modules.audit.models import AuditAction

    org, user, doc, _ = await _document_fixture(db_session, "list-bounds")
    await AuditService(db_session).log(
        AuditAction.DOCUMENT_UPLOADED,
        "document",
        doc,
        user_id=user,
        organization_id=org,
    )
    reads = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(db_session.bind.sync_engine, "before_cursor_execute", capture)
    try:
        items, total = await DocumentService(db_session).list_documents(
            org, page_size=1
        )
        assert total == 1 and len(items) == 1
        assert len(reads) == 2
        items, total = await DocumentService(db_session).list_documents(
            org, status=DocumentStatus.COMPLETED
        )
        assert total == 0 and items == []
        logs = await AuditService(db_session).get_logs(
            organization_id=org, action=AuditAction.JOB_CREATED
        )
        assert logs.total == 0 and logs.items == []
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", capture)
