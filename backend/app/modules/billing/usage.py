"""Atomic admission, durable settlement, and bounded encrypted retry receipts.

PostgreSQL transaction advisory locks serialize each tenant's usage transitions.
No lock is held across synchronous inference. A crashed synchronous operation is
released on expiry but never automatically re-executed under the same identity.
"""

import base64
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.core.config import settings
from app.core.request_context import request_id_ctx
from app.modules.billing.models import UsageBucket, UsageOperation
from app.modules.organizations.models import Organization, SubscriptionTier

LIMITS = {
    "document_upload": (20, 200),
    "document_processing": (200, 2000),
    "text_analyze": (200, 2000),
    "text_verify": (200, 2000),
    "text_refine": (200, 2000),
    "editorial": (200, 2000),
}
MODEL_CALLS: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "usage_model_calls", default=None
)


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def cipher():
    key = settings.USAGE_ENCRYPTION_KEY
    if (
        key
        and settings.ENVIRONMENT == "production"
        and key == settings.IDENTITY_ENCRYPTION_KEY
    ):
        raise HTTPException(503, "Usage and identity encryption keys must differ")
    if not key:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(503, "Usage receipt encryption is not configured")
        key = base64.urlsafe_b64encode(
            hashlib.sha256(
                (settings.SECRET_KEY + ":usage-development-only").encode()
            ).digest()
        ).decode()
    try:
        return Fernet(key.encode())
    except (TypeError, ValueError):
        raise HTTPException(503, "Usage receipt encryption is not configured") from None


@contextmanager
def collect_model_calls():
    calls: list[dict[str, Any]] = []
    token = MODEL_CALLS.set(calls)
    try:
        yield calls
    finally:
        MODEL_CALLS.reset(token)


def record_model_call(result):
    calls = MODEL_CALLS.get()
    if calls is not None:
        calls.append(
            {
                name: getattr(result, name)
                for name in (
                    "model_id",
                    "model_revision",
                    "input_tokens",
                    "output_tokens",
                    "duration_ms",
                )
            }
        )


