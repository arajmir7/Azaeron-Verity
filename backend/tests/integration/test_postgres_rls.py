"""Exercise actual PostgreSQL policies through the non-owner runtime role.

Set POSTGRES_TEST_DATABASE_URL to a migrated, isolated PostgreSQL database.
Fixtures roll back all seeded records; SQLite cannot substitute for this gate.
"""

import os
import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import insert, select, text, delete, update, func
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.database import apply_tenant_context
from app.modules.auth.models import User
from app.modules.audit.models import AuditAction, AuditLog
from app.modules.audit.service import AuditService
from app.modules.documents.models import Document, DocumentStatus, DocumentVersion
from app.modules.documents.service import DocumentService
from app.modules.jobs.models import Job, JobType
from app.modules.organizations.models import Membership, Organization, OrganizationRole

POSTGRES_URL = os.environ.get("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="POSTGRES_TEST_DATABASE_URL is required for real PostgreSQL RLS verification",
)

TENANT_TABLES = {
    "ai_voice_profiles",
    "ai_conversations",
    "ai_messages",
    "ai_runs",
    "ai_events",
    "ai_tool_calls",
    "ai_tool_results",
    "ai_action_receipts",
    "ai_document_attachments",
    "usage_operations",
    "usage_buckets",
    "privacy_erasures",
    "aegis_edits",
    "analysis_runs",
    "api_keys",
    "assignments",
    "audit_logs",
    "authorship_profiles",
    "authorship_signals",
    "billing_events",
    "citation_findings",
    "citation_references",
    "citation_sources",
    "citations",
    "claims",
    "compliance_reports",
    "detection_results",
    "detection_segments",
    "document_chunks",
    "document_versions",
    "documents",
    "evidence_edges",
    "evidence_nodes",
    "integrity_reports",
    "jobs",
    "processed_documents",
    "provenance_events",
    "provenance_exports",
    "provenance_reports",
    "similarity_index_entries",
    "similarity_matches",
    "similarity_analyses",
    "submissions",
}


@pytest_asyncio.fixture
async def postgres_session():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_size=1, max_overflow=0)
    try:
        async with engine.connect() as connection:
            async with connection.begin() as transaction:
                session = AsyncSession(bind=connection, expire_on_commit=False)
                try:
                    role = (
                        await session.execute(
                            text(
                                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                            )
                        )
                    ).one()
                    assert (
                        role.current_user == "azaeron_app"
                    ), "Use the actual runtime DB role"
                    assert not role.rolsuper and not role.rolbypassrls
                    owners = (
                        await session.execute(
                            text(
                                "SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user"
                            )
                        )
                    ).scalar_one()
                    assert owners == 0, "Runtime must not own the application tables"
                    yield session
                finally:
                    await session.close()
                    if transaction.is_active:
                        await transaction.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def tenants(postgres_session):
    session = postgres_session
    records = []
    for _ in range(2):
        user_id, org_id, doc_id, version_id, job_id = [str(uuid4()) for _ in range(5)]
        await session.execute(
            insert(User).values(
                id=user_id,
                email=f"rls-{user_id}@example.com",
                hashed_password="fixture-only-no-login",
            )
        )
        await session.execute(
            insert(Organization).values(
                id=org_id, name="RLS fixture", slug=f"rls-{org_id}"
            )
        )
        await session.execute(
            insert(Membership).values(
                user_id=user_id,
                organization_id=org_id,
                role=OrganizationRole.OWNER,
                joined_at=datetime.now(timezone.utc),
            )
        )
        await apply_tenant_context(session, org_id, user_id)
        await session.execute(
            insert(Document).values(
                id=doc_id,
                organization_id=org_id,
                owner_id=user_id,
                filename="fixture.txt",
                original_filename="fixture.txt",
                file_size=12,
                mime_type="text/plain",
                extension="txt",
                sha256_fingerprint="a" * 64,
                storage_path=f"uploads/{org_id}/{doc_id}.txt",
            )
        )
        await session.execute(
            insert(DocumentVersion).values(
                id=version_id,
                document_id=doc_id,
                version_number=1,
                storage_path=f"uploads/{org_id}/{doc_id}.txt",
                content_hash="a" * 64,
                sha256_fingerprint="a" * 64,
                created_by_id=user_id,
                uploaded_by_id=user_id,
            )
        )
        await session.execute(
            insert(Job).values(
                id=job_id,
                organization_id=org_id,
                document_id=doc_id,
                document_version_id=version_id,
                job_type=JobType.DOCUMENT_PROCESSING,
            )
        )
        records.append(
            {
                "user": user_id,
                "org": org_id,
                "documents": doc_id,
                "document_versions": version_id,
                "jobs": job_id,
            }
        )
    return records


async def test_runtime_role_has_forced_policies_on_all_tenant_tables(postgres_session):
    rows = (
        await postgres_session.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace "
                "WHERE nspname = 'public' AND relkind = 'r'"
            )
        )
    ).all()
    policies = {
        row.relname: row.relrowsecurity and row.relforcerowsecurity for row in rows
    }
    assert TENANT_TABLES <= policies.keys()
    assert all(policies[name] for name in TENANT_TABLES)


