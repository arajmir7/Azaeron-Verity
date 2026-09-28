"""Worker-only object maintenance and transaction-scoped writer/collector locks."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io

from fastapi import HTTPException
from app.core.object_storage import Minio
from minio.commonconfig import ENABLED, Filter
from minio.error import S3Error
from minio.lifecycleconfig import (
    Expiration,
    LifecycleConfig,
    Rule,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, apply_tenant_context
from app.modules.documents.target import AnalysisTarget
from app.modules.uploads.service import UploadService


def maintenance_client():
    if not settings.PRIVACY_MINIO_ACCESS_KEY or not settings.PRIVACY_MINIO_SECRET_KEY:
        raise RuntimeError("Worker storage maintenance credentials are required")
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.PRIVACY_MINIO_ACCESS_KEY,
        secret_key=settings.PRIVACY_MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )


async def lock_object(db: AsyncSession, key: str):
    if db.bind and db.bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "object:" + key},
        )


def configure_lifecycle(storage):
    """Preserve operator rules; never age-delete referenced document versions."""
    try:
        existing = storage.get_bucket_lifecycle(settings.MINIO_BUCKET)
        rules = list(existing.rules) if existing is not None else []
    except S3Error as error:
        if error.code != "NoSuchLifecycleConfiguration":
            raise
        rules = []
    rules = [
        rule
        for rule in rules
        if rule.rule_id not in {"verity-temporary", "verity-multipart"}
    ]
    rules.extend(
        [
            Rule(
                ENABLED,
                rule_id="verity-temporary",
                rule_filter=Filter(prefix="temporary/"),
                expiration=Expiration(days=1),
            ),
        ]
    )
    storage.set_bucket_lifecycle(settings.MINIO_BUCKET, LifecycleConfig(rules))


async def migrate_legacy_version(
    db: AsyncSession, storage, document_id: str, organization_id: str, version_id: str
) -> bool:
    await apply_tenant_context(db, organization_id, None)
    target = await AnalysisTarget.resolve(
        db, organization_id, document_id, version_id, lock=True
    )
    source = target.version.storage_path
    if not source.startswith("uploads/"):
        return False
    content = await asyncio.to_thread(UploadService(storage).get_file_content, source)
    if hashlib.sha256(content).hexdigest() != target.version.content_hash:
        # Never move changed staging bytes into an allegedly verified snapshot.
        raise ValueError("Legacy bytes do not match their recorded fingerprint")
    extension = source.rsplit(".", 1)[-1].lower()
    if "." + extension not in UploadService.ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported legacy object format")
    destination = f"versions/legacy/{organization_id}/{document_id}/{version_id}/{target.version.content_hash}.{extension}"
    await lock_object(db, destination)
    await asyncio.to_thread(
        storage.put_object,
        settings.MINIO_BUCKET,
        destination,
        io.BytesIO(content),
        len(content),
        content_type=target.document.mime_type,
    )
    copied = await asyncio.to_thread(
        UploadService(storage).get_file_content, destination
    )
    if hashlib.sha256(copied).hexdigest() != target.version.content_hash:
        raise ValueError("Relocated bytes did not verify")
    return bool(
        await db.scalar(
            text("SELECT app.storage_relocate(:version,:old,:new,:hash)"),
            {
                "version": version_id,
                "old": source,
                "new": destination,
                "hash": target.version.content_hash,
            },
        )
    )


async def collect_orphans(
    db: AsyncSession, storage, *, limit: int = 1000
) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    examined, removed, protected = 0, 0, 0
    # Each prefix has durable progress; referenced early keys cannot starve later
    # orphans. Ending within an object's versions defers any remainder to the
    # next sweep, never deletes an unexamined version.
    for prefix in ("uploads/", "versions/", "temporary/"):
        cursor = await db.scalar(
            text("SELECT app.storage_gc_cursor(:prefix)"), {"prefix": prefix}
        )
        iterator = storage.list_objects(
            settings.MINIO_BUCKET,
            prefix=prefix,
            recursive=True,
            include_version=True,
            start_after=cursor or None,
        )
        for _ in range(limit):
            item = await asyncio.to_thread(next, iterator, None)
            if item is None:
                await db.execute(
                    text("SELECT app.storage_gc_cursor(:prefix,'')"), {"prefix": prefix}
                )
                await db.commit()
                break
            examined += 1
            try:
                if item.last_modified is None or item.last_modified >= cutoff:
                    continue
                await lock_object(db, item.object_name)
                referenced = await db.scalar(
                    text("SELECT app.storage_referenced(:key)"),
                    {"key": item.object_name},
                )
                if referenced:
                    protected += 1
                    continue
                # A writer that held this lock may have replaced an unversioned key.
                try:
                    current = await asyncio.to_thread(
                        storage.stat_object,
                        settings.MINIO_BUCKET,
                        item.object_name,
                        version_id=item.version_id,
                    )
                    if current.last_modified >= cutoff:
                        continue
                except S3Error as error:
                    if error.code not in {
                        "NoSuchKey",
                        "NoSuchVersion",
                        "MethodNotAllowed",
                    }:
                        raise
                    if not item.is_delete_marker:
                        continue
                await asyncio.to_thread(
                    storage.remove_object,
                    settings.MINIO_BUCKET,
                    item.object_name,
                    version_id=item.version_id,
                )
                removed += 1
            finally:
                await db.execute(
                    text("SELECT app.storage_gc_cursor(:prefix,:cursor)"),
                    {"prefix": prefix, "cursor": item.object_name},
                )
                await db.commit()
    return {"examined": examined, "removed": removed, "referenced": protected}


async def maintain_storage(storage):
    await asyncio.to_thread(configure_lifecycle, storage)
    migrated, rejected = 0, 0
    async with AsyncSessionLocal() as db:
        candidates = (
            await db.execute(text("SELECT * FROM app.storage_legacy_candidates()"))
        ).all()
        await db.commit()
        for candidate in candidates:
            try:
                migrated += int(
                    await migrate_legacy_version(
                        db,
                        storage,
                        candidate.document_id,
                        candidate.organization_id,
                        candidate.version_id,
                    )
                )
                await db.commit()
            except Exception:
                await db.rollback()
                rejected += 1
        report = await collect_orphans(db, storage)
    return {"legacy_migrated": migrated, "legacy_rejected": rejected, **report}
