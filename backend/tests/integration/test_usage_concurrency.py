"""Quota admission races use actual non-owner PostgreSQL transactions."""

import asyncio
from datetime import datetime, timezone
import os
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import apply_tenant_context
from app.modules.auth.models import User
from app.modules.billing.models import UsageBucket, UsageOperation
from app.modules.billing.usage import UsageService, now
from app.modules.organizations.models import Organization, Membership, OrganizationRole

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="Actual isolated PostgreSQL required"
)


async def test_last_quota_slot_concurrency_retry_settlement_and_tenant_isolation():
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, other, user = (str(uuid4()) for _ in range(3))
    try:
        async with sessions.begin() as db:
            await db.execute(
                insert(User).values(
                    id=user,
                    email=f"usage-{user}@example.com",
                    hashed_password="fixture-only",
                )
            )
            for org_id in (org, other):
                await db.execute(
                    insert(Organization).values(
                        id=org_id, name="Usage race", slug=org_id
                    )
                )
            await db.execute(
                insert(Membership).values(
                    user_id=user,
                    organization_id=org,
                    role=OrganizationRole.OWNER,
                    joined_at=datetime.now(timezone.utc),
                )
            )
            await apply_tenant_context(db, org, user)
            db.add(
                UsageBucket(
                    organization_id=org,
                    period=now().strftime("%Y-%m"),
                    task="text_analyze",
                    committed=199,
                    reserved=0,
                )
            )

        async def reserve(operation):
            async with sessions.begin() as db:
                await apply_tenant_context(db, org, user)
                try:
                    row, replay = await UsageService(db).reserve(
                        org, user, "text_analyze", operation, {"fixture": 1}
                    )
                    return str(row.id), replay
                except HTTPException as error:
                    return error.status_code

        operations = [str(uuid4()) for _ in range(8)]
        results = await asyncio.gather(
            *(reserve(operation) for operation in operations)
        )
        assert results.count(402) == 7
        winner_index = next(
            i for i, result in enumerate(results) if isinstance(result, tuple)
        )
        record_id = results[winner_index][0]
        assert (
            await asyncio.gather(*(reserve(operations[winner_index]) for _ in range(4)))
            == [(record_id, True)] * 4
        )

        async def settle():
            async with sessions.begin() as db:
                await apply_tenant_context(db, org, user)
                await UsageService(db).settle(
                    record_id, org, success=True, outcome="completed"
                )

        await asyncio.gather(*(settle() for _ in range(5)))
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            bucket = await db.scalar(
                select(UsageBucket).where(UsageBucket.organization_id == org)
            )
            assert (bucket.committed, bucket.reserved) == (200, 0)
            await apply_tenant_context(db, other, user)
            assert (
                await db.scalar(
                    select(UsageOperation.id).where(UsageOperation.id == record_id)
                )
                is None
            )
        # Release of a different reservation makes exactly one slot reusable.
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            row, _ = await UsageService(db).reserve(
                org, user, "text_verify", str(uuid4()), {}
            )
            await UsageService(db).settle(
                str(row.id), org, success=False, outcome="failed"
            )
            bucket = await UsageService(db).bucket(
                org, now().strftime("%Y-%m"), "text_verify"
            )
            assert (bucket.committed, bucket.reserved) == (0, 0)
    finally:
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            await db.execute(
                delete(Organization).where(Organization.id.in_([org, other]))
            )
            await db.execute(delete(User).where(User.id == user))
        await engine.dispose()


async def test_concurrent_text_limit_is_shared_across_tasks():
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, user = str(uuid4()), str(uuid4())
    try:
        async with sessions.begin() as db:
            await db.execute(
                insert(User).values(
                    id=user,
                    email=f"active-{user}@example.com",
                    hashed_password="fixture-only",
                )
            )
            await db.execute(
                insert(Organization).values(id=org, name="Active race", slug=org)
            )
            await apply_tenant_context(db, org, user)

        async def reserve(i):
            async with sessions.begin() as db:
                await apply_tenant_context(db, org, user)
                try:
                    await UsageService(db).reserve(
                        org,
                        user,
                        ["text_analyze", "text_verify"][i % 2],
                        str(uuid4()),
                        {},
                    )
                    return 200
                except HTTPException as error:
                    return error.status_code

        results = await asyncio.gather(*(reserve(i) for i in range(10)))
        assert results.count(200) == 4 and results.count(429) == 6
    finally:
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            await db.execute(delete(Organization).where(Organization.id == org))
            await db.execute(delete(User).where(User.id == user))
        await engine.dispose()