@pytest.mark.parametrize("table", ["documents", "document_versions", "jobs"])
async def test_raw_reads_hide_other_tenant_without_application_filter(
    postgres_session, tenants, table
):
    own, other = tenants
    await apply_tenant_context(postgres_session, own["org"], own["user"])
    # Only the row IDs constrain the query: no application tenant predicate.
    visible = (
        (
            await postgres_session.execute(
                text(f"SELECT id FROM {table} WHERE id IN (:own, :other)"),
                {"own": own[table], "other": other[table]},
            )
        )
        .scalars()
        .all()
    )
    assert visible == [own[table]]
    await apply_tenant_context(postgres_session, other["org"], other["user"])
    visible = (
        (
            await postgres_session.execute(
                text(f"SELECT id FROM {table} WHERE id IN (:own, :other)"),
                {"own": own[table], "other": other[table]},
            )
        )
        .scalars()
        .all()
    )
    assert visible == [other[table]]


async def test_clearing_context_fails_closed_in_same_transaction(
    postgres_session, tenants
):
    own = tenants[0]
    await apply_tenant_context(postgres_session, own["org"], own["user"])
    assert (
        await postgres_session.execute(
            select(Document.id).where(Document.id == own["documents"])
        )
    ).scalar_one()
    await apply_tenant_context(postgres_session, None, None)
    for model in (Document, DocumentVersion, Job):
        assert not (await postgres_session.execute(select(model.id))).all()


async def test_account_audit_events_are_user_scoped_without_workspace(
    postgres_session, tenants
):
    for tenant in tenants:
        await AuditService(postgres_session).log(
            AuditAction.USER_LOGIN, "user", tenant["user"], user_id=tenant["user"]
        )
    own, other = tenants
    await apply_tenant_context(postgres_session, None, own["user"])
    ids = (
        (
            await postgres_session.execute(
                select(AuditLog.user_id).where(AuditLog.organization_id.is_(None))
            )
        )
        .scalars()
        .all()
    )
    assert own["user"] in ids
    assert other["user"] not in ids
    await apply_tenant_context(postgres_session, None, None)
    assert not (await postgres_session.execute(select(AuditLog.id))).all()


async def test_cross_tenant_update_and_insert_are_denied(postgres_session, tenants):
    own, other = tenants
    await apply_tenant_context(postgres_session, own["org"], own["user"])
    updated = await postgres_session.execute(
        text("UPDATE documents SET title = 'forbidden' WHERE id = :id RETURNING id"),
        {"id": other["documents"]},
    )
    assert updated.all() == []
    async with postgres_session.begin_nested() as savepoint:
        with pytest.raises(
            DBAPIError,
            match="row-level security|analysis organization/document/version target mismatch",
        ):
            await postgres_session.execute(
                insert(Job).values(
                    organization_id=other["org"],
                    document_id=other["documents"],
                    document_version_id=other["document_versions"],
                    job_type=JobType.DOCUMENT_PROCESSING,
                )
            )
        await savepoint.rollback()


async def test_tenant_settings_do_not_survive_connection_reuse():
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL, pool_size=1, max_overflow=0)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT set_config('app.current_organization_id', 'previous-tenant', true)"
                )
            )
        async with engine.begin() as connection:
            assert (
                await connection.execute(text("SELECT app.current_organization_id()"))
            ).scalar_one() is None
            assert (
                await connection.execute(text("SELECT id FROM documents"))
            ).all() == []
    finally:
        await engine.dispose()


async def test_foreign_document_status_update_returns_404(postgres_session, tenants):
    from fastapi import HTTPException

    own, other = tenants
    await apply_tenant_context(postgres_session, own["org"], own["user"])
    with pytest.raises(HTTPException) as error:
        await DocumentService(postgres_session).update_status(
            other["documents"],
            own["org"],
            DocumentStatus.PROCESSING,
        )
    assert error.value.status_code == 404


async def test_concurrent_first_run_creates_one_workspace():
    from app.modules.auth.service import AuthService
    from app.modules.auth.schemas import OnboardingRequest, ProductRole

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = str(uuid4())
    try:
        async with sessions.begin() as session:
            await session.execute(
                insert(User).values(
                    id=user_id,
                    email=f"concurrent-{user_id}@example.com",
                    hashed_password="fixture-only",
                )
            )

        async def onboard():
            async with sessions.begin() as session:
                user = (
                    await session.execute(select(User).where(User.id == user_id))
                ).scalar_one()
                result = await AuthService(session).complete_onboarding(
                    user, OnboardingRequest(product_role=ProductRole.STUDENT)
                )
                return result.personal_organization_id

        results = await asyncio.gather(onboard(), onboard())
        assert results[0] == results[1]
        async with sessions.begin() as session:
            assert (
                await session.execute(
                    select(func.count(Membership.id)).where(
                        Membership.user_id == user_id
                    )
                )
            ).scalar_one() == 1
    finally:
        async with sessions.begin() as session:
            org_id = (
                await session.execute(
                    select(User.personal_organization_id).where(User.id == user_id)
                )
            ).scalar_one_or_none()
            await apply_tenant_context(session, org_id, user_id)
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(personal_organization_id=None, last_active_organization_id=None)
            )
            if org_id:
                await session.execute(
                    delete(Organization).where(Organization.id == org_id)
                )
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_concurrent_uploads_cannot_both_spend_last_plan_slot():
    from fastapi import HTTPException
    from app.modules.billing.entitlements import EntitlementService

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    org_id, user_id = str(uuid4()), str(uuid4())

    async def add_document(session):
        await session.execute(
            insert(Document).values(
                organization_id=org_id,
                owner_id=user_id,
                filename="quota.txt",
                original_filename="quota.txt",
                file_size=10,
                mime_type="text/plain",
                extension="txt",
                sha256_fingerprint="a" * 64,
                storage_path=f"quota/{uuid4()}.txt",
            )
        )

    try:
        async with sessions.begin() as session:
            await session.execute(
                insert(User).values(
                    id=user_id,
                    email=f"quota-{user_id}@example.com",
                    hashed_password="fixture-only",
                )
            )
            await session.execute(
                insert(Organization).values(
                    id=org_id, name="Quota fixture", slug=org_id
                )
            )
            await apply_tenant_context(session, org_id, user_id)
            for _ in range(19):
                await add_document(session)

        async def spend():
            try:
                async with sessions.begin() as session:
                    await apply_tenant_context(session, org_id, user_id)
                    await EntitlementService(session).require_upload(org_id, 10)
                    await add_document(session)
                return 201
            except HTTPException as error:
                return error.status_code

        assert sorted(await asyncio.gather(spend(), spend())) == [201, 402]
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            assert (
                await EntitlementService(session).describe(org_id)
            ).documents_this_month == 20
    finally:
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            await session.execute(
                delete(Document).where(Document.organization_id == org_id)
            )
            await session.execute(delete(Organization).where(Organization.id == org_id))
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_similarity_snapshot_rls(postgres_session, tenants):
    from app.modules.similarity.models import SimilarityAnalysis

    snapshots = []
    for tenant in tenants:
        await apply_tenant_context(postgres_session, tenant["org"], tenant["user"])
        snapshot = SimilarityAnalysis(
            organization_id=tenant["org"],
            document_id=tenant["documents"],
            document_version_id=tenant["document_versions"],
            pipeline_version="similarity-test",
            model_version="test",
            text_hash="a" * 64,
            corpus_state="UNAVAILABLE",
            corpus_version_count=0,
            index_version="test",
            completed_at=datetime.now(timezone.utc),
            truncated=False,
            metadata_json={},
        )
        postgres_session.add(snapshot)
        await postgres_session.flush()
        snapshots.append(snapshot.id)
    await apply_tenant_context(postgres_session, tenants[0]["org"], tenants[0]["user"])
    visible = (
        (
            await postgres_session.execute(
                select(SimilarityAnalysis.id).where(
                    SimilarityAnalysis.id.in_(snapshots)
                )
            )
        )
        .scalars()
        .all()
    )
    assert visible == [snapshots[0]]
    await apply_tenant_context(postgres_session, None, None)
    assert not (await postgres_session.execute(select(SimilarityAnalysis.id))).all()


