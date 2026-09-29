"""AZAERON document service."""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import lazyload
from fastapi import HTTPException, status

from app.modules.documents.models import (
    Document,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionLifecycle,
)
from app.modules.documents.schemas import DocumentCreate
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction
from app.modules.provenance.models import ProvenanceEventType
from app.modules.organizations.models import Membership, OrganizationRole
from app.core.logging import get_logger
from app.core.permissions import Permission, require_member_permission

logger = get_logger(__name__)


class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def create_document(
        self, doc_data: DocumentCreate, owner_id: str, org_id: str
    ) -> Document:
        await require_member_permission(
            self.db, org_id, owner_id, Permission.DOCUMENT_WRITE
        )
        doc = Document(
            organization_id=org_id,
            owner_id=owner_id,
            title=doc_data.title or doc_data.original_filename,
            filename=doc_data.filename,
            original_filename=doc_data.original_filename,
            file_size=doc_data.file_size,
            mime_type=doc_data.mime_type,
            extension=doc_data.extension,
            sha256_fingerprint=doc_data.sha256_fingerprint,
            storage_path=doc_data.storage_path,
            status=DocumentStatus.PENDING,
            uploaded_at=datetime.now(timezone.utc),
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)
        # Freeze the uploaded object as version one. Analysis must always be
        # traceable to an immutable input rather than a mutable document row.
        self.db.add(
            DocumentVersion(
                document_id=str(doc.id),
                version_number=1,
                storage_path=doc.storage_path,
                uploaded_at=doc.uploaded_at,
                uploaded_by_id=owner_id,
                content_hash=doc.sha256_fingerprint,
                sha256_fingerprint=doc.sha256_fingerprint,
                created_by_id=owner_id,
                change_summary="Initial uploaded version",
                edit_type="upload",
                lifecycle_state=DocumentVersionLifecycle.DRAFT.value,
            )
        )
        await self.db.flush()
        from app.modules.provenance.service import ProvenanceService

        await ProvenanceService(self.db).record_event(
            str(doc.id),
            ProvenanceEventType.CREATED,
            user_id=owner_id,
            description="Initial document version uploaded",
            sha256_after=doc.sha256_fingerprint,
            metadata={"lifecycle_state": DocumentVersionLifecycle.DRAFT.value},
            document_version_id=(
                await self.db.execute(
                    select(DocumentVersion.id).where(
                        DocumentVersion.document_id == str(doc.id),
                        DocumentVersion.version_number == 1,
                    )
                )
            ).scalar_one(),
        )
        await self.audit.log(
            AuditAction.DOCUMENT_UPLOADED,
            "document",
            str(doc.id),
            details={
                "filename": doc.original_filename,
                "size": doc.file_size,
                "mime_type": doc.mime_type,
            },
            user_id=owner_id,
            organization_id=org_id,
        )
        logger.info(
            "document_created",
            document_id=str(doc.id),
            owner_id=owner_id,
            organization_id=org_id,
        )
        return doc

    async def get_document(self, doc_id: str, org_id: str) -> Optional[Document]:
        result = await self.db.execute(
            select(Document)
            .options(lazyload("*"))
            .where(and_(Document.id == doc_id, Document.organization_id == org_id))
        )
        return result.scalar_one_or_none()

    async def rename_document(
        self,
        doc_id: str,
        org_id: str,
        user_id: str,
        title: str,
        expected_title: str | None,
    ) -> Document:
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(Document.id == doc_id, Document.organization_id == org_id)
                .with_for_update(of=Document)
            )
        ).scalar_one_or_none()
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        await self._require_mutation_access(document, user_id)
        if document.status == DocumentStatus.ARCHIVED:
            raise HTTPException(
                status_code=409, detail="An archived document cannot be renamed"
            )
        if document.title == title:
            return document
        if document.title != expected_title:
            raise HTTPException(
                status_code=409, detail="Document title changed; reload it"
            )
        document.title = title
        await self.db.flush()
        from app.modules.provenance.service import ProvenanceService

        await ProvenanceService(self.db).record_event(
            doc_id,
            ProvenanceEventType.EDITED,
            user_id=user_id,
            description="Document title renamed",
            sha256_after=document.sha256_fingerprint,
            metadata={"operation": "rename"},
        )
        return document

    async def get_document_by_storage_path(
        self, storage_path: str, org_id: str
    ) -> Optional[Document]:
        """Return an existing tenant document for idempotent upload confirmation."""
        result = await self.db.execute(
            select(Document)
            .options(lazyload("*"))
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                DocumentVersion.storage_path == storage_path,
                Document.organization_id == org_id,
            )
        )
        return result.unique().scalar_one_or_none()

    async def _require_mutation_access(self, document: Document, user_id: str) -> None:
        """Enforce document mutation authorization inside the service layer.

        Route-level role checks are useful UX, but they are not a sufficient
        boundary because services are also called by workers and future API
        paths.  A document owner may revise/archive their own document; an
        organization owner/admin may manage any document in that workspace.
        """
        membership = await require_member_permission(
            self.db,
            str(document.organization_id),
            str(user_id),
            Permission.DOCUMENT_WRITE,
        )
        if str(document.owner_id) != str(user_id) and membership.role not in (
            OrganizationRole.OWNER,
            OrganizationRole.ADMIN,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to modify this document",
            )

    async def list_documents(
        self,
        org_id: str,
        status: Optional[DocumentStatus] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        query = (
            select(Document)
            .options(lazyload("*"))
            .where(Document.organization_id == org_id)
        )
        if status:
            query = query.where(Document.status == status)
        query = query.order_by(desc(Document.created_at))
        total = await self.db.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def update_status(
        self,
        doc_id: str,
        org_id: str,
        document_status: DocumentStatus,
        error_message: Optional[str] = None,
    ) -> Document:
        doc = await self.get_document(doc_id, org_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        doc.status = document_status
        if error_message:
            doc.error_message = error_message
        if document_status == DocumentStatus.COMPLETED:
            doc.processed_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(doc)
        return doc

    async def delete_document(self, doc_id: str, org_id: str, user_id: str) -> bool:
        doc = await self.get_document(doc_id, org_id)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        await self._require_mutation_access(doc, user_id)
        # Provenance is append-only. Preserve the document, versions, analysis,
        # and evidence history by archiving instead of hard-deleting it.
        doc.status = DocumentStatus.ARCHIVED
        await self.db.flush()
        from app.modules.provenance.service import ProvenanceService

        await ProvenanceService(self.db).record_event(
            doc_id,
            ProvenanceEventType.EDITED,
            user_id=user_id,
            description="Document archived; historical versions and analysis retained",
            sha256_after=doc.sha256_fingerprint,
            metadata={
                "document_status": DocumentStatus.ARCHIVED.value,
                "operation": "archive",
            },
        )
        await self.audit.log(
            AuditAction.DOCUMENT_DELETED,
            "document",
            doc_id,
            user_id=user_id,
            organization_id=org_id,
        )
        return True

    async def create_version(
        self,
        document_id: str,
        org_id: str,
        user_id: str,
        storage_path: str,
        content_hash: str,
        change_summary: str,
        edit_type: str = "revision",
        lifecycle_state: str = DocumentVersionLifecycle.REVISION.value,
        uploaded_at: datetime | None = None,
        operation_id: str | None = None,
        operation_fingerprint: str | None = None,
    ) -> DocumentVersion:
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(
                    Document.id == document_id,
                    Document.organization_id == org_id,
                )
                .with_for_update(of=Document, key_share=True)
            )
        ).scalar_one_or_none()
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
        await self._require_mutation_access(document, user_id)
        if document.status == DocumentStatus.ARCHIVED:
            raise HTTPException(
                status_code=409, detail="An archived document cannot be revised"
            )
        latest = (
            await self.db.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not latest:
            raise ValueError(
                "A document version one is required before creating a revision"
            )
        levels = {
            DocumentVersionLifecycle.DRAFT.value: 0,
            DocumentVersionLifecycle.REVISION.value: 1,
            DocumentVersionLifecycle.FINAL.value: 2,
        }
        if lifecycle_state not in levels:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid document lifecycle state",
            )
        if levels[lifecycle_state] < levels.get(latest.lifecycle_state, 0):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document lifecycle cannot move backwards",
            )
        version = DocumentVersion(
            document_id=document_id,
            operation_id=operation_id,
            operation_fingerprint=operation_fingerprint,
            version_number=latest.version_number + 1,
            storage_path=storage_path,
            uploaded_at=uploaded_at or datetime.now(timezone.utc),
            uploaded_by_id=user_id,
            content_hash=content_hash,
            sha256_fingerprint=content_hash,
            created_by_id=user_id,
            previous_version_id=str(latest.id),
            lifecycle_state=lifecycle_state,
            change_summary=change_summary,
            edit_type=edit_type,
        )
        self.db.add(version)
        document.storage_path = storage_path
        document.sha256_fingerprint = content_hash
        document.uploaded_at = version.uploaded_at
        document.status = DocumentStatus.QUEUED
        await self.db.flush()
        from app.modules.provenance.models import ProvenanceEventType
        from app.modules.provenance.service import ProvenanceService

        await ProvenanceService(self.db).record_event(
            document_id,
            ProvenanceEventType.REVISION,
            user_id=user_id,
            description=change_summary,
            sha256_before=latest.content_hash,
            sha256_after=content_hash,
            metadata={
                "lifecycle_state": lifecycle_state,
                "version_number": version.version_number,
            },
            document_version_id=str(version.id),
        )
        await self.db.refresh(version)
        return version

    async def transition_version(
        self,
        document_id: str,
        org_id: str,
        version_id: str,
        user_id: str,
        lifecycle_state: str,
    ) -> DocumentVersion:
        document = await self.get_document(document_id, org_id)
        version = (
            await self.db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == version_id,
                    DocumentVersion.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if not document or not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        await self._require_mutation_access(document, user_id)
        levels = {
            DocumentVersionLifecycle.DRAFT.value: 0,
            DocumentVersionLifecycle.REVISION.value: 1,
            DocumentVersionLifecycle.FINAL.value: 2,
        }
        if lifecycle_state not in levels or levels[lifecycle_state] < levels.get(
            version.lifecycle_state, 0
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document lifecycle cannot move backwards",
            )
        if levels[lifecycle_state] - levels.get(version.lifecycle_state, 0) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document lifecycle transitions must be sequential",
            )
        if lifecycle_state == version.lifecycle_state:
            return version
        version.lifecycle_state = lifecycle_state
        await self.db.flush()
        from app.modules.provenance.models import ProvenanceEventType
        from app.modules.provenance.service import ProvenanceService

        await ProvenanceService(self.db).record_event(
            document_id,
            (
                ProvenanceEventType.SIGNED
                if lifecycle_state == DocumentVersionLifecycle.FINAL.value
                else ProvenanceEventType.REVISION
            ),
            user_id=user_id,
            description=f"Version {version.version_number} transitioned to {lifecycle_state}",
            sha256_after=version.content_hash,
            metadata={
                "lifecycle_state": lifecycle_state,
                "version_number": version.version_number,
            },
            document_version_id=str(version.id),
        )
        await self.db.refresh(version)
        return version