async def test_upload_admission_does_not_wait_for_a_worker_privacy_fence():
    from app.modules.billing.entitlements import EntitlementService

    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, user = str(uuid4()), str(uuid4())
    try:
        async with sessions.begin() as db:
            await db.execute(
                insert(User).values(
                    id=user,
                    email=f"load-lock-{user}@example.com",
                    hashed_password="fixture-only",
                )
            )
            await db.execute(
                insert(Organization).values(id=org, name="Concurrent uploads", slug=org)
            )
            await db.execute(
                insert(Membership).values(
                    user_id=user,
                    organization_id=org,
                    role=OrganizationRole.OWNER,
                    joined_at=datetime.now(timezone.utc),
                )
            )
        async with sessions.begin() as worker:
            await apply_tenant_context(worker, org, user)
            # Exactly the tenant lock retained by privacy_write_fence for a long job.
            await worker.execute(
                select(Organization.id)
                .where(Organization.id == org)
                .with_for_update(read=True)
            )
            async with sessions.begin() as api:
                await apply_tenant_context(api, org, user)
                await api.execute(text("SET LOCAL lock_timeout='500ms'"))
                await EntitlementService(api).require_upload(org, 1024)
                record, replay = await UsageService(api).reserve(
                    org, user, "document_upload", str(uuid4()), {}
                )
                assert not replay and record.status == "RESERVED"
    finally:
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            await db.execute(delete(Organization).where(Organization.id == org))
            await db.execute(delete(User).where(User.id == user))
        await engine.dispose()


