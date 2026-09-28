"""Tenant-scoped persistence and audit orchestration for AZAERON WRITE."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.permissions import Permission, require_member_permission
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.aegiswrite.engine import (
    EDITORIAL_ENGINE_VERSION,
    EditorialChange,
    analyze_editorial_changes,
    apply_editorial_changes,
)
from app.modules.aegiswrite.models import AegisEdit, EditType
from app.modules.documents.models import Document, DocumentVersion

logger = get_logger(__name__)


@dataclass(frozen=True)
class EditorialRun:
    document: Document
    version: DocumentVersion
    original_text: str
    revised_text: str
    edits: list[AegisEdit]


class AegisWriteService:
    """Editorial assistant service with explicit tenant and version lineage."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _context(
        self,
        document_id: str,
        organization_id: str,
        document_version_id: str | None,
    ) -> tuple[Document, DocumentVersion]:
        document = (
            await self.db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if not document:
            raise ValueError("Document not found")
        if document_version_id:
            version = (
                await self.db.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == document_version_id,
                        DocumentVersion.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()
        else:
            version = (
                await self.db.execute(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.document_id == document_id,
                    )
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if not version:
            raise ValueError(
                "Writing assistance requires an immutable document version"
            )
        return document, version

    @staticmethod
    def _validate_span(
        text: str, span_start: int, span_end: int | None
    ) -> tuple[int, int]:
        end = len(text) if span_end is None else span_end
        if span_start < 0 or end < span_start or end > len(text):
            raise ValueError("Editorial span is outside the submitted text")
        return span_start, end

    async def _persist_changes(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        user_id: str,
        text: str,
        changes: Iterable[EditorialChange],
        preserve_voice: bool,
    ) -> list[AegisEdit]:
        source_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        persisted: list[AegisEdit] = []
        for change in changes:
            edit = AegisEdit(
                document_id=str(document.id),
                organization_id=str(document.organization_id),
                document_version_id=str(version.id),
                user_id=user_id,
                edit_type=change.edit_type,
                dimension=change.dimension,
                original_text=change.original,
                suggested_text=change.revision,
                explanation=change.reason,
                span_start=change.span_start,
                span_end=change.span_end,
                applied=False,
                ai_generated=False,
                preserve_voice=preserve_voice,
                engine_version=EDITORIAL_ENGINE_VERSION,
                source_text_hash=source_hash,
                metadata_json={**change.metadata, "provenance_preserved": True},
            )
            self.db.add(edit)
            persisted.append(edit)
        await self.db.flush()
        for edit in persisted:
            await self.db.refresh(edit)
        return persisted

    async def refine(
        self,
        *,
        document_id: str,
        organization_id: str,
        user_id: str,
        text: str,
        document_version_id: str | None,
        edit_types: list[EditType],
        preserve_voice: bool,
        locked_spans: Iterable[tuple[int, int]] = (),
    ) -> EditorialRun:
        await require_member_permission(
            self.db, organization_id, user_id, Permission.EDITORIAL_WRITE
        )
        document, version = await self._context(
            document_id, organization_id, document_version_id
        )
        locked_spans = tuple(locked_spans)
        changes = analyze_editorial_changes(
            text, set(edit_types), preserve_voice, locked_spans=locked_spans
        )
        revised = apply_editorial_changes(text, changes, locked_spans)
        edits = await self._persist_changes(
            document=document,
            version=version,
            user_id=user_id,
            text=text,
            changes=changes,
            preserve_voice=preserve_voice,
        )
        await AuditService(self.db).log(
            AuditAction.WRITING_REFINEMENT,
            resource_type="aegis_write",
            resource_id=str(document.id),
            details={
                "document_version_id": str(version.id),
                "edit_count": len(edits),
                "engine_version": EDITORIAL_ENGINE_VERSION,
                "preserve_voice": preserve_voice,
                "provenance_preserved": True,
            },
            user_id=user_id,
            organization_id=organization_id,
        )
        logger.info(
            "aegiswrite_refinement_completed",
            document_id=document_id,
            document_version_id=str(version.id),
            edit_count=len(edits),
            engine_version=EDITORIAL_ENGINE_VERSION,
        )
        return EditorialRun(document, version, text, revised, edits)

    async def suggest(
        self,
        *,
        document_id: str,
        organization_id: str,
        user_id: str,
        text: str,
        document_version_id: str | None,
        span_start: int,
        span_end: int | None,
        edit_types: list[EditType],
        preserve_voice: bool,
        locked_spans: Iterable[tuple[int, int]] = (),
    ) -> EditorialRun:
        await require_member_permission(
            self.db, organization_id, user_id, Permission.EDITORIAL_WRITE
        )
        document, version = await self._context(
            document_id, organization_id, document_version_id
        )
        start, end = self._validate_span(text, span_start, span_end)
        locked_spans = tuple(locked_spans)
        changes = analyze_editorial_changes(
            text,
            set(edit_types),
            preserve_voice,
            span_start=start,
            span_end=end,
            locked_spans=locked_spans,
        )
        revised = apply_editorial_changes(text, changes, locked_spans)
        edits = await self._persist_changes(
            document=document,
            version=version,
            user_id=user_id,
            text=text,
            changes=changes,
            preserve_voice=preserve_voice,
        )
        await AuditService(self.db).log(
            AuditAction.WRITING_SUGGESTIONS,
            resource_type="aegis_write",
            resource_id=str(document.id),
            details={
                "document_version_id": str(version.id),
                "edit_count": len(edits),
                "span": [start, end],
                "engine_version": EDITORIAL_ENGINE_VERSION,
                "preserve_voice": preserve_voice,
                "provenance_preserved": True,
            },
            user_id=user_id,
            organization_id=organization_id,
        )
        logger.info(
            "aegiswrite_suggestions_generated",
            document_id=document_id,
            document_version_id=str(version.id),
            edit_count=len(edits),
            span_start=start,
            span_end=end,
        )
        return EditorialRun(document, version, text, revised, edits)

    async def apply_edit(
        self,
        edit_id: str,
        organization_id: str,
        user_id: str,
        apply: bool,
    ) -> AegisEdit:
        await require_member_permission(
            self.db, organization_id, user_id, Permission.EDITORIAL_WRITE
        )
        edit = (
            await self.db.execute(
                select(AegisEdit).where(
                    AegisEdit.id == edit_id,
                    AegisEdit.organization_id == organization_id,
                    AegisEdit.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if not edit:
            raise ValueError("Edit not found")
        edit.applied = apply
        edit.applied_at = datetime.now(timezone.utc) if apply else None
        await AuditService(self.db).log(
            (
                AuditAction.WRITING_EDIT_APPLIED
                if apply
                else AuditAction.WRITING_EDIT_REJECTED
            ),
            resource_type="aegis_edit",
            resource_id=str(edit.id),
            details={
                "document_id": str(edit.document_id),
                "document_version_id": str(edit.document_version_id),
                "applied": apply,
                "engine_version": edit.engine_version,
            },
            user_id=user_id,
            organization_id=organization_id,
        )
        logger.info("aegiswrite_edit_decision", edit_id=str(edit.id), applied=apply)
        await self.db.flush()
        await self.db.refresh(edit)
        return edit

    async def history(
        self,
        document_id: str,
        organization_id: str,
        document_version_id: str | None = None,
    ) -> list[AegisEdit]:
        _, version = await self._context(
            document_id, organization_id, document_version_id
        )
        query = (
            select(AegisEdit)
            .where(
                AegisEdit.document_id == document_id,
                AegisEdit.organization_id == organization_id,
            )
            .order_by(AegisEdit.created_at.asc())
        )
        query = query.where(AegisEdit.document_version_id == str(version.id))
        return list((await self.db.execute(query)).scalars().all())