async def test_document_core_database_rejects_cross_version_links_and_parser_mutation(
    postgres_session, tenants
):
    from types import SimpleNamespace
    from app.modules.processing.service import DocumentProcessingService
    from app.modules.processing.models import ProcessedDocument
    from app.modules.detection.models import (
        DetectionResult,
        DetectionSegment,
        DetectionVerdict,
    )
    from app.modules.evidence.models import EvidenceNode, EvidenceEdge
    from tests.test_document_intelligence import version_input, analyze

    own, other = tenants
    session = postgres_session
    await apply_tenant_context(session, own["org"], own["user"])
    org, user = SimpleNamespace(id=own["org"]), SimpleNamespace(id=own["user"])
    text1, text2 = (
        "Version one has a recorded observation [1].",
        "Version two contains a separate sentence.",
    )
    document, v1 = await version_input(session, org, user, text1)
    parsed, _ = await analyze(session, org, user, document, v1, text1)
    _, v2 = await version_input(session, org, user, text2, document)
    await analyze(session, org, user, document, v2, text2)
    detection = (
        await session.execute(
            select(DetectionResult).where(DetectionResult.document_version_id == v1.id)
        )
    ).scalar_one()
    nodes = []
    for version in (v1, v2):
        nodes.append(
            (
                await session.execute(
                    select(EvidenceNode).where(
                        EvidenceNode.document_version_id == version.id,
                        EvidenceNode.canonical_type == "DOCUMENT",
                    )
                )
            ).scalar_one()
        )
    mutations = [
        (
            update(ProcessedDocument)
            .where(ProcessedDocument.id == parsed.id)
            .values(cleaned_text="Overwritten"),
            "immutable",
        ),
        (
            update(ProcessedDocument)
            .where(ProcessedDocument.id == parsed.id)
            .values(parser_version="replacement"),
            "immutable",
        ),
        (
            update(DocumentVersion)
            .where(DocumentVersion.id == v1.id)
            .values(sha256_fingerprint="b" * 64),
            "immutable",
        ),
        (
            insert(Job).values(
                organization_id=own["org"],
                document_id=document.id,
                document_version_id=own["document_versions"],
                job_type=JobType.AI_DETECTION,
            ),
            "target mismatch",
        ),
        (
            insert(DetectionSegment).values(
                organization_id=own["org"],
                document_id=document.id,
                document_version_id=v2.id,
                detection_result_id=detection.id,
                segment_type="sentence",
                segment_index=99,
                text=text2,
                span_start=0,
                span_end=len(text2),
                verdict=DetectionVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0,
            ),
            "share one immutable target",
        ),
        (
            insert(EvidenceEdge).values(
                organization_id=own["org"],
                document_id=document.id,
                document_version_id=v1.id,
                source_node_id=nodes[0].node_id,
                target_node_id=nodes[1].node_id,
                edge_type="DERIVED_FROM",
                weight=1,
            ),
            "share the analysis target",
        ),
    ]
    for statement, message in mutations:
        async with session.begin_nested() as savepoint:
            with pytest.raises(DBAPIError, match=message):
                await session.execute(statement)
            await savepoint.rollback()
    await apply_tenant_context(session, other["org"], other["user"])
    assert not (
        await session.execute(
            select(ProcessedDocument.id).where(ProcessedDocument.id == parsed.id)
        )
    ).all()
    await apply_tenant_context(session, own["org"], own["user"])
    historical = await DocumentProcessingService(session).process_document(
        document, text1.encode(), str(v1.id)
    )
    assert historical.cleaned_text == text1


