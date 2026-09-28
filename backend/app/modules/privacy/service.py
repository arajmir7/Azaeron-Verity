"""Retry-safe erasure; PostgreSQL owns authority, MinIO absence gates completion."""

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import re
import secrets
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.modules.auth import identity
from app.modules.auth.models import User
from app.modules.privacy.multipart import erase_multipart, multipart_uploads


def receipt_digest(receipt: str) -> str:
    return hashlib.sha256(receipt.encode()).hexdigest()


async def request_erasure(
    db: AsyncSession,
    user: User,
    scope: str,
    target_id: str,
    password: str,
    mfa_code: str | None,
) -> dict:
    if user.current_api_key_id:
        raise HTTPException(403, "Privacy erasure requires an authenticated session")
    user = await identity.lock_user(db, str(user.id))
    identity.check_password(user, password)
    await identity.require_mfa(db, user, mfa_code)
    request_id, receipt = str(uuid4()), secrets.token_urlsafe(32)
    try:
        result_id = await db.scalar(
            text("SELECT app.privacy_request(:id,:scope,:target,:digest)"),
            {
                "id": request_id,
                "scope": scope,
                "target": target_id,
                "digest": receipt_digest(receipt),
            },
        )
    except DBAPIError as error:
        code = getattr(error.orig, "sqlstate", None)
        if code == "42501":
            raise HTTPException(
                404, "Resource not found or erasure not authorized"
            ) from None
        if code == "P0002":
            raise HTTPException(
                409, "Transfer shared workspace ownership or erase that workspace first"
            ) from None
        if code in {"40P01", "40001", "23505"}:
            raise HTTPException(409, "Concurrent privacy request; retry") from None
        raise
    return {
        "id": result_id,
        "status": await db.scalar(
            text("SELECT status FROM privacy_erasures WHERE id=:id"), {"id": result_id}
        ),
        "receipt": receipt if result_id == request_id else None,
        "message": "Erasure is queued. Save the receipt to check completion. Existing upload URLs must expire before storage verification can complete.",
    }


def object_targets(record: dict) -> tuple[set[str], set[str]]:
    keys = set(record["object_keys"])
    prefixes = set(record["prefixes"])
    for key in list(keys):
        match = re.fullmatch(r"versions/uploads/(.+)/[0-9a-f]{64}\.([a-z0-9]+)", key)
        if match:
            # Include staging bytes that predate the immutable upload snapshot.
            keys.add(f"uploads/{match[1]}.{match[2]}")
    if any(
        not value or value.startswith("/") or ".." in value.split("/")
        for value in keys | prefixes
    ):
        raise ValueError("Invalid object erasure manifest")
    return keys, prefixes


def erase_objects(storage, record: dict) -> int:
    """Remove every object version/delete marker, then enumerate again to verify.

    Listing or retention failures are errors. A missing current object alone is
    not proof that an older version is absent. S3 listing is strongly consistent.
    """
    keys, prefixes = object_targets(record)
    removed = erase_multipart(storage, keys, prefixes)

    def selected():
        seen = set()
        for prefix in sorted(keys | prefixes):
            for item in storage.list_objects(
                settings.MINIO_BUCKET,
                prefix=prefix,
                recursive=True,
                include_version=True,
            ):
                name = item.object_name
                if name not in keys and not any(name.startswith(p) for p in prefixes):
                    continue
                identity_key = (name, item.version_id)
                if identity_key not in seen:
                    seen.add(identity_key)
                    yield item

    for item in selected():
        storage.remove_object(
            settings.MINIO_BUCKET, item.object_name, version_id=item.version_id
        )
        removed += 1
    if next(selected(), None) is not None:
        raise RuntimeError("Object absence has not been verified")
    if next(multipart_uploads(storage, keys, prefixes), None) is not None:
        raise RuntimeError("Multipart absence has not been verified")
    return removed


async def run_erasure(db: AsyncSession, storage, request_id: str) -> str:
    record = await db.scalar(
        text("SELECT app.privacy_erase_database(:id)"), {"id": request_id}
    )
    # The manifest survives crashes after DB erasure and before object removal.
    await db.commit()
    if record["status"] == "COMPLETED":
        return "COMPLETED"
    removed, succeeded = 0, False
    try:
        removed = await asyncio.to_thread(erase_objects, storage, record)
        succeeded = True
    except Exception:
        # Do not copy object names, response bodies or credentials into logs.
        succeeded = False
    state = await db.scalar(
        text("SELECT app.privacy_result(:id,:success,:removed)"),
        {"id": request_id, "success": succeeded, "removed": removed},
    )
    await db.commit()
    return str(state)


async def run_pending(storage) -> dict[str, int]:
    results: dict[str, int] = {}
    async with AsyncSessionLocal() as db:
        request_ids = list(
            (await db.scalars(text("SELECT app.privacy_pending()"))).all()
        )
        await db.commit()
        for request_id in request_ids:
            try:
                state = await run_erasure(db, storage, request_id)
            except Exception:
                await db.rollback()
                state = "DATABASE_UNAVAILABLE"
            results[state] = results.get(state, 0) + 1
    return results
