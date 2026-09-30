"""Real PostgreSQL red-team checks for the new agent boundary."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError

from app.core.database import apply_tenant_context
from app.modules.agent.models import (
    Conversation,
    Message,
    DocumentAttachment,
    ActionReceipt,
)
from tests.integration import test_postgres_rls as fixtures

POSTGRES_URL = fixtures.POSTGRES_URL
postgres_session = fixtures.postgres_session
tenants = fixtures.tenants

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="Real PostgreSQL required")


async def create_chat(db, tenant):
    await apply_tenant_context(db, tenant["org"], tenant["user"])
    chat = Conversation(
        organization_id=tenant["org"], user_id=tenant["user"], title="Private source"
    )
    db.add(chat)
    await db.flush()
    message = Message(
        organization_id=tenant["org"],
        user_id=tenant["user"],
        conversation_id=chat.id,
        role="user",
        sequence=1,
        content="Never leak this message",
    )
    db.add(message)
    await db.flush()
    return chat, message


async def test_all_agent_tables_force_actor_and_tenant_rls(postgres_session, tenants):
    db = postgres_session
    chats = [await create_chat(db, tenant) for tenant in tenants]
    rows = (
        await db.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname LIKE 'ai_%' AND relkind='r'"
            )
        )
    ).all()
    assert len(rows) >= 8 and all(
        row.relrowsecurity and row.relforcerowsecurity for row in rows
    )
    await apply_tenant_context(db, tenants[0]["org"], tenants[0]["user"])
    assert list(await db.scalars(select(Conversation.id))) == [chats[0][0].id]
    assert list(await db.scalars(select(Message.id))) == [chats[0][1].id]
    await apply_tenant_context(db, tenants[0]["org"], tenants[1]["user"])
    assert not list(await db.scalars(select(Conversation.id)))
    await apply_tenant_context(db, None, None)
    assert not list(await db.scalars(select(Message.id)))


async def test_attachment_and_parent_forgery_rejected_by_database(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    chat, message = await create_chat(db, own)
    for document, version in (
        (other["documents"], other["document_versions"]),
        (own["documents"], other["document_versions"]),
    ):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    insert(DocumentAttachment).values(
                        id=str(uuid4()),
                        organization_id=own["org"],
                        user_id=own["user"],
                        conversation_id=chat.id,
                        document_id=document,
                        document_version_id=version,
                        input_sha256="a" * 64,
                    )
                )
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(Message)
                .where(Message.id == message.id)
                .values(content="rewritten audit history")
            )
    assert (
        await db.scalar(select(Message).where(Message.id == message.id))
    ).content == "Never leak this message"


async def test_receipt_candidate_immutable_and_cannot_forge_result(
    postgres_session, tenants
):
    db = postgres_session
    own, other = tenants
    await apply_tenant_context(db, own["org"], own["user"])
    receipt = ActionReceipt(
        organization_id=own["org"],
        user_id=own["user"],
        operation_id=str(uuid4()),
        document_id=own["documents"],
        source_version_id=own["document_versions"],
        input_sha256="a" * 64,
        candidate_sha256="b" * 64,
        candidate_text="Review this",
        candidate_diff="diff",
        model_evidence={},
        policy_revision="fixture",
        tool_calls=[],
        protected_spans=[],
        verification={"outcome": "REJECTED"},
        decision="PENDING",
    )
    db.add(receipt)
    await db.flush()
    for values in (
        {"candidate_text": "tampered"},
        {
            "decision": "ACCEPTED",
            "decided_at": datetime.now(timezone.utc),
            "result_version_id": other["document_versions"],
            "result_sha256": "b" * 64,
        },
    ):
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    update(ActionReceipt)
                    .where(ActionReceipt.id == receipt.id)
                    .values(**values)
                )
    await db.execute(
        update(ActionReceipt)
        .where(ActionReceipt.id == receipt.id)
        .values(decision="REJECTED", decided_at=datetime.now(timezone.utc))
    )
    with pytest.raises(DBAPIError):
        async with db.begin_nested():
            await db.execute(
                update(ActionReceipt)
                .where(ActionReceipt.id == receipt.id)
                .values(decision="PENDING")
            )


async def test_document_erasure_covers_chat_and_receipt_derivatives(
    postgres_session, tenants
):
    db = postgres_session
    own = tenants[0]
    chat, _ = await create_chat(db, own)
    db.add(
        DocumentAttachment(
            organization_id=own["org"],
            user_id=own["user"],
            conversation_id=chat.id,
            document_id=own["documents"],
            document_version_id=own["document_versions"],
            input_sha256="a" * 64,
        )
    )
    from app.modules.agent.models import VoiceProfile

    profile = VoiceProfile(
        organization_id=own["org"],
        user_id=own["user"],
        name="Owned",
        samples=[
            {
                "document_id": own["documents"],
                "document_version_id": own["document_versions"],
                "approved_by": own["user"],
                "input_sha256": "a" * 64,
            }
        ],
        style={},
        policy_revision="test",
    )
    db.add(profile)
    await db.flush()
    assert await db.scalar(select(Conversation.id).where(Conversation.id == chat.id))
    request_id = str(uuid4())
    await db.execute(
        text("SELECT app.privacy_request(:id,'document',:target,:digest)"),
        {"id": request_id, "target": own["documents"], "digest": "b" * 64},
    )
    assert not await db.scalar(
        select(Conversation.id).where(Conversation.id == chat.id)
    )
    assert not await db.scalar(
        select(Message.id).where(Message.conversation_id == chat.id)
    )
    assert not await db.scalar(
        select(VoiceProfile.id).where(VoiceProfile.id == profile.id)
    )
    await db.execute(text("SELECT app.privacy_erase_database(:id)"), {"id": request_id})
    assert not await db.scalar(
        select(Conversation.id).where(Conversation.id == chat.id)
    )
