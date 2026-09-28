from datetime import datetime, timezone
import hashlib
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from httpx import AsyncClient

from app.modules.aegiswrite.engine import (
    analyze_editorial_changes,
    apply_editorial_changes,
)
from app.modules.aegiswrite.models import AegisEdit, EditType
from app.modules.aegiswrite.schemas import AegisRefineRequest
from app.modules.aegiswrite.service import AegisWriteService
from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.organizations.models import Membership, Organization, OrganizationRole


async def _fixture(db_session):
    organization_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    fingerprint = hashlib.sha256(document_id.encode()).hexdigest()
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
                name="Write Org",
                slug=f"write-{organization_id[:8]}",
            ),
            User(
                id=user_id,
                email=f"write-{organization_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            Document(
                id=document_id,
                organization_id=organization_id,
                owner_id=user_id,
                filename="draft.txt",
                original_filename="draft.txt",
                file_size=64,
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


def test_editorial_engine_returns_explainable_non_evasion_changes():
    source = (
        "It is important to note that the the result is due to the fact that it works."
    )
    changes = analyze_editorial_changes(
        source,
        {EditType.GRAMMAR, EditType.CLARITY, EditType.CONCISION},
    )
    assert changes
    assert all(change.original != change.revision for change in changes)
    assert all(change.reason for change in changes)
    revised = apply_editorial_changes(source, changes)
    assert "detector" not in revised.lower()
    assert "because" in revised


async def test_editorial_service_persists_lineage_and_decisions(db_session):
    organization_id, user_id, document_id, version_id = await _fixture(db_session)
    source = "In order to improve clarity, the the sentence is concise."
    service = AegisWriteService(db_session)

    run = await service.refine(
        document_id=document_id,
        organization_id=organization_id,
        user_id=user_id,
        text=source,
        document_version_id=version_id,
        edit_types=[EditType.GRAMMAR, EditType.CONCISION],
        preserve_voice=True,
    )

    assert run.revised_text != source
    assert run.edits
    assert all(edit.organization_id == organization_id for edit in run.edits)
    assert all(str(edit.document_version_id) == version_id for edit in run.edits)
    assert all(
        edit.original_text and edit.suggested_text and edit.explanation
        for edit in run.edits
    )
    assert all(edit.ai_generated is False for edit in run.edits)

    accepted = await service.apply_edit(
        str(run.edits[0].id), organization_id, user_id, True
    )
    assert accepted.applied is True
    history = await service.history(document_id, organization_id, version_id)
    assert len(history) == len(run.edits)

    assert await db_session.scalar(
        select(AegisEdit).where(AegisEdit.id == run.edits[0].id)
    )


def test_editorial_requests_reject_detector_specific_controls():
    with pytest.raises(ValidationError):
        AegisRefineRequest(
            document_id="doc",
            text="A draft.",
            detector_mode="undetectable",
        )


async def test_editorial_api_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/api/v1/aegiswrite/refine",
        json={"document_id": "document", "text": "A draft."},
    )
    assert response.status_code == 401