async def test_api_key_issue_does_not_wait_for_a_worker_privacy_fence():
    from app.modules.auth.api_keys import KeyCreate, create_key

    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, user_id = str(uuid4()), str(uuid4())
    try:
        async with sessions.begin() as db:
            await db.execute(
                insert(User).values(
                    id=user_id,
                    email=f"key-lock-{user_id}@example.com",
                    hashed_password="fixture-only",
                )
            )
            await db.execute(
                insert(Organization).values(id=org, name="Key worker lock", slug=org)
            )
            await db.execute(
                insert(Membership).values(
                    user_id=user_id,
                    organization_id=org,
                    role=OrganizationRole.OWNER,
                    joined_at=datetime.now(timezone.utc),
                )
            )

        async with sessions.begin() as worker:
            await apply_tenant_context(worker, org, user_id)
            await worker.execute(
                select(Organization.id)
                .where(Organization.id == org)
                .with_for_update(read=True)
            )
            async with sessions.begin() as api:
                await apply_tenant_context(api, org, user_id)
                await api.execute(text("SET LOCAL lock_timeout='500ms'"))
                manager = await api.get(User, user_id)
                assert manager is not None
                manager.current_organization_id = org
                issued = await create_key(
                    api,
                    manager,
                    KeyCreate(name="Under worker load", scopes=["usage:read"]),
                )
                assert issued.key.organization_id == org
    finally:
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user_id)
            await db.execute(delete(Organization).where(Organization.id == org))
            await db.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_concurrent_analysis_targets_allow_reciprocal_similarity_foreign_keys():
    from app.modules.documents.models import Document, DocumentVersion
    from app.modules.documents.target import AnalysisTarget
    from app.modules.similarity.models import SimilarityMatch, SimilarityType

    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org, user = str(uuid4()), str(uuid4())
    documents = [(str(uuid4()), str(uuid4())) for _ in range(2)]
    barrier = asyncio.Barrier(2)
    try:
        async with sessions.begin() as db:
            await db.execute(
                insert(User).values(
                    id=user,
                    email=f"fk-lock-{user}@example.com",
                    hashed_password="fixture-only",
                )
            )
            await db.execute(
                insert(Organization).values(
                    id=org, name="Analysis foreign keys", slug=org
                )
            )
            await db.execute(
                insert(Membership).values(
                    user_id=user,
                    organization_id=org,
                    role=OrganizationRole.OWNER,
                    joined_at=datetime.now(timezone.utc),
                )
            )
            await apply_tenant_context(db, org, user)
            for doc, version in documents:
                await db.execute(
                    insert(Document).values(
                        id=doc,
                        organization_id=org,
                        owner_id=user,
                        filename="fixture.txt",
                        original_filename="fixture.txt",
                        file_size=12,
                        mime_type="text/plain",
                        extension="txt",
                        sha256_fingerprint="a" * 64,
                        storage_path=f"uploads/{org}/{doc}.txt",
                    )
                )
                await db.execute(
                    insert(DocumentVersion).values(
                        id=version,
                        document_id=doc,
                        version_number=1,
                        storage_path=f"uploads/{org}/{doc}.txt",
                        content_hash="a" * 64,
                        sha256_fingerprint="a" * 64,
                        created_by_id=user,
                    )
                )

        async def link(index):
            doc, version = documents[index]
            other, other_version = documents[1 - index]
            async with sessions.begin() as db:
                await apply_tenant_context(db, org, user)
                await db.execute(text("SET LOCAL lock_timeout='2s'"))
                await AnalysisTarget.resolve(db, org, doc, version, lock=True)
                await barrier.wait()
                db.add(
                    SimilarityMatch(
                        organization_id=org,
                        document_id=doc,
                        target_document_id=doc,
                        document_version_id=version,
                        source_document_id=other,
                        source_document_version_id=other_version,
                        match_type=SimilarityType.EXACT,
                        document_span_start=0,
                        document_span_end=4,
                        similarity_score=1,
                        confidence=1,
                        pipeline_version="lock-test",
                        model_version="fixture",
                    )
                )
                await db.flush()
                # A real child write has taken privacy_write_fence, in addition
                # to AnalysisTarget's locks. Saves must still proceed immediately.
                await barrier.wait()
                if index == 0:
                    from app.modules.documents.service import DocumentService
                    from sqlalchemy.exc import DBAPIError

                    async with sessions.begin() as writer:
                        await apply_tenant_context(writer, org, user)
                        await writer.execute(text("SET LOCAL lock_timeout='500ms'"))
                        saved = await DocumentService(writer).create_version(
                            doc,
                            org,
                            user,
                            f"versions/{org}/{doc}/second.txt",
                            "c" * 64,
                            "Save during immutable analysis",
                        )
                        assert saved.version_number == 2
                    # Erasure must wait for the still-open analysis, rather than
                    # permitting an artifact to commit after a completed fence.
                    async with sessions.begin() as eraser:
                        await apply_tenant_context(eraser, org, user)
                        await eraser.execute(text("SET LOCAL lock_timeout='100ms'"))
                        with pytest.raises(DBAPIError):
                            await eraser.execute(
                                text(
                                    "SELECT app.privacy_request(:id,'document',:target,:digest)"
                                ),
                                {"id": str(uuid4()), "target": doc, "digest": "d" * 64},
                            )
                        await eraser.rollback()
                await barrier.wait()

        await asyncio.wait_for(asyncio.gather(link(0), link(1)), timeout=10)
        # The partial index must retain the original storage-path uniqueness.
        from sqlalchemy.exc import IntegrityError

        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(
                        text("UPDATE documents SET storage_path=:path WHERE id=:id"),
                        {
                            "id": documents[1][0],
                            "path": f"versions/{org}/{documents[0][0]}/second.txt",
                        },
                    )
    finally:
        # Immutable committed fixtures are removed through the authorized privacy
        # database routine, retaining the tombstone just like other integration fixtures.
        async with sessions.begin() as db:
            await apply_tenant_context(db, org, user)
            request_id = str(uuid4())
            await db.execute(
                text("SELECT app.privacy_request(:id,'account',:target,:digest)"),
                {"id": request_id, "target": user, "digest": "b" * 64},
            )
            await db.execute(
                text("SELECT app.privacy_erase_database(:id)"), {"id": request_id}
            )
        await engine.dispose()
