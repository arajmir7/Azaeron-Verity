"""Regression tests for document mutation authorization at the service boundary."""

from datetime import datetime, timezone
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.documents.service import DocumentService
from app.modules.organizations.models import Membership, Organization, OrganizationRole
from app.modules.provenance.models import ProvenanceEvent


async def _fixture(db_session):
    org_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    db_session.add_all(
        [
            Organization(id=org_id, name="Mutation Org", slug=f"mutation-{org_id[:8]}"),
            User(
                id=owner_id,
                email=f"owner-{org_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            User(
                id=member_id,
                email=f"member-{org_id[:8]}@example.invalid",
                hashed_password="not-used",
            ),
            Membership(
                user_id=owner_id,
                organization_id=org_id,
                role=OrganizationRole.OWNER,
                is_active=True,
                joined_at=now,
            ),
            Membership(
                user_id=member_id,
                organization_id=org_id,
                role=OrganizationRole.STUDENT,
                is_active=True,
                joined_at=now,
            ),
            Document(
                id=document_id,
                organization_id=org_id,
                owner_id=owner_id,
                filename="document.txt",
                original_filename="document.txt",
                file_size=4,
                mime_type="text/plain",
                extension="txt",
                sha256_fingerprint="0" * 64,
                storage_path=f"uploads/{org_id}/{owner_id}/document.txt",
                status=DocumentStatus.QUEUED,
            ),
            DocumentVersion(
                id=str(uuid.uuid4()),
                document_id=document_id,
                version_number=1,
                storage_path=f"uploads/{org_id}/{owner_id}/document.txt",
                uploaded_at=now,
                uploaded_by_id=owner_id,
                content_hash="0" * 64,
                sha256_fingerprint="0" * 64,
                created_by_id=owner_id,
                lifecycle_state="DRAFT",
                change_summary="Initial",
                edit_type="upload",
            ),
        ]
    )
    await db_session.flush()
    return org_id, owner_id, member_id, document_id


@pytest.mark.asyncio
async def test_non_owner_cannot_archive_another_member_document(db_session):
    org_id, _, member_id, document_id = await _fixture(db_session)

    with pytest.raises(HTTPException) as error:
        await DocumentService(db_session).delete_document(
            document_id, org_id, member_id
        )
    assert error.value.status_code == 403

    document = await DocumentService(db_session).get_document(document_id, org_id)
    assert document.status == DocumentStatus.QUEUED


@pytest.mark.asyncio
async def test_rename_is_tenant_scoped_owner_only_and_retry_safe(db_session):
    org_id, owner_id, member_id, document_id = await _fixture(db_session)
    service = DocumentService(db_session)
    with pytest.raises(HTTPException) as denied:
        await service.rename_document(
            document_id, org_id, member_id, "Unauthorized", None
        )
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as hidden:
        await service.rename_document(
            document_id, str(uuid.uuid4()), owner_id, "Hidden", None
        )
    assert hidden.value.status_code == 404

    renamed = await service.rename_document(
        document_id, org_id, owner_id, "Research draft", None
    )
    assert renamed.title == "Research draft"
    count = await db_session.scalar(
        select(func.count(ProvenanceEvent.id)).where(
            ProvenanceEvent.document_id == document_id
        )
    )
    repeated = await service.rename_document(
        document_id, org_id, owner_id, "Research draft", None
    )
    assert repeated.title == "Research draft"
    assert (
        await db_session.scalar(
            select(func.count(ProvenanceEvent.id)).where(
                ProvenanceEvent.document_id == document_id
            )
        )
        == count
    )
    with pytest.raises(HTTPException) as conflict:
        await service.rename_document(document_id, org_id, owner_id, "Stale", None)
    assert conflict.value.status_code == 409
    assert (await service.get_document(document_id, org_id)).title == "Research draft"


@pytest.mark.asyncio
async def test_non_owner_cannot_append_or_transition_another_member_document(
    db_session,
):
    org_id, _, member_id, document_id = await _fixture(db_session)

    with pytest.raises(HTTPException) as version_error:
        await DocumentService(db_session).create_version(
            document_id=document_id,
            org_id=org_id,
            user_id=member_id,
            storage_path=f"uploads/{org_id}/{member_id}/revision.txt",
            content_hash="1" * 64,
            change_summary="unauthorized revision",
        )
    assert version_error.value.status_code == 403

    version_id = (
        await db_session.execute(
            select(DocumentVersion.id).where(DocumentVersion.document_id == document_id)
        )
    ).scalar_one()
    with pytest.raises(HTTPException) as lifecycle_error:
        await DocumentService(db_session).transition_version(
            document_id,
            org_id,
            str(version_id),
            member_id,
            "REVISION",
        )
    assert lifecycle_error.value.status_code == 403


@pytest.mark.parametrize(
    "role,active",
    [
        (OrganizationRole.OWNER, False),
        (OrganizationRole.REVIEWER, True),
        (OrganizationRole.AUDITOR, True),
    ],
)
async def test_document_ownership_does_not_bypass_current_membership(
    db_session, role, active
):
    org_id, owner_id, _, document_id = await _fixture(db_session)
    membership = (
        await db_session.execute(
            select(Membership).where(
                Membership.user_id == owner_id,
                Membership.organization_id == org_id,
            )
        )
    ).scalar_one()
    membership.role, membership.is_active = role, active
    await db_session.flush()
    with pytest.raises(HTTPException) as denied:
        await DocumentService(db_session).delete_document(document_id, org_id, owner_id)
    assert denied.value.status_code == 403
    document = await DocumentService(db_session).get_document(document_id, org_id)
    assert document.status == DocumentStatus.QUEUED
