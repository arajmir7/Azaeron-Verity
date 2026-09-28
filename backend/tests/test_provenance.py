import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.documents.service import DocumentService
from app.modules.governance.models import AnalysisRun, AnalysisRunStatus
from app.modules.organizations.models import Membership, Organization, OrganizationRole
from app.modules.provenance.models import ProvenanceEventType
from app.modules.provenance.models import ProvenanceEvent
from app.modules.provenance.service import ProvenanceService


async def test_provenance_timeline_and_export_are_versioned_and_reproducible(
    db_session,
):
    organization_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    first_hash = hashlib.sha256(b"version-one").hexdigest()
    second_hash = hashlib.sha256(b"version-two").hexdigest()

    db_session.add_all(
        [
            Membership(
                user_id=user_id,
                organization_id=organization_id,
                role=OrganizationRole.OWNER,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            ),
            Organization(
                id=organization_id,
                name="Provenance test org",
                slug=f"provenance-{organization_id[:8]}",
            ),
            User(
                id=user_id,
                email=f"provenance-{organization_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            Document(
                id=document_id,
                organization_id=organization_id,
                owner_id=user_id,
                filename="draft.txt",
                original_filename="draft.txt",
                file_size=11,
                mime_type="text/plain",
                extension=".txt",
                sha256_fingerprint=first_hash,
                storage_path=f"uploads/{document_id}/v1.txt",
                status=DocumentStatus.PROCESSING,
            ),
            DocumentVersion(
                id=version_id,
                document_id=document_id,
                version_number=1,
                storage_path=f"uploads/{document_id}/v1.txt",
                sha256_fingerprint=first_hash,
                content_hash=first_hash,
                created_by_id=user_id,
                uploaded_by_id=user_id,
                change_summary="Initial uploaded version",
                edit_type="upload",
                lifecycle_state="DRAFT",
            ),
        ]
    )
    await db_session.flush()

    provenance = ProvenanceService(db_session)
    await provenance.record_event(
        document_id,
        ProvenanceEventType.CREATED,
        user_id=user_id,
        description="Initial version recorded",
        sha256_after=first_hash,
        document_version_id=version_id,
    )

    version = await DocumentService(db_session).create_version(
        document_id=document_id,
        org_id=organization_id,
        user_id=user_id,
        storage_path=f"uploads/{document_id}/v2.txt",
        content_hash=second_hash,
        change_summary="Reviewed and revised",
    )
    version_two_id = str(version.id)
    await DocumentService(db_session).transition_version(
        document_id, organization_id, version_two_id, user_id, "FINAL"
    )

    run = AnalysisRun(
        organization_id=organization_id,
        document_id=document_id,
        document_version_id=version_two_id,
        model_id="provenance-test-model",
        model_version="1",
        pipeline_version="test-pipeline-v1",
        status=AnalysisRunStatus.COMPLETED,
        input_fingerprint=second_hash,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    await db_session.flush()
    await provenance.record_event(
        document_id,
        ProvenanceEventType.ANALYSIS_RUN,
        user_id=user_id,
        description="Analysis completed",
        sha256_after=second_hash,
        document_version_id=version_two_id,
        analysis_run_id=str(run.id),
    )

    timeline = await provenance.build_timeline(document_id, organization_id)
    assert [item["lifecycle_state"] for item in timeline["versions"]] == [
        "DRAFT",
        "FINAL",
    ]
    assert (
        timeline["versions"][1]["previous_version_id"] == timeline["versions"][0]["id"]
    )
    assert timeline["versions"][1]["content_hash"] == second_hash
    assert timeline["analysis_runs"][0]["document_version_id"] == version_two_id
    assert any(
        event["event_type"] == "analysis_run"
        and event["analysis_run_id"] == str(run.id)
        for event in timeline["provenance_events"]
    )

    export, payload = await provenance.export_history(
        document_id, organization_id, user_id
    )
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert export.document_version_id == version_two_id
    assert export.export_hash == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert payload["export"]["document_version_id"] == version_two_id


async def test_archiving_preserves_document_history(db_session):
    organization_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    fingerprint = hashlib.sha256(b"archive-me").hexdigest()
    db_session.add_all(
        [
            Membership(
                user_id=user_id,
                organization_id=organization_id,
                role=OrganizationRole.OWNER,
                is_active=True,
                joined_at=datetime.now(timezone.utc),
            ),
            Organization(
                id=organization_id,
                name="Archive test org",
                slug=f"archive-{organization_id[:8]}",
            ),
            User(
                id=user_id,
                email=f"archive-{organization_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            Document(
                id=document_id,
                organization_id=organization_id,
                owner_id=user_id,
                filename="archive.txt",
                original_filename="archive.txt",
                file_size=10,
                mime_type="text/plain",
                extension=".txt",
                sha256_fingerprint=fingerprint,
                storage_path=f"uploads/{document_id}/v1.txt",
                status=DocumentStatus.COMPLETED,
            ),
            DocumentVersion(
                document_id=document_id,
                version_number=1,
                storage_path=f"uploads/{document_id}/v1.txt",
                sha256_fingerprint=fingerprint,
                content_hash=fingerprint,
                created_by_id=user_id,
                uploaded_by_id=user_id,
                lifecycle_state="DRAFT",
            ),
        ]
    )
    await db_session.flush()

    assert await DocumentService(db_session).delete_document(
        document_id, organization_id, user_id
    )
    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    version = (
        await db_session.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == document_id)
        )
    ).scalar_one()
    event = (
        await db_session.execute(
            select(ProvenanceEvent).where(ProvenanceEvent.document_id == document_id)
        )
    ).scalar_one()
    assert document.status == DocumentStatus.ARCHIVED
    assert version.content_hash == fingerprint
    assert event.event_type == ProvenanceEventType.EDITED
    assert event.metadata_json["operation"] == "archive"