async def test_concurrent_document_version_analysis_keeps_inputs_and_findings_isolated():
    from app.modules.processing.service import DocumentProcessingService
    from app.modules.processing.models import ProcessedDocument
    from app.modules.documents.target import AnalysisTarget
    from app.modules.detection.models import DetectionResult
    from app.modules.evidence.service import EvidenceService
    from tests.test_document_intelligence import identity, version_input, analyze

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    text1 = "The first concurrent version has unique habitat observations [1]."
    text2 = (
        "The second concurrent version has distinct sediment measurements (Lee, 2024)."
    )
    try:
        async with sessions.begin() as session:
            org, user = await identity(session)
            await apply_tenant_context(session, str(org.id), str(user.id))
            document, v1 = await version_input(session, org, user, text1)
            _, v2 = await version_input(session, org, user, text2, document)
            org_id, user_id, doc_id, first, second = map(
                str, (org.id, user.id, document.id, v1.id, v2.id)
            )

        async def run(version_id, text_value):
            async with sessions.begin() as session:
                await apply_tenant_context(session, org_id, user_id)
                target = await AnalysisTarget.resolve(
                    session, org_id, doc_id, version_id
                )
                parsed, job = await analyze(
                    session, org, user, target.document, target.version, text_value
                )
                return parsed.id, parsed.cleaned_text, job.document_version_id

        results = await asyncio.gather(run(first, text1), run(second, text2))
        assert results[0][1:] == (text1, first) and results[1][1:] == (text2, second)
        assert results[0][0] != results[1][0]

        async def replay():
            async with sessions.begin() as session:
                await apply_tenant_context(session, org_id, user_id)
                target = await AnalysisTarget.resolve(session, org_id, doc_id, first)
                parsed = await DocumentProcessingService(session).process_document(
                    target.document, text1.encode(), first
                )
                return str(parsed.id)

        assert await asyncio.gather(replay(), replay()) == [str(results[0][0])] * 2
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            assert (
                await session.scalar(
                    select(func.count(ProcessedDocument.id)).where(
                        ProcessedDocument.document_id == doc_id
                    )
                )
                == 2
            )
            for version_id, expected in ((first, text1), (second, text2)):
                detection = (
                    await session.execute(
                        select(DetectionResult).where(
                            DetectionResult.document_version_id == version_id
                        )
                    )
                ).scalar_one()
                assert detection.segments[0].text == expected
                graph = await EvidenceService(session).build_evidence_graph(
                    doc_id, org_id, version_id
                )
                assert graph.complete and all(
                    node.document_version_id == version_id for node in graph.nodes
                )
            # Immutable fixtures are retained in this isolated verification DB.
            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(status=DocumentStatus.ARCHIVED)
            )
    finally:
        await engine.dispose()


