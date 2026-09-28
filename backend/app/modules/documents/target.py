"""Resolve one authorized immutable analysis target; never fall back to results."""

from dataclasses import dataclass
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import lazyload
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentVersion
from app.modules.processing.models import ProcessedDocument


@dataclass(frozen=True)
class AnalysisTarget:
    organization_id: str
    document: Document
    version: DocumentVersion

    @classmethod
    async def resolve(
        cls,
        db: AsyncSession,
        organization_id: str | None,
        document_id: str,
        version_id: str | None = None,
        *,
        lock: bool = False
    ) -> "AnalysisTarget":
        document_query = (
            select(Document)
            .options(lazyload("*"))
            .where(
                Document.id == document_id,
                Document.organization_id == organization_id,
            )
        )
        if lock:
            # NO KEY UPDATE still serializes writers, while allowing foreign-key
            # readers from concurrent similarity analyses of other documents.
            document_query = document_query.with_for_update(of=Document, key_share=True)
        document = (
            (await db.execute(document_query)).scalar_one_or_none()
            if organization_id
            else None
        )
        if document is None:
            raise HTTPException(404, "Document not found")
        query = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id
        )
        if version_id:
            query = query.where(DocumentVersion.id == version_id)
        query = query.order_by(DocumentVersion.version_number.desc()).limit(1)
        if lock:
            query = query.with_for_update(of=DocumentVersion, key_share=True)
        version = (await db.execute(query)).scalar_one_or_none()
        if version is None:
            raise HTTPException(404, "Document version not found")
        return cls(str(organization_id), document, version)

    async def processed(self, db: AsyncSession) -> ProcessedDocument:
        processed = (
            await db.execute(
                select(ProcessedDocument).where(
                    ProcessedDocument.organization_id == self.organization_id,
                    ProcessedDocument.document_id == str(self.document.id),
                    ProcessedDocument.document_version_id == str(self.version.id),
                )
            )
        ).scalar_one_or_none()
        if processed is None:
            raise HTTPException(
                409, "This document version has not finished text extraction"
            )
        return processed


def require_processed_target(
    document_id: str,
    processed: ProcessedDocument,
    organization_id: str | None = None,
    version_id: str | None = None,
) -> None:
    if (
        str(processed.document_id) != document_id
        or not processed.organization_id
        or not processed.document_version_id
        or (organization_id and str(processed.organization_id) != organization_id)
        or (version_id and str(processed.document_version_id) != version_id)
    ):
        raise ValueError(
            "Analysis input does not match its organization/document/version target"
        )