class UsageService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def lock(self, organization_id: str):
        if self.db.bind and self.db.bind.dialect.name == "postgresql":
            # Match privacy/worker ordering: shared tenant fence before usage.
            # Acquiring usage first can deadlock behind queued tenant erasure.
            await self.db.execute(
                select(Organization.id)
                .where(Organization.id == organization_id)
                .with_for_update(read=True)
            )
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                {"key": "usage:" + organization_id},
            )

    async def limits(self, organization_id: str):
        org = await self.db.scalar(
            select(Organization)
            .options(lazyload("*"))
            .where(
                Organization.id == organization_id,
                Organization.is_active.is_(True),
                Organization.erasure_pending.is_(False),
            )
            .execution_options(populate_existing=True)
        )
        if org is None:
            raise HTTPException(404, "Workspace not found")
        free = org.subscription_tier == SubscriptionTier.FREE or bool(
            org.subscription_expires_at and aware(org.subscription_expires_at) <= now()
        )
        return {task: limits[0 if free else 1] for task, limits in LIMITS.items()}

    async def bucket(self, org: str, period: str, task: str):
        bucket = await self.db.scalar(
            select(UsageBucket)
            .where(
                UsageBucket.organization_id == org,
                UsageBucket.period == period,
                UsageBucket.task == task,
            )
            .execution_options(populate_existing=True)
        )
        if bucket is None:
            baseline = 0
            if task == "document_upload":
                from app.modules.documents.models import Document

                start = datetime.strptime(period, "%Y-%m")
                end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                baseline = int(
                    await self.db.scalar(
                        select(func.count())
                        .select_from(Document)
                        .where(
                            Document.organization_id == org,
                            Document.created_at >= start,
                            Document.created_at < end,
                        )
                    )
                    or 0
                )
            bucket = UsageBucket(
                organization_id=org,
                period=period,
                task=task,
                reserved=0,
                committed=baseline,
            )
            self.db.add(bucket)
            await self.db.flush()
        return bucket

    async def reserve(
        self,
        org: str,
        user: str,
        task: str,
        operation_id: str,
        payload: Any,
        *,
        api_key_id: str | None = None,
        document_id: str | None = None,
        job_id: str | None = None
    ):
        if task not in LIMITS:
            raise ValueError("Unknown metered task")
        await self.lock(org)
        existing = await self.db.scalar(
            select(UsageOperation)
            .where(
                UsageOperation.organization_id == org,
                UsageOperation.task == task,
                UsageOperation.operation_id == operation_id,
            )
            .execution_options(populate_existing=True)
        )
        digest = fingerprint(payload)
        if existing:
            if (
                existing.fingerprint != digest
                or existing.user_id != user
                or existing.api_key_id != api_key_id
            ):
                raise HTTPException(
                    409, "Operation ID belongs to a different request or credential"
                )
            if (
                existing.status == "RESERVED"
                and not existing.job_id
                and aware(existing.expires_at) <= now()
            ):
                await self.settle(
                    str(existing.id), org, success=False, outcome="outcome_unknown"
                )
            return existing, True
        limits = await self.limits(org)
        # Expiry never authorizes duplicate execution. Requests get a terminal
        # unknown-outcome receipt and must use a new ID for intentional new work.
        await self.expire(org)
        period = now().strftime("%Y-%m")
        bucket = await self.bucket(org, period, task)
        if bucket.reserved + bucket.committed >= limits[task]:
            raise HTTPException(
                402,
                {
                    "code": "usage_quota_exceeded",
                    "task": task,
                    "limit": limits[task],
                    "period": period,
                },
            )
        if task.startswith("text_"):
            active = await self.db.scalar(
                select(func.count())
                .select_from(UsageOperation)
                .where(
                    UsageOperation.organization_id == org,
                    UsageOperation.status == "RESERVED",
                    UsageOperation.task.like("text_%"),
                )
            )
            if active and active >= 4:
                raise HTTPException(
                    429,
                    "Workspace concurrent text-operation limit reached",
                    headers={"Retry-After": "5"},
                )
        record = UsageOperation(
            organization_id=org,
            user_id=user,
            api_key_id=api_key_id,
            document_id=document_id,
            job_id=job_id,
            operation_id=operation_id,
            request_id=request_id_ctx.get(),
            task=task,
            period=period,
            fingerprint=digest,
            status="RESERVED",
            chargeable=False,
            billable=False,
            model_calls=[],
            expires_at=now()
            + timedelta(
                seconds=(
                    300
                    if not job_id
                    else settings.CELERY_TASK_TIME_LIMIT_SECONDS * 5 + 3600
                )
            ),
        )
        bucket.reserved += 1
        self.db.add(record)
        await self.db.flush()
        return record, False

    async def settle(
        self,
        record_id: str,
        org: str,
        *,
        success: bool,
        outcome: str,
        response: Any = None,
        response_status: int = 200,
        calls: list[dict] | None = None,
        duration_ms: int | None = None
    ):
        await self.db.flush()
        await self.lock(org)
        record = await self.db.scalar(
            select(UsageOperation)
            .where(
                UsageOperation.id == record_id, UsageOperation.organization_id == org
            )
            .execution_options(populate_existing=True)
        )
        if record is None:
            raise HTTPException(409, "Operation was removed by privacy erasure")
        if record.status != "RESERVED":
            return record
        bucket = await self.bucket(org, record.period, record.task)
        bucket.reserved -= 1
        bucket.committed += int(success)
        record.status = "COMMITTED" if success else "RELEASED"
        record.chargeable = success
        record.outcome = outcome
        record.completed_at = now()
        record.model_calls = list(calls or [])
        record.input_tokens = (
            sum(call["input_tokens"] for call in calls) if calls else None
        )
        record.output_tokens = (
            sum(call["output_tokens"] for call in calls) if calls else None
        )
        record.duration_ms = duration_ms
        if response is not None:
            record.response_ciphertext = (
                cipher()
                .encrypt(json.dumps(response, separators=(",", ":")).encode())
                .decode()
            )
            record.response_expires_at = now() + timedelta(hours=24)
            record.response_status = response_status
        await self.db.flush()
        return record

    async def settle_job(
        self,
        job_id: str,
        org: str,
        *,
        success: bool,
        outcome: str,
        duration_ms: int | None = None
    ):
        record = await self.db.scalar(
            select(UsageOperation).where(
                UsageOperation.organization_id == org, UsageOperation.job_id == job_id
            )
        )
        # Pre-migration jobs have no reservation; never fabricate past usage.
        if record:
            await self.settle(
                str(record.id),
                org,
                success=success,
                outcome=outcome,
                duration_ms=duration_ms,
            )

    def replay(self, record):
        if record.status == "RESERVED":
            raise HTTPException(
                409, "Operation is still in progress", headers={"Retry-After": "5"}
            )
        if (
            not record.response_ciphertext
            or not record.response_expires_at
            or aware(record.response_expires_at) <= now()
        ):
            raise HTTPException(
                409,
                "Operation receipt expired or outcome is unknown; this ID will not execute again",
            )
        try:
            return (
                json.loads(cipher().decrypt(record.response_ciphertext.encode())),
                record.response_status,
            )
        except (InvalidToken, ValueError):
            raise HTTPException(503, "Operation receipt cannot be decrypted") from None

    async def expire(self, org):
        records = list(
            (
                await self.db.scalars(
                    select(UsageOperation)
                    .where(
                        UsageOperation.organization_id == org,
                        UsageOperation.status == "RESERVED",
                        UsageOperation.expires_at <= now(),
                        UsageOperation.job_id.is_(None),
                    )
                    .limit(100)
                )
            ).all()
        )
        for record in records:
            await self.settle(
                str(record.id), org, success=False, outcome="outcome_unknown"
            )
        return len(records)

    async def summary(self, org):
        limits = await self.limits(org)
        period = now().strftime("%Y-%m")
        buckets = {
            bucket.task: bucket
            for bucket in (
                await self.db.scalars(
                    select(UsageBucket).where(
                        UsageBucket.organization_id == org, UsageBucket.period == period
                    )
                )
            ).all()
        }
        return {
            "period": period,
            "unit": "operations",
            "billing_enabled": False,
            "limits": [
                {
                    "task": task,
                    "limit": limit,
                    "reserved": buckets[task].reserved if task in buckets else 0,
                    "committed": buckets[task].committed if task in buckets else 0,
                }
                for task, limit in limits.items()
            ],
        }
