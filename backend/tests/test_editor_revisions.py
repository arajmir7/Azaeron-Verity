"""Durable editor candidates, retry identities, conflicts and failure safety."""

from datetime import datetime, timezone
import hashlib
import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.core.queue import QueueUnavailable
from app.modules.auth.models import User
from app.modules.organizations.models import Organization, Membership, OrganizationRole
from app.modules.documents.models import DocumentVersion
from app.modules.documents.schemas import DocumentCreate
from app.modules.documents.service import DocumentService
from app.modules.documents.editor import EditorRevisionService
from app.modules.processing.models import ProcessedDocument
from app.modules.aegiswrite.models import EditType
from app.modules.aegiswrite.service import AegisWriteService


class MemoryStorage:
    def __init__(self):
        self.objects = {}
        self.fail = False

    def put_object(self, bucket, key, data, size, **kwargs):
        if self.fail:
            raise OSError("unavailable")
        self.objects[key] = data.read(size)

    def get_object(self, bucket, key):
        value = io.BytesIO(self.objects[key])
        value.release_conn = lambda: None
        return value


async def seed_editor(db, monkeypatch):
    org, user = Organization(name="Editor fixture", slug=str(uuid4())), User(
        email=f"{uuid4()}@example.com", hashed_password="fixture-only"
    )
    db.add_all([org, user])
    await db.flush()
    db.add(
        Membership(
            user_id=str(user.id),
            organization_id=str(org.id),
            role=OrganizationRole.OWNER,
            is_active=True,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    source = "In order to explain the finding, the the report uses clear language."
    digest = hashlib.sha256(source.encode()).hexdigest()
    doc = await DocumentService(db).create_document(
        DocumentCreate(
            filename="draft.txt",
            original_filename="draft.txt",
            file_size=len(source.encode()),
            mime_type="text/plain",
            extension="txt",
            sha256_fingerprint=digest,
            storage_path=f"fixture/{uuid4()}.txt",
        ),
        str(user.id),
        str(org.id),
    )
    version = (
        await db.execute(
            select(DocumentVersion).where(DocumentVersion.document_id == str(doc.id))
        )
    ).scalar_one()
    storage = MemoryStorage()
    storage.objects[version.storage_path] = source.encode()
    monkeypatch.setattr(
        "app.modules.documents.editor.enqueue_with_retry",
        lambda *args: SimpleNamespace(id=str(uuid4())),
    )
    return org, user, doc, version, storage, source


async def test_selective_acceptance_is_durable_idempotent_and_version_bound(
    db_session, monkeypatch
):
    org, user, doc, original, storage, source = await seed_editor(
        db_session, monkeypatch
    )
    run = await AegisWriteService(db_session).refine(
        document_id=str(doc.id),
        organization_id=str(org.id),
        user_id=str(user.id),
        text=source,
        document_version_id=str(original.id),
        edit_types=[EditType.GRAMMAR, EditType.CONCISION],
        preserve_voice=True,
    )
    assert len(run.edits) >= 2
    service = EditorRevisionService(db_session, storage)
    identity = str(uuid4())
    args = (
        str(doc.id),
        str(org.id),
        str(user.id),
        str(original.id),
        identity,
        source,
        [str(run.edits[0].id)],
    )
    accepted = await service.save(*args)
    assert accepted.version_number == 2 and accepted.previous_version_id == original.id
    assert run.edits[0].metadata_json["accepted_version_id"] == accepted.id
    parsed = (
        await db_session.execute(
            select(ProcessedDocument).where(
                ProcessedDocument.document_version_id == accepted.id
            )
        )
    ).scalar_one()
    assert parsed.cleaned_text != source and parsed.cleaned_text != run.revised_text
    assert storage.objects[accepted.storage_path].decode() == parsed.cleaned_text
    assert (await service.save(*args)).id == accepted.id
    assert await db_session.scalar(select(func.count(DocumentVersion.id))) == 2
    with pytest.raises(HTTPException) as conflict:
        await service.save(*args[:4], identity, source + " Changed.", [])
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as stale:
        await service.save(*args[:4], str(uuid4()), "A different draft.", [])
    assert stale.value.status_code == 409
    restored = await service.restore(
        str(doc.id),
        str(org.id),
        str(user.id),
        str(accepted.id),
        str(original.id),
        str(uuid4()),
    )
    assert restored.version_number == 3 and restored.previous_version_id == accepted.id
    assert storage.objects[restored.storage_path].decode() == source
    assert original.content_hash == hashlib.sha256(source.encode()).hexdigest()
    assert (await service.save(*args)).id == accepted.id


async def test_foreign_or_stale_suggestions_cannot_be_accepted(db_session, monkeypatch):
    org, user, doc, original, storage, source = await seed_editor(
        db_session, monkeypatch
    )
    run = await AegisWriteService(db_session).refine(
        document_id=str(doc.id),
        organization_id=str(org.id),
        user_id=str(user.id),
        text=source,
        document_version_id=str(original.id),
        edit_types=[EditType.GRAMMAR],
        preserve_voice=True,
    )
    service = EditorRevisionService(db_session, storage)
    for text, ids in [
        (source + "changed", [str(run.edits[0].id)]),
        (source, [str(uuid4())]),
    ]:
        with pytest.raises(HTTPException) as denied:
            await service.save(
                str(doc.id),
                str(org.id),
                str(user.id),
                str(original.id),
                str(uuid4()),
                text,
                ids,
            )
        assert denied.value.status_code == 409
    with pytest.raises(HTTPException) as foreign:
        await service.restore(
            str(doc.id),
            str(uuid4()),
            str(user.id),
            str(original.id),
            str(original.id),
            str(uuid4()),
        )
    assert foreign.value.status_code == 404
    assert await db_session.scalar(select(func.count(DocumentVersion.id))) == 1


async def test_storage_or_queue_failure_preserves_accepted_version(
    db_session, monkeypatch
):
    org, user, doc, original, storage, source = await seed_editor(
        db_session, monkeypatch
    )
    service = EditorRevisionService(db_session, storage)
    args = (
        str(doc.id),
        str(org.id),
        str(user.id),
        str(original.id),
        str(uuid4()),
        source + " A new sentence.",
        [],
    )
    storage.fail = True
    with pytest.raises(HTTPException) as unavailable:
        await service.save(*args)
    assert unavailable.value.status_code == 503
    assert await db_session.scalar(select(func.count(DocumentVersion.id))) == 1
    storage.fail = False

    def reject_queue(*args):
        raise QueueUnavailable("unavailable")

    monkeypatch.setattr("app.modules.documents.editor.enqueue_with_retry", reject_queue)
    with pytest.raises(HTTPException) as unavailable:
        async with db_session.begin_nested():
            await service.save(*args)
    assert unavailable.value.status_code == 503
    assert await db_session.scalar(select(func.count(DocumentVersion.id))) == 1


async def test_restore_rejects_changed_storage_bytes(db_session, monkeypatch):
    org, user, doc, original, storage, source = await seed_editor(
        db_session, monkeypatch
    )
    storage.objects[original.storage_path] = b"tampered"
    with pytest.raises(HTTPException) as rejected:
        await EditorRevisionService(db_session, storage).restore(
            str(doc.id),
            str(org.id),
            str(user.id),
            str(original.id),
            str(original.id),
            str(uuid4()),
        )
    assert rejected.value.status_code == 409
    assert await db_session.scalar(select(func.count(DocumentVersion.id))) == 1
