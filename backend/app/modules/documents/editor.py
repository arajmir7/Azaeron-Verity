"""Transactional editor acceptance and restoration of immutable revisions."""

import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.core.config import settings
from app.core.queue import QueueUnavailable, enqueue_with_retry
from app.modules.aegiswrite.engine import EditorialChange, apply_editorial_changes
from app.modules.aegiswrite.models import AegisEdit
from app.modules.billing.entitlements import EntitlementService
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.documents.service import DocumentService
from app.modules.jobs.models import JobType
from app.modules.jobs.schemas import JobCreate
from app.modules.jobs.service import JobService
from app.modules.processing.service import DocumentProcessingService
from app.modules.uploads.service import UploadService


class EditorRevisionService:
    def __init__(self, db: AsyncSession, storage):
        self.db, self.storage = db, storage

    async def _context(
        self,
        document_id: str,
        organization_id: str,
        user_id: str,
        base_version_id: str,
        operation_id: str,
        fingerprint: str,
    ):
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(
                    Document.id == document_id,
                    Document.organization_id == organization_id,
                )
                .with_for_update(of=Document, key_share=True)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(404, "Document not found")
        await DocumentService(self.db)._require_mutation_access(document, user_id)
        previous = (
            await self.db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.operation_id == operation_id,
                )
            )
        ).scalar_one_or_none()
        if previous:
            if (
                previous.operation_fingerprint != fingerprint
                or previous.created_by_id != user_id
            ):
                raise HTTPException(
                    409, "This operation ID was already used for a different revision"
                )
            return document, previous, True
        if document.status == DocumentStatus.ARCHIVED:
            raise HTTPException(409, "An archived document cannot be revised")
        latest = (
            await self.db.execute(
                select(DocumentVersion)
                .where(
                    DocumentVersion.document_id == document_id,
                )
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None or str(latest.id) != base_version_id:
            raise HTTPException(
                409,
                "A newer version exists. Keep your draft and review the latest version before saving.",
            )
        return document, latest, False

    @staticmethod
    def fingerprint(payload: dict) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    async def save(
        self,
        document_id: str,
        organization_id: str,
        user_id: str,
        base_version_id: str,
        operation_id: str,
        text: str,
        edit_ids: list[str],
    ) -> DocumentVersion:
        await EntitlementService(self.db).require_write(organization_id, len(text))
        if not text.strip() or len(set(edit_ids)) != len(edit_ids):
            raise HTTPException(422, "Use nonempty text and distinct edit IDs")
        source_hash = hashlib.sha256(text.encode()).hexdigest()
        fingerprint = self.fingerprint(
            {
                "operation": "editor",
                "base": base_version_id,
                "source": source_hash,
                "edits": sorted(edit_ids),
            }
        )
        document, latest, replay = await self._context(
            document_id,
            organization_id,
            user_id,
            base_version_id,
            operation_id,
            fingerprint,
        )
        if replay:
            return latest
        edits = []
        if edit_ids:
            edits = list(
                (
                    await self.db.execute(
                        select(AegisEdit).where(
                            AegisEdit.id.in_(edit_ids),
                            AegisEdit.organization_id == organization_id,
                            AegisEdit.document_id == document_id,
                            AegisEdit.document_version_id == base_version_id,
                            AegisEdit.user_id == user_id,
                            AegisEdit.source_text_hash == source_hash,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(edits) != len(edit_ids):
                raise HTTPException(
                    409,
                    "Suggestions do not match this draft, actor and version; review again",
                )
            changes = [
                EditorialChange(
                    edit.edit_type,
                    edit.dimension,
                    edit.original_text,
                    edit.suggested_text,
                    edit.explanation,
                    edit.span_start,
                    edit.span_end,
                    {},
                )
                for edit in edits
            ]
            try:
                text = apply_editorial_changes(text, changes)
            except ValueError as error:
                raise HTTPException(
                    409,
                    "The candidate failed protected-text verification; review again",
                ) from error
        version = await self._persist(
            document,
            latest,
            user_id,
            operation_id,
            fingerprint,
            text.encode(),
            "txt",
            "text/plain",
            "editor_accept" if edits else "editor_save",
            (
                "Accepted selected editorial suggestions"
                if edits
                else "Saved working draft"
            ),
        )
        for edit in edits:
            edit.applied = True
            edit.applied_at = datetime.now(timezone.utc)
            edit.metadata_json = {
                **(edit.metadata_json or {}),
                "accepted_version_id": str(version.id),
            }
        await self.db.flush()
        return version

    async def restore(
        self,
        document_id: str,
        organization_id: str,
        user_id: str,
        base_version_id: str,
        source_version_id: str,
        operation_id: str,
    ) -> DocumentVersion:
        fingerprint = self.fingerprint(
            {
                "operation": "restore",
                "base": base_version_id,
                "source": source_version_id,
            }
        )
        document, latest, replay = await self._context(
            document_id,
            organization_id,
            user_id,
            base_version_id,
            operation_id,
            fingerprint,
        )
        if replay:
            return latest
        source = (
            await self.db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.id == source_version_id,
                )
            )
        ).scalar_one_or_none()
        if source is None:
            raise HTTPException(404, "Document version not found")
        content = await asyncio.to_thread(
            UploadService(self.storage).get_file_content, source.storage_path
        )
        if hashlib.sha256(content).hexdigest() != source.content_hash:
            raise HTTPException(409, "Stored version failed its integrity check")
        extension = source.storage_path.rsplit(".", 1)[-1].lower()
        media = {
            "txt": "text/plain",
            "md": "text/markdown",
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "html": "text/html",
        }
        if extension not in media:
            raise HTTPException(422, "Unsupported source format")
        return await self._persist(
            document,
            latest,
            user_id,
            operation_id,
            fingerprint,
            content,
            extension,
            media[extension],
            "restore",
            f"Restored version {source.version_number}",
        )

    async def _persist(
        self,
        document,
        latest,
        user_id,
        operation_id,
        fingerprint,
        content: bytes,
        extension: str,
        media_type: str,
        edit_type: str,
        summary: str,
    ):
        digest = hashlib.sha256(content).hexdigest()
        # Browser-signed upload URLs cannot address this immutable namespace.
        key = f"versions/{document.organization_id}/{document.id}/{operation_id}/{digest}.{extension}"
        from app.modules.privacy.storage import lock_object

        await lock_object(self.db, key)
        try:
            await asyncio.to_thread(
                self.storage.put_object,
                settings.MINIO_BUCKET,
                key,
                io.BytesIO(content),
                len(content),
                content_type=media_type,
            )
        except Exception as error:
            raise HTTPException(
                503, "Storage temporarily unavailable; your draft has not been saved"
            ) from error
        version = await DocumentService(self.db).create_version(
            str(document.id),
            str(document.organization_id),
            user_id,
            key,
            digest,
            summary,
            edit_type=edit_type,
            operation_id=operation_id,
            operation_fingerprint=fingerprint,
            lifecycle_state=(
                "FINAL" if latest.lifecycle_state == "FINAL" else "REVISION"
            ),
        )
        document.file_size, document.mime_type, document.extension = (
            len(content),
            media_type,
            extension,
        )
        # Make saved text immediately readable. The worker reuses this frozen parse.
        await DocumentProcessingService(self.db).process_document(
            document, content, str(version.id)
        )
        job = await JobService(self.db).create_job(
            JobCreate(
                job_type=JobType.DOCUMENT_PROCESSING,
                document_id=str(document.id),
                document_version_id=str(version.id),
                input_data={"storage_key": key, "document_version_id": str(version.id)},
            ),
            str(document.organization_id),
            user_id,
        )
        from app.workers.tasks import process_document

        try:
            task = enqueue_with_retry(
                process_document,
                (
                    str(job.id),
                    str(document.id),
                    key,
                    str(document.organization_id),
                    str(version.id),
                ),
            )
        except QueueUnavailable as error:
            raise HTTPException(
                503,
                "Processing queue unavailable; retain your draft and retry with the same operation ID",
            ) from error
        job.celery_task_id = task.id
        await self.db.flush()
        return version
