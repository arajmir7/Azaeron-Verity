"""AZAERON document API routes."""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import select
from sqlalchemy.orm import lazyload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_active_organization
from app.core.security import generate_sha256_fingerprint
from app.core.permissions import Permission, require_permission
from app.modules.auth.models import User
from app.modules.documents.schemas import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadRequest,
    DocumentUploadResponse,
    DocumentUploadConfirm,
    DocumentDeleteResponse,
    DocumentDownloadResponse,
    DocumentVersionCreate,
    DocumentVersionLifecycleUpdate,
    DocumentVersionResponse,
    DocumentContentResponse,
    EditorRevisionRequest,
    RestoreVersionRequest,
)
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.documents.service import DocumentService
from app.modules.documents.editor import EditorRevisionService
from app.modules.documents.target import AnalysisTarget
from app.modules.uploads.service import UploadService
from app.modules.jobs.service import JobService
from app.modules.jobs.schemas import JobCreate
from app.modules.jobs.models import JobType
from app.core.logging import get_logger
from app.core.queue import QueueUnavailable, enqueue_with_retry
from app.modules.processing.models import ProcessedDocument
from app.modules.billing.entitlements import EntitlementService

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["Documents"])


def get_storage_client(*, public: bool = False):
    from app.core.object_storage import Minio
    from app.core.config import settings

    endpoint = settings.MINIO_ENDPOINT
    if public and settings.MINIO_PUBLIC_ENDPOINT:
        endpoint = settings.MINIO_PUBLIC_ENDPOINT
    return Minio(
        endpoint,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )


@router.post("/upload-request", response_model=DocumentUploadResponse)
async def request_upload(
    data: DocumentUploadRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    # Sign the URL with the browser-reachable endpoint. Object verification
    # remains on the private service-to-service client below.
    await EntitlementService(db).require_upload(
        current_user.current_organization_id, data.file_size, new_document=False
    )
    storage = get_storage_client(public=True)
    upload_service = UploadService(storage, db)
    result = upload_service.generate_upload_url(
        filename=data.filename,
        content_type=data.content_type,
        file_size=data.file_size,
        org_id=current_user.current_organization_id,
        user_id=str(current_user.id),
    )
    return DocumentUploadResponse(
        upload_id=result["upload_id"],
        upload_url=result["upload_url"],
        storage_key=result["storage_key"],
        expires_at=result["expires_at"],
    )


@router.post("/upload-confirm", response_model=DocumentResponse)
async def confirm_upload(
    data: DocumentUploadConfirm,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )

    storage = get_storage_client()
    upload_service = UploadService(storage, db)
    if not UploadService.expected_storage_key(
        data.storage_key,
        data.upload_id,
        current_user.current_organization_id,
        str(current_user.id),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upload does not belong to the active user and organization",
        )
    doc_service = DocumentService(db)
    snapshot_key = upload_service.snapshot_key(
        data.storage_key, data.sha256_fingerprint
    )
    existing = await doc_service.get_document_by_storage_path(
        snapshot_key, current_user.current_organization_id
    )
    if existing:
        return existing
    exists, size, content_type = await upload_service.verify_upload(data.storage_key)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload not found or incomplete",
        )

    content = upload_service.get_file_content(data.storage_key, max_bytes=size)
    valid, message = upload_service.validate_uploaded_content(
        data.storage_key, content_type, content
    )
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    actual_fingerprint = generate_sha256_fingerprint(content)
    if actual_fingerprint != data.sha256_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Fingerprint mismatch"
        )

    doc_service = DocumentService(db)
    existing = await doc_service.get_document_by_storage_path(
        snapshot_key,
        current_user.current_organization_id,
    )
    if existing:
        # A retried confirmation must not create a second document or enqueue
        # a second analysis for the same immutable storage object.
        return existing
    await EntitlementService(db).describe(
        current_user.current_organization_id, lock=True
    )
    # Repeat the identity check after the plan lock: a concurrent retry may
    # have committed while this request was waiting for the workspace lock.
    existing = await doc_service.get_document_by_storage_path(
        snapshot_key, current_user.current_organization_id
    )
    if existing:
        return existing
    await EntitlementService(db).require_upload(
        current_user.current_organization_id, size
    )
    from app.modules.billing.usage import UsageService

    usage = UsageService(db)
    reservation, replay = await usage.reserve(
        current_user.current_organization_id,
        str(current_user.id),
        "document_upload",
        str(data.upload_id),
        {"snapshot": snapshot_key, "fingerprint": actual_fingerprint},
        api_key_id=current_user.current_api_key_id,
    )
    if replay:
        raise HTTPException(409, "Upload operation no longer has an available document")
    await upload_service.freeze_upload(
        data.storage_key, content, actual_fingerprint, content_type
    )
    from app.modules.documents.schemas import DocumentCreate

    original_filename = data.original_filename or data.storage_key.split("/")[-1]
    doc_data = DocumentCreate(
        filename=original_filename,
        original_filename=original_filename,
        file_size=size,
        mime_type=content_type,
        extension=data.storage_key.rsplit(".", 1)[-1].lower(),
        sha256_fingerprint=data.sha256_fingerprint,
        storage_path=snapshot_key,
    )
    doc = await doc_service.create_document(
        doc_data=doc_data,
        owner_id=str(current_user.id),
        org_id=current_user.current_organization_id,
    )
    reservation.document_id = str(doc.id)
    await usage.settle(
        str(reservation.id),
        current_user.current_organization_id,
        success=True,
        outcome="completed",
    )
    initial_version_id = (
        await db.execute(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == str(doc.id),
                DocumentVersion.version_number == 1,
            )
        )
    ).scalar_one()

    job_service = JobService(db)
    job = await job_service.create_job(
        JobCreate(
            job_type=JobType.DOCUMENT_PROCESSING,
            document_id=str(doc.id),
            document_version_id=str(initial_version_id),
            input_data={
                "storage_key": snapshot_key,
                "document_version_id": str(initial_version_id),
            },
        ),
        org_id=current_user.current_organization_id,
        user_id=str(current_user.id),
    )

    await doc_service.update_status(
        str(doc.id), current_user.current_organization_id, DocumentStatus.QUEUED
    )

    from app.workers.tasks import process_document

    try:
        task = enqueue_with_retry(
            process_document,
            (
                str(job.id),
                str(doc.id),
                snapshot_key,
                current_user.current_organization_id,
                str(initial_version_id),
            ),
        )
    except QueueUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue temporarily unavailable; retry confirmation",
            headers={"Retry-After": "5"},
        )
    job.celery_task_id = task.id
    await db.flush()

    return doc


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = Query(default=1, ge=1, le=100),
    page_size: int = Query(default=20, ge=1, le=100),
    document_status: DocumentStatus | None = None,
    org_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    doc_service = DocumentService(db)
    items, total = await doc_service.list_documents(
        org_id=org_id,
        status=document_status,
        page=page,
        page_size=page_size,
    )
    return DocumentListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    doc_service = DocumentService(db)
    doc = await doc_service.get_document(doc_id, current_user.current_organization_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return doc


@router.get("/{doc_id}/content", response_model=DocumentContentResponse)
async def get_document_content(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Return only processed text for an authorized, immutable document version.

    The content is deliberately read from the processing record rather than
    the client upload. This keeps the evidence viewer aligned with the exact
    normalized text used by analysis and prevents cross-tenant object access.
    """
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    target = await AnalysisTarget.resolve(
        db, organization_id, doc_id, document_version_id
    )
    processed = await target.processed(db)
    return DocumentContentResponse(
        document_id=doc_id,
        document_version_id=str(processed.document_version_id),
        content=processed.cleaned_text or processed.raw_text or "",
        paragraphs=processed.paragraphs or [],
        sentences=processed.sentences or [],
        pipeline_version=processed.pipeline_version,
        model_version=processed.model_version,
        extracted_at=processed.created_at,
        parser_version=processed.parser_version,
        normalized_content_hash=processed.normalized_content_hash,
        structure_fingerprint=processed.structure_fingerprint,
    )


@router.get("/{doc_id}/structure")
async def get_document_structure(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    target = await AnalysisTarget.resolve(
        db, current_user.current_organization_id, doc_id, document_version_id
    )
    processed = await target.processed(db)
    return {
        "organization_id": target.organization_id,
        "document_id": doc_id,
        "document_version_id": str(target.version.id),
        "parser_version": processed.parser_version,
        "normalized_content_hash": processed.normalized_content_hash,
        "structure_fingerprint": processed.structure_fingerprint,
        "structure": processed.structure_json,
        "state": "AVAILABLE" if processed.structure_json else "LEGACY_UNAVAILABLE",
    }


@router.post("/{doc_id}/versions", response_model=DocumentVersionResponse)
async def create_document_version(
    doc_id: str,
    data: DocumentVersionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Verify an uploaded object, append an immutable version, and queue analysis."""
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    document = await DocumentService(db).get_document(doc_id, organization_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    await DocumentService(db)._require_mutation_access(document, str(current_user.id))
    if not UploadService.expected_storage_key(
        data.storage_key, data.upload_id, organization_id, str(current_user.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Upload does not belong to the active user and organization",
        )
    storage = get_storage_client()
    upload_service = UploadService(storage, db)
    snapshot_key = upload_service.snapshot_key(
        data.storage_key, data.sha256_fingerprint
    )
    existing_query = select(DocumentVersion).where(
        DocumentVersion.document_id == doc_id,
        DocumentVersion.storage_path == snapshot_key,
    )
    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        return existing
    exists, size, content_type = await upload_service.verify_upload(data.storage_key)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload not found or incomplete",
        )
    content = upload_service.get_file_content(data.storage_key, max_bytes=size)
    valid, message = upload_service.validate_uploaded_content(
        data.storage_key, content_type, content
    )
    if not valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    actual_fingerprint = generate_sha256_fingerprint(content)
    if actual_fingerprint != data.sha256_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Fingerprint mismatch"
        )
    await EntitlementService(db).require_upload(
        organization_id, size, new_document=False
    )
    # Serialize retries after the workspace quota lock, before writing a version.
    await db.execute(
        select(Document)
        .options(lazyload("*"))
        .where(Document.id == doc_id, Document.organization_id == organization_id)
        .with_for_update(of=Document)
    )
    existing = (await db.execute(existing_query)).scalar_one_or_none()
    if existing:
        return existing
    await upload_service.freeze_upload(
        data.storage_key, content, actual_fingerprint, content_type
    )
    version = await DocumentService(db).create_version(
        document_id=doc_id,
        org_id=organization_id,
        user_id=str(current_user.id),
        storage_path=snapshot_key,
        content_hash=actual_fingerprint,
        change_summary=data.change_summary,
        edit_type=data.edit_type,
        lifecycle_state=data.lifecycle_state.value,
    )
    job = await JobService(db).create_job(
        JobCreate(
            job_type=JobType.DOCUMENT_PROCESSING,
            document_id=doc_id,
            document_version_id=str(version.id),
            input_data={
                "storage_key": snapshot_key,
                "document_version_id": str(version.id),
            },
        ),
        org_id=organization_id,
        user_id=str(current_user.id),
    )
    from app.workers.tasks import process_document

    try:
        task = enqueue_with_retry(
            process_document,
            (
                str(job.id),
                doc_id,
                snapshot_key,
                organization_id,
                str(version.id),
            ),
        )
    except QueueUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue temporarily unavailable; retry confirmation",
            headers={"Retry-After": "5"},
        )
    job.celery_task_id = task.id
    await db.flush()
    return version


@router.post(
    "/{doc_id}/versions/{version_id}/lifecycle", response_model=DocumentVersionResponse
)
async def transition_document_version(
    doc_id: str,
    version_id: str,
    data: DocumentVersionLifecycleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    return await DocumentService(db).transition_version(
        doc_id,
        organization_id,
        version_id,
        str(current_user.id),
        data.lifecycle_state.value,
    )


@router.post("/{doc_id}/revisions", response_model=DocumentVersionResponse)
async def save_editor_revision(
    doc_id: str,
    data: EditorRevisionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(400, "No active organization selected")
    return await EditorRevisionService(db, get_storage_client()).save(
        doc_id,
        organization_id,
        str(current_user.id),
        str(data.base_version_id),
        str(data.operation_id),
        data.text,
        [str(edit_id) for edit_id in data.edit_ids],
    )


@router.post(
    "/{doc_id}/versions/{version_id}/restore", response_model=DocumentVersionResponse
)
async def restore_document_version(
    doc_id: str,
    version_id: str,
    data: RestoreVersionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(400, "No active organization selected")
    return await EditorRevisionService(db, get_storage_client()).restore(
        doc_id,
        organization_id,
        str(current_user.id),
        str(data.base_version_id),
        version_id,
        str(data.operation_id),
    )


@router.get("/{doc_id}/download", response_model=DocumentDownloadResponse)
async def download_document(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Issue a short-lived object URL only after tenant-scoped document lookup."""
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    target = await AnalysisTarget.resolve(
        db, current_user.current_organization_id, doc_id, document_version_id
    )
    expires = datetime.now(timezone.utc) + timedelta(minutes=7)
    from app.core.config import settings

    url = get_storage_client(public=True).presigned_get_object(
        settings.MINIO_BUCKET, target.version.storage_path, expires=timedelta(minutes=7)
    )
    return DocumentDownloadResponse(download_url=url, expires_at=expires)


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    doc_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.DOCUMENT_WRITE)
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    doc_service = DocumentService(db)
    await doc_service.delete_document(
        doc_id=doc_id,
        org_id=current_user.current_organization_id,
        user_id=str(current_user.id),
    )
    return DocumentDeleteResponse(
        id=doc_id, deleted=True, message="Document deleted successfully"
    )