async def test_concurrent_editor_saves_have_one_winner_and_safe_replay(monkeypatch):
    from fastapi import HTTPException
    from app.modules.documents.editor import EditorRevisionService
    from tests.test_editor_revisions import seed_editor

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions.begin() as session:
            # Seed identities without RLS document writes, then establish context.
            original_context = DocumentService.create_document

            async def create_with_context(service, doc_data, owner_id, org_id):
                await apply_tenant_context(service.db, org_id, owner_id)
                return await original_context(service, doc_data, owner_id, org_id)

            monkeypatch.setattr(DocumentService, "create_document", create_with_context)
            org, user, doc, version, storage, source = await seed_editor(
                session, monkeypatch
            )
            org_id, user_id, doc_id, base = map(
                str, (org.id, user.id, doc.id, version.id)
            )
        operations = [str(uuid4()), str(uuid4())]

        async def save(operation_id):
            async with sessions.begin() as session:
                await apply_tenant_context(session, org_id, user_id)
                try:
                    revision = await EditorRevisionService(session, storage).save(
                        doc_id,
                        org_id,
                        user_id,
                        base,
                        operation_id,
                        source + " Another sentence.",
                        [],
                    )
                    return str(revision.id), operation_id
                except HTTPException as error:
                    return error.status_code, operation_id

        results = await asyncio.gather(*(save(operation) for operation in operations))
        winners = [result for result in results if isinstance(result[0], str)]
        assert len(winners) == 1 and sum(result[0] == 409 for result in results) == 1
        assert await asyncio.gather(save(winners[0][1]), save(winners[0][1])) == [
            winners[0],
            winners[0],
        ]
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            assert (
                await session.scalar(
                    select(func.count(DocumentVersion.id)).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
                == 2
            )
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(
                        update(DocumentVersion)
                        .where(DocumentVersion.id == winners[0][0])
                        .values(operation_id=str(uuid4()))
                    )
            await session.execute(
                update(Document)
                .where(Document.id == doc_id)
                .values(status=DocumentStatus.ARCHIVED)
            )
    finally:
        await engine.dispose()


async def test_api_key_rls_authentication_and_concurrent_rotation(monkeypatch):
    from fastapi import HTTPException, Response
    from starlette.requests import Request
    from app.api.v1.api_keys import rotate
    from app.modules.auth.api_keys import KeyCreate, create_key, authenticate_api_key
    from app.modules.auth.models import ApiKey
    from app.core.dependencies import api_key_rate_limiter, api_tenant_rate_limiter

    # Rate-limiter arithmetic is tested separately; this test uses the real
    # non-owner PostgreSQL role for authentication and transaction races.
    async def admitted(key):
        return None

    monkeypatch.setattr(api_key_rate_limiter, "check_key", admitted)
    monkeypatch.setattr(api_tenant_rate_limiter, "check_key", admitted)
    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, org_id, other_org = (str(uuid4()) for _ in range(3))

    async def manager(session):
        await apply_tenant_context(session, org_id, user_id)
        user = await session.get(User, user_id)
        user.current_organization_id = org_id
        return user

    try:
        async with sessions.begin() as session:
            await session.execute(
                insert(User).values(
                    id=user_id,
                    email=f"api-race-{user_id}@example.com",
                    hashed_password="fixture-only",
                )
            )
            for org in [org_id, other_org]:
                await session.execute(
                    insert(Organization).values(
                        id=org, name="Key race fixture", slug=org
                    )
                )
            await session.execute(
                insert(Membership).values(
                    user_id=user_id,
                    organization_id=org_id,
                    role=OrganizationRole.OWNER,
                    joined_at=datetime.now(timezone.utc),
                )
            )
            user = await manager(session)
            issued = await create_key(
                session,
                user,
                KeyCreate(name="Concurrent fixture", scopes=["text:verify"]),
            )
            key_id, secret = issued.key.id, issued.secret

        async def use(secret):
            async with sessions() as session:
                request = Request(
                    {
                        "type": "http",
                        "method": "POST",
                        "path": "/api/v1/text/verify",
                        "headers": [],
                    }
                )
                try:
                    user = await authenticate_api_key(session, request, secret)
                    return user.current_api_key_id
                except HTTPException as error:
                    return error.status_code

        assert await asyncio.gather(*(use(secret) for _ in range(6))) == [key_id] * 6
        async with sessions.begin() as session:
            await apply_tenant_context(session, other_org, user_id)
            assert (
                await session.scalar(select(ApiKey.id).where(ApiKey.id == key_id))
                is None
            )
        assert await use(secret.replace(org_id, other_org)) == 401

        async def rotate_once():
            async with sessions.begin() as session:
                user = await manager(session)
                try:
                    return await rotate(UUID(key_id), Response(), user, session)
                except HTTPException as error:
                    return error.status_code

        results = await asyncio.gather(rotate_once(), rotate_once())
        assert sum(result == 409 for result in results) == 1
        winner = next(result for result in results if result != 409)
        assert await use(secret) == 401
        assert await use(winner.secret) == winner.key.id
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            assert (
                await session.scalar(
                    select(func.count(ApiKey.id)).where(
                        ApiKey.organization_id == org_id, ApiKey.is_active.is_(True)
                    )
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count(AuditLog.id)).where(
                        AuditLog.organization_id == org_id,
                        AuditLog.action == AuditAction.API_KEY_REVOKED,
                    )
                )
                == 1
            )
    finally:
        async with sessions.begin() as session:
            await apply_tenant_context(session, org_id, user_id)
            await session.execute(
                delete(Organization).where(Organization.id.in_([org_id, other_org]))
            )
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_identity_token_and_mfa_replay_are_atomic():
    import base64
    import hashlib
    import secrets
    import time
    from datetime import timedelta
    from fastapi import HTTPException
    from app.modules.auth import identity
    from app.modules.auth.identity_models import IdentityToken

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id, token = str(uuid4()), secrets.token_urlsafe(32)
    totp_secret = secrets.token_bytes(20)
    try:
        async with sessions.begin() as session:
            await session.execute(
                insert(User).values(
                    id=user_id,
                    email=f"identity-race-{user_id}@example.com",
                    hashed_password="fixture-only",
                    mfa_enabled=True,
                    mfa_secret=identity.cipher()
                    .encrypt(base64.b32encode(totp_secret))
                    .decode(),
                )
            )
            session.add(
                IdentityToken(
                    user_id=user_id,
                    purpose="verify_email",
                    digest=hashlib.sha256(token.encode()).hexdigest(),
                    expires_at=identity.now() + timedelta(minutes=10),
                )
            )
            user = await identity.lock_user(session, user_id)
            recovery = identity.recovery_codes(user)

        async def verify_email_once():
            async with sessions.begin() as session:
                try:
                    await identity.consume_email(session, token, "verify_email")
                    return 200
                except HTTPException as error:
                    return error.status_code

        assert sorted(
            await asyncio.gather(verify_email_once(), verify_email_once())
        ) == [200, 400]

        async def factor_once(code):
            async with sessions.begin() as session:
                user = await identity.lock_user(session, user_id)
                try:
                    await identity.require_mfa(session, user, code)
                    return 200
                except HTTPException as error:
                    return error.status_code

        code = identity.totp(totp_secret).generate(time.time()).decode()
        assert sorted(await asyncio.gather(factor_once(code), factor_once(code))) == [
            200,
            401,
        ]
        assert sorted(
            await asyncio.gather(factor_once(recovery[0]), factor_once(recovery[0]))
        ) == [200, 401]
        async with sessions.begin() as session:
            user = await identity.lock_user(session, user_id)
            assert user.is_verified
            await apply_tenant_context(session, None, user_id)
            events = (
                await session.scalars(
                    select(AuditLog).where(AuditLog.user_id == user_id)
                )
            ).all()
            assert (
                sum(
                    event.details.get("event") == "verify_email_completed"
                    for event in events
                )
                == 1
            )
            assert (
                sum(
                    event.details.get("event") == "mfa_recovery_code_used"
                    for event in events
                )
                == 1
            )
    finally:
        async with sessions.begin() as session:
            await apply_tenant_context(session, None, user_id)
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_concurrent_session_revocation_cannot_resurrect_refresh_family():
    from fastapi import HTTPException
    from app.api.v1.identity import revoke_session
    from app.modules.auth import identity
    from app.modules.auth.models import RefreshToken
    from app.modules.auth.service import AuthService
    from app.core.security import decode_refresh_token

    assert POSTGRES_URL is not None
    engine = create_async_engine(POSTGRES_URL)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = str(uuid4())
    try:
        async with sessions.begin() as session:
            await session.execute(
                insert(User).values(
                    id=user_id,
                    email=f"session-race-{user_id}@example.com",
                    hashed_password="fixture-only",
                )
            )
            user = await identity.lock_user(session, user_id)
            tokens = await AuthService(session).create_token_pair(user)
            family = decode_refresh_token(tokens["refresh_token"]).family

        async def refresh_once():
            async with sessions.begin() as session:
                try:
                    await AuthService(session).refresh_access_token(
                        tokens["refresh_token"]
                    )
                    return 200
                except HTTPException as error:
                    return error.status_code

        async def revoke_once():
            async with sessions.begin() as session:
                user = await session.get(User, user_id)
                user.current_session_family = family
                await revoke_session(family, user, session)

        result, _ = await asyncio.gather(refresh_once(), revoke_once())
        assert result in {200, 401}
        async with sessions.begin() as session:
            assert (
                await session.scalar(
                    select(func.count(RefreshToken.id)).where(
                        RefreshToken.user_id == user_id,
                        RefreshToken.token_family == family,
                        RefreshToken.revoked_at.is_(None),
                    )
                )
                == 0
            )
    finally:
        async with sessions.begin() as session:
            await apply_tenant_context(session, None, user_id)
            await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()


