"""AZAERON upload service."""

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import uuid
import re
import time
import io
import asyncio
import hashlib

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import record_storage

logger = get_logger(__name__)


class UploadService:
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html"}
    ALLOWED_MIME_TYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "text/markdown",
        "text/html",
    }
    MAX_FILE_SIZE = 100 * 1024 * 1024

    def __init__(self, storage_client, db=None):
        self.storage = storage_client
        self.db = db

    @staticmethod
    def snapshot_key(storage_key: str, fingerprint: str) -> str:
        """Content-addressed destination outside browser-writable staging URLs."""
        stem, extension = storage_key.removeprefix("uploads/").rsplit(".", 1)
        return f"versions/uploads/{stem}/{fingerprint}.{extension}"

    async def freeze_upload(
        self, storage_key: str, content: bytes, fingerprint: str, content_type: str
    ) -> str:
        if hashlib.sha256(content).hexdigest() != fingerprint:
            raise ValueError("Snapshot fingerprint does not match its bytes")
        destination = self.snapshot_key(storage_key, fingerprint)
        if self.db is not None:
            from app.modules.privacy.storage import lock_object

            await lock_object(self.db, destination)
        try:
            await asyncio.to_thread(
                self.storage.put_object,
                settings.MINIO_BUCKET,
                destination,
                io.BytesIO(content),
                len(content),
                content_type=content_type,
            )
        except Exception as error:
            from fastapi import HTTPException

            raise HTTPException(
                503, "Unable to preserve the uploaded version; retry confirmation"
            ) from error
        return destination

    def validate_file(
        self, filename: str, content_type: str, file_size: int
    ) -> Tuple[bool, str]:
        if not isinstance(file_size, int) or file_size <= 0:
            return False, "File size must be greater than zero"
        ext = "." + filename.split(".")[-1].lower() if "." in filename else ""
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"Extension '{ext}' not allowed"
        if content_type.lower() not in self.ALLOWED_MIME_TYPES:
            return False, f"MIME type '{content_type}' not allowed"
        if file_size > min(
            self.MAX_FILE_SIZE, settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        ):
            return False, f"Size {file_size} exceeds max {self.MAX_FILE_SIZE}"
        return True, "Valid"

    @classmethod
    def expected_storage_key(
        cls, storage_key: str, upload_id: str, org_id: str, user_id: str
    ) -> bool:
        """Require the exact object namespace issued for this upload.

        Object names are opaque to MinIO; a prefix check is not a sufficient
        authorization primitive because it accepts path-like suffixes and
        alternate extensions.  The API only accepts the UUID and extension
        combination that the upload request generated.
        """
        try:
            parsed_upload_id = uuid.UUID(upload_id)
        except (ValueError, TypeError, AttributeError):
            return False
        prefix = f"uploads/{org_id}/{user_id}/{parsed_upload_id}."
        return storage_key in {
            f"{prefix}{extension.lstrip('.')}" for extension in cls.ALLOWED_EXTENSIONS
        }

    def generate_upload_url(
        self,
        filename: str,
        content_type: str,
        file_size: int,
        org_id: str,
        user_id: str,
    ) -> dict:
        is_valid, message = self.validate_file(filename, content_type, file_size)
        if not is_valid:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
        ext = filename.split(".")[-1].lower()
        upload_id = str(uuid.uuid4())
        storage_key = f"uploads/{org_id}/{user_id}/{upload_id}.{ext}"
        expires = datetime.now(timezone.utc) + timedelta(minutes=7)
        url = self.storage.presigned_put_object(
            settings.MINIO_BUCKET, storage_key, expires=timedelta(minutes=7)
        )
        return {
            "upload_id": upload_id,
            "upload_url": url,
            "storage_key": storage_key,
            "expires_at": expires,
            "fields": {},
        }

    async def verify_upload(self, storage_key: str) -> Tuple[bool, int, str]:
        started = time.perf_counter()
        outcome = "error"
        try:
            stat = self.storage.stat_object(settings.MINIO_BUCKET, storage_key)
            if stat.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                return False, 0, ""
            outcome = "success"
            return (
                True,
                stat.size,
                (stat.content_type or "application/octet-stream").lower(),
            )
        except Exception:
            return False, 0, ""
        finally:
            record_storage("stat_object", outcome, time.perf_counter() - started)

    def get_file_content(self, storage_key: str, max_bytes: int | None = None) -> bytes:
        started = time.perf_counter()
        outcome = "error"
        response = None
        try:
            response = self.storage.get_object(settings.MINIO_BUCKET, storage_key)
            data = response.read(
                (max_bytes or settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024) + 1
            )
            if len(data) > (max_bytes or settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024):
                raise ValueError("File exceeds configured size limit")
            outcome = "success"
            return data
        except Exception as e:
            logger.error(
                "file_retrieval_failed",
                error_type=type(e).__name__,
                storage_key=storage_key,
            )
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve file",
            )
        finally:
            if response is not None:
                response.close()
                response.release_conn()
            record_storage("get_object", outcome, time.perf_counter() - started)

    def validate_uploaded_content(
        self, storage_key: str, content_type: str, content: bytes
    ) -> Tuple[bool, str]:
        """Validate magic bytes and reject unsafe/ambiguous uploaded content."""
        ext = "." + storage_key.rsplit(".", 1)[-1].lower() if "." in storage_key else ""
        if ext == ".pdf" and not content.startswith(b"%PDF-"):
            return False, "Uploaded content is not a valid PDF"
        if ext == ".docx" and not content.startswith(b"PK\x03\x04"):
            return False, "Uploaded content is not a valid DOCX"
        if ext in {".txt", ".md", ".html"}:
            try:
                content.decode("utf-8")
            except UnicodeDecodeError:
                return False, "Text uploads must be UTF-8"
        if ext == ".html" and re.search(rb"<script\b|on\w+\s*=", content, re.I):
            return False, "HTML containing executable script is not accepted"
        return True, "Valid"
