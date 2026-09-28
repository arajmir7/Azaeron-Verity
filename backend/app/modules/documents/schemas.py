"""AZAERON document schemas."""

from datetime import datetime
from uuid import UUID
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.modules.documents.models import DocumentStatus, DocumentVersionLifecycle


class DocumentBase(BaseModel):
    title: Optional[str] = None


class DocumentCreate(DocumentBase):
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    extension: str
    sha256_fingerprint: str
    storage_path: str


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    owner_id: str
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    extension: str
    sha256_fingerprint: str
    status: DocumentStatus
    error_message: Optional[str] = None
    word_count: Optional[int] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentUploadRequest(BaseModel):
    filename: str
    content_type: str
    file_size: int = Field(..., gt=0, le=100 * 1024 * 1024)


class DocumentUploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    storage_key: str
    expires_at: datetime


class DocumentUploadConfirm(BaseModel):
    upload_id: str
    storage_key: str
    sha256_fingerprint: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"
    )
    # Kept separate from the opaque storage key so the workspace can show the
    # filename a reviewer selected without exposing object namespace details.
    original_filename: Optional[str] = Field(default=None, max_length=255)


class DocumentDeleteResponse(BaseModel):
    id: str
    deleted: bool
    message: str


class DocumentDownloadResponse(BaseModel):
    """Short-lived, tenant-authorized object retrieval URL."""

    download_url: str
    expires_at: datetime


class DocumentContentResponse(BaseModel):
    """Tenant-authorized, version-scoped extracted text for evidence review."""

    document_id: str
    document_version_id: str
    content: str
    paragraphs: list[dict[str, Any]] = []
    sentences: list[dict[str, Any]] = []
    pipeline_version: str
    model_version: Optional[str] = None
    extracted_at: Optional[datetime] = None
    parser_version: str
    normalized_content_hash: Optional[str] = None
    structure_fingerprint: Optional[str] = None


class DocumentVersionCreate(BaseModel):
    upload_id: str
    storage_key: str
    sha256_fingerprint: str = Field(
        ..., min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$"
    )
    change_summary: str = Field(..., min_length=1, max_length=2000)
    edit_type: str = Field(default="revision", min_length=1, max_length=50)
    lifecycle_state: DocumentVersionLifecycle = DocumentVersionLifecycle.REVISION


class DocumentVersionLifecycleUpdate(BaseModel):
    lifecycle_state: DocumentVersionLifecycle


class EditorRevisionRequest(BaseModel):
    """A working draft or a server-verified subset of persisted suggestions."""

    model_config = {"extra": "forbid"}
    operation_id: UUID
    base_version_id: UUID
    text: str = Field(min_length=1, max_length=200_000)
    edit_ids: list[UUID] = Field(default_factory=list, max_length=1000)


class RestoreVersionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    operation_id: UUID
    base_version_id: UUID


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    version_number: int
    content_hash: str
    sha256_fingerprint: str
    created_by_id: Optional[str]
    uploaded_by_id: Optional[str]
    created_at: datetime
    uploaded_at: datetime
    storage_path: str
    previous_version_id: Optional[str]
    lifecycle_state: str
    change_summary: Optional[str]
    edit_type: Optional[str]