async def test_privacy_erasure_authority_immutability_and_retry(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    await apply_tenant_context(db, own["org"], own["user"])
    # A caller-controlled context string never bypasses immutable history.
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text("SELECT set_config('app.privacy_request','forged',true)")
            )
            await db.execute(
                delete(DocumentVersion).where(
                    DocumentVersion.id == own["document_versions"]
                )
            )
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                text("SELECT app.privacy_request(:id,'document',:target,:digest)"),
                {"id": str(uuid4()), "target": other["documents"], "digest": "a" * 64},
            )
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(text("INSERT INTO privacy_erasures(id) VALUES ('forged')"))
    request_id = str(uuid4())
    args = {"id": request_id, "target": own["documents"], "digest": "b" * 64}
    assert (
        await db.scalar(
            text("SELECT app.privacy_request(:id,'document',:target,:digest)"), args
        )
        == request_id
    )
    # Read fencing takes effect before asynchronous removal starts.
    assert not await db.scalar(
        select(Document.id).where(Document.id == own["documents"])
    )
    assert not await db.scalar(select(Job.id).where(Job.id == own["jobs"]))
    assert (
        await db.scalar(
            text("SELECT app.privacy_request(:id,'document',:target,:digest)"),
            {**args, "id": str(uuid4())},
        )
        == request_id
    )
    record = await db.scalar(
        text("SELECT app.privacy_erase_database(:id)"), {"id": request_id}
    )
    assert record["status"] == "ERASING_OBJECTS"
    assert record["document_ids"] == [own["documents"]]
    assert record["object_keys"] == [f"uploads/{own['org']}/{own['documents']}.txt"]
    assert (
        await db.scalar(
            text("SELECT app.privacy_result(:id,false,0)"), {"id": request_id}
        )
        == "FAILED"
    )
    # A fast successful object pass cannot bypass the issued PUT expiration window.
    assert (
        await db.scalar(
            text("SELECT app.privacy_result(:id,true,1)"), {"id": request_id}
        )
        == "VERIFYING"
    )
    assert (
        await db.scalar(
            text("SELECT app.privacy_erase_database(:id)"), {"id": request_id}
        )
    )["status"] == "VERIFYING"
    assert (
        await db.scalar(
            text("SELECT app.privacy_receipt(:id,:digest)"),
            {"id": request_id, "digest": "wrong"},
        )
        is None
    )
    receipt = await db.scalar(
        text("SELECT app.privacy_receipt(:id,:digest)"),
        {"id": request_id, "digest": "b" * 64},
    )
    assert receipt["status"] == "VERIFYING" and "object_keys" not in receipt
    await apply_tenant_context(db, other["org"], other["user"])
    assert (
        await db.scalar(select(Document.id).where(Document.id == other["documents"]))
        == other["documents"]
    )
    assert not await db.scalar(
        text("SELECT id FROM privacy_erasures WHERE id=:id"), {"id": request_id}
    )


async def test_account_erasure_removes_identity_and_personal_workspace(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    await apply_tenant_context(db, own["org"], own["user"])
    request_id = str(uuid4())
    await db.execute(
        text("SELECT app.privacy_request(:id,'account',:target,:digest)"),
        {"id": request_id, "target": own["user"], "digest": "c" * 64},
    )
    assert not (await db.scalar(select(User.is_active).where(User.id == own["user"])))
    await db.execute(text("SELECT app.privacy_erase_database(:id)"), {"id": request_id})
    assert not await db.scalar(select(User.id).where(User.id == own["user"]))
    assert not await db.scalar(
        select(Organization.id).where(Organization.id == own["org"])
    )
    assert (
        await db.scalar(select(User.id).where(User.id == other["user"]))
        == other["user"]
    )


async def test_account_erasure_preserves_shared_content_but_redacts_actor(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    await apply_tenant_context(db, other["org"], own["user"])
    shared_version = str(uuid4())
    await db.execute(
        insert(DocumentVersion).values(
            id=shared_version,
            document_id=other["documents"],
            version_number=2,
            storage_path=f"versions/{other['org']}/{other['documents']}/shared.txt",
            content_hash="b" * 64,
            sha256_fingerprint="b" * 64,
            created_by_id=own["user"],
            uploaded_by_id=own["user"],
            previous_version_id=other["document_versions"],
        )
    )
    await apply_tenant_context(db, own["org"], own["user"])
    request_id = str(uuid4())
    await db.execute(
        text("SELECT app.privacy_request(:id,'account',:target,:digest)"),
        {"id": request_id, "target": own["user"], "digest": "d" * 64},
    )
    await db.execute(text("SELECT app.privacy_erase_database(:id)"), {"id": request_id})
    await apply_tenant_context(db, other["org"], other["user"])
    version = (
        await db.execute(
            select(DocumentVersion).where(DocumentVersion.id == shared_version)
        )
    ).scalar_one()
    assert version.created_by_id is None and version.uploaded_by_id is None
    assert (
        version.content_hash == "b" * 64
        and version.previous_version_id == other["document_versions"]
    )
    assert (
        await db.scalar(select(Document.id).where(Document.id == other["documents"]))
        == other["documents"]
    )
    # An ordinary author cannot create unattributed content even though historical
    # attribution becomes nullable after an authorized account erasure.
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                insert(DocumentVersion).values(
                    id=str(uuid4()),
                    document_id=other["documents"],
                    version_number=3,
                    storage_path=f"versions/{other['org']}/{other['documents']}/unattributed.txt",
                    content_hash="c" * 64,
                    sha256_fingerprint="c" * 64,
                    created_by_id=None,
                )
            )


async def test_account_erasure_requires_shared_owner_transfer(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    await db.execute(
        insert(Membership).values(
            user_id=other["user"],
            organization_id=own["org"],
            role=OrganizationRole.RESEARCHER,
            joined_at=datetime.now(timezone.utc),
        )
    )
    await apply_tenant_context(db, own["org"], own["user"])
    with pytest.raises(DBAPIError, match="transfer workspace ownership"):
        async with db.begin_nested():
            await db.execute(
                text("SELECT app.privacy_request(:id,'account',:target,:digest)"),
                {"id": str(uuid4()), "target": own["user"], "digest": "e" * 64},
            )
    assert await db.scalar(select(User.is_active).where(User.id == own["user"]))
    request_id = str(uuid4())
    await db.execute(
        text("SELECT app.privacy_request(:id,'organization',:target,:digest)"),
        {"id": request_id, "target": own["org"], "digest": "e" * 64},
    )
    await db.execute(text("SELECT app.privacy_erase_database(:id)"), {"id": request_id})
    assert not await db.scalar(
        select(Organization.id).where(Organization.id == own["org"])
    )
    assert await db.scalar(select(User.is_active).where(User.id == other["user"]))


@pytest.mark.skipif(
    os.getenv("RUN_STORAGE_INTEGRATION") != "1",
    reason="Requires isolated MinIO and worker-only maintenance credentials",
)
async def test_legacy_migration_and_erasure_use_actual_minio(postgres_session, tenants):
    import io
    import hashlib
    from app.api.v1.documents import get_storage_client
    from app.core.config import settings
    from app.modules.privacy.storage import maintenance_client, migrate_legacy_version
    from app.modules.privacy.service import erase_objects

    db = postgres_session
    own = tenants[0]
    await apply_tenant_context(db, own["org"], own["user"])
    doc_id, version_id = str(uuid4()), str(uuid4())
    content = b"Legacy immutable source fixture with a verifiable fingerprint."
    fingerprint = hashlib.sha256(content).hexdigest()
    source = f"uploads/{own['org']}/{own['user']}/{uuid4()}.txt"
    destination = (
        f"versions/legacy/{own['org']}/{doc_id}/{version_id}/{fingerprint}.txt"
    )
    app_storage, storage = get_storage_client(), maintenance_client()
    await db.execute(
        insert(Document).values(
            id=doc_id,
            organization_id=own["org"],
            owner_id=own["user"],
            filename="legacy.txt",
            original_filename="legacy.txt",
            file_size=len(content),
            mime_type="text/plain",
            extension="txt",
            sha256_fingerprint=fingerprint,
            storage_path=source,
        )
    )
    await db.execute(
        insert(DocumentVersion).values(
            id=version_id,
            document_id=doc_id,
            version_number=1,
            storage_path=source,
            content_hash=fingerprint,
            sha256_fingerprint=fingerprint,
            created_by_id=own["user"],
        )
    )
    try:
        app_storage.put_object(
            settings.MINIO_BUCKET, source, io.BytesIO(b"changed bytes"), 13
        )
        with pytest.raises(ValueError, match="recorded fingerprint"):
            await migrate_legacy_version(db, storage, doc_id, own["org"], version_id)
        assert (
            await db.scalar(
                select(DocumentVersion.storage_path).where(
                    DocumentVersion.id == version_id
                )
            )
            == source
        )
        app_storage.put_object(
            settings.MINIO_BUCKET, source, io.BytesIO(content), len(content)
        )
        from app.modules.jobs.models import JobStatus

        job_id = str(uuid4())
        await db.execute(
            insert(Job).values(
                id=job_id,
                organization_id=own["org"],
                document_id=doc_id,
                document_version_id=version_id,
                job_type=JobType.DOCUMENT_PROCESSING,
                status=JobStatus.PENDING,
            )
        )
        candidates = (
            await db.execute(text("SELECT * FROM app.storage_legacy_candidates()"))
        ).all()
        assert version_id not in {candidate.version_id for candidate in candidates}
        with pytest.raises(DBAPIError, match="active jobs"):
            async with db.begin_nested():
                await migrate_legacy_version(
                    db, storage, doc_id, own["org"], version_id
                )
        await db.execute(
            update(Job).where(Job.id == job_id).values(status=JobStatus.COMPLETED)
        )
        assert await migrate_legacy_version(db, storage, doc_id, own["org"], version_id)
        assert not await migrate_legacy_version(
            db, storage, doc_id, own["org"], version_id
        )
        assert (
            await db.scalar(
                select(DocumentVersion.storage_path).where(
                    DocumentVersion.id == version_id
                )
            )
            == destination
        )
        assert storage.stat_object(settings.MINIO_BUCKET, source).size == len(content)
        assert await db.scalar(
            text("SELECT app.storage_referenced(:key)"), {"key": destination}
        )
        assert not await db.scalar(
            text("SELECT app.storage_referenced(:key)"), {"key": source}
        )
        await apply_tenant_context(db, own["org"], own["user"])
        request_id = str(uuid4())
        await db.execute(
            text("SELECT app.privacy_request(:id,'document',:target,:digest)"),
            {"id": request_id, "target": doc_id, "digest": "f" * 64},
        )
        record = await db.scalar(
            text("SELECT app.privacy_erase_database(:id)"), {"id": request_id}
        )
        assert {source, destination} <= set(record["object_keys"])
        multipart_id = app_storage._create_multipart_upload(
            settings.MINIO_BUCKET, source, {}
        )
        app_storage._upload_part(
            settings.MINIO_BUCKET,
            source,
            b"partial private fixture",
            {},
            multipart_id,
            1,
        )
        from app.modules.privacy.multipart import multipart_uploads

        assert len(list(multipart_uploads(storage, {source}, set()))) == 1
        assert erase_objects(storage, record) == 3
        assert not list(multipart_uploads(storage, {source}, set()))
        assert erase_objects(storage, record) == 0
        for key in [source, destination]:
            assert not list(
                storage.list_objects(
                    settings.MINIO_BUCKET,
                    prefix=key,
                    recursive=True,
                    include_version=True,
                )
            )
    finally:
        for key in [source, destination]:
            storage.remove_object(settings.MINIO_BUCKET, key)


async def test_privacy_removes_usage_receipts_without_refunding_completed_quota(
    postgres_session, tenants
):
    from app.modules.billing.models import UsageOperation
    from app.modules.billing.usage import UsageService, now

    db, own = postgres_session, tenants[0]
    await apply_tenant_context(db, own["org"], own["user"])
    service = UsageService(db)
    first, _ = await service.reserve(
        own["org"],
        own["user"],
        "editorial",
        str(uuid4()),
        {"text": "private fixture"},
        document_id=own["documents"],
    )
    await service.settle(
        str(first.id),
        own["org"],
        success=True,
        outcome="completed",
        response={"text": "private fixture"},
    )
    await service.reserve(
        own["org"],
        own["user"],
        "editorial",
        str(uuid4()),
        {"text": "pending private fixture"},
        document_id=own["documents"],
    )
    request_id = str(uuid4())
    await db.execute(
        text("SELECT app.privacy_request(:id,'document',:target,:digest)"),
        {"id": request_id, "target": own["documents"], "digest": "e" * 64},
    )
    await db.execute(text("SELECT app.privacy_erase_database(:id)"), {"id": request_id})
    assert (
        await db.scalar(
            select(func.count())
            .select_from(UsageOperation)
            .where(UsageOperation.organization_id == own["org"])
        )
        == 0
    )
    db.expire_all()
    bucket = await service.bucket(own["org"], now().strftime("%Y-%m"), "editorial")
    assert (bucket.committed, bucket.reserved) == (1, 0)


async def test_usage_reconciliation_releases_crashes_and_expires_cached_text(
    postgres_session, tenants, monkeypatch
):
    from datetime import timedelta
    from app.modules.billing import maintenance
    from app.modules.billing.models import UsageOperation
    from app.modules.billing.usage import UsageService, now
    from app.modules.jobs.models import JobStatus

    db, own = postgres_session, tenants[0]
    await apply_tenant_context(db, own["org"], own["user"])
    service = UsageService(db)
    cache, _ = await service.reserve(
        own["org"], own["user"], "text_analyze", str(uuid4()), {}
    )
    await service.settle(
        str(cache.id),
        own["org"],
        success=True,
        outcome="completed",
        response={"private": "fixture"},
    )
    cache.response_expires_at = now() - timedelta(seconds=1)
    crash, _ = await service.reserve(
        own["org"], own["user"], "text_verify", str(uuid4()), {}
    )
    job, _ = await service.reserve(
        own["org"],
        own["user"],
        "document_processing",
        own["jobs"],
        {},
        job_id=own["jobs"],
    )
    crash.expires_at = job.expires_at = now() - timedelta(seconds=1)
    await db.flush()

    class Scope:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr(maintenance, "AsyncSessionLocal", Scope)
    result = await maintenance.maintain_usage()
    assert result["released"] >= 2 and result["receipts_expired"] >= 1
    await apply_tenant_context(db, own["org"], own["user"])
    db.expire_all()
    records = list(
        (
            await db.scalars(
                select(UsageOperation).where(
                    UsageOperation.organization_id == own["org"]
                )
            )
        ).all()
    )
    assert sorted(record.status for record in records) == [
        "COMMITTED",
        "RELEASED",
        "RELEASED",
    ]
    assert all(record.response_ciphertext is None for record in records)
    assert (
        await db.scalar(select(Job.status).where(Job.id == own["jobs"]))
        == JobStatus.FAILED
    )
    assert (
        await service.bucket(own["org"], now().strftime("%Y-%m"), "text_analyze")
    ).committed == 1
