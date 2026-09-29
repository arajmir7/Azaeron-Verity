"""Durable conversation admission, scoped authorization and replayable events."""

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func, delete

from app.core.permissions import Permission, require_member_permission
from app.modules.agent.models import (
    Conversation,
    Message,
    AgentRun,
    AgentEvent,
    ToolCall,
    ToolResult,
    DocumentAttachment,
)
from app.modules.agent.schemas import MessageCreate
from app.modules.agent.tools import attach
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.auth.models import User, RefreshToken
from app.modules.billing.usage import UsageService, fingerprint, aware
from app.modules.organizations.models import Organization

TERMINAL = {"COMPLETED", "FAILED", "UNAVAILABLE", "CANCELLED"}


def view(record):
    return {
        column.name: getattr(record, column.name) for column in record.__table__.columns
    }


def run_view(run):
    return {
        key: value
        for key, value in view(run).items()
        if key
        not in {
            "session_family",
            "session_version",
            "usage_operation_id",
            "request",
            "fingerprint",
        }
    }


async def authorize(db, org, actor, *, family=None, version=None):
    await require_member_permission(db, org, actor, Permission.EDITORIAL_WRITE)
    user = await db.scalar(
        select(User).where(
            User.id == actor, User.is_active.is_(True), User.erasure_pending.is_(False)
        )
    )
    workspace = await db.scalar(
        select(Organization.id).where(
            Organization.id == org,
            Organization.is_active.is_(True),
            Organization.erasure_pending.is_(False),
        )
    )
    if not user or not workspace:
        raise HTTPException(403, "Workspace access is unavailable")
    if family is not None:
        active = await db.scalar(
            select(RefreshToken.id)
            .where(
                RefreshToken.user_id == actor,
                RefreshToken.token_family == family,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .limit(1)
        )
        if not active or user.session_version != version:
            raise HTTPException(401, "Session expired or revoked")


async def conversation(db, org, actor, identifier, *, lock=False):
    query = select(Conversation).where(
        Conversation.id == identifier,
        Conversation.organization_id == org,
        Conversation.user_id == actor,
    )
    if lock:
        query = query.with_for_update()
    result = await db.scalar(query.execution_options(populate_existing=True))
    if not result:
        raise HTTPException(404, "Conversation not found")
    return result


async def event(db, run, kind, payload):
    # Callers serialize state transitions on the run row. No model call holds it.
    count = await db.scalar(
        select(func.max(AgentEvent.sequence)).where(
            AgentEvent.run_id == run.id,
            AgentEvent.organization_id == run.organization_id,
            AgentEvent.user_id == run.user_id,
        )
    )
    row = AgentEvent(
        organization_id=run.organization_id,
        user_id=run.user_id,
        run_id=run.id,
        sequence=(count or 0) + 1,
        kind=kind,
        payload=payload,
    )
    db.add(row)
    await db.flush()
    return row


async def create_conversation(db, org, actor, title):
    await authorize(db, org, actor)
    await UsageService(db).lock(org)
    count = await db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.organization_id == org, Conversation.user_id == actor)
    )
    if (count or 0) >= 200:
        raise HTTPException(
            402, "Conversation limit reached; delete an old conversation"
        )
    row = Conversation(organization_id=org, user_id=actor, title=title)
    db.add(row)
    await db.flush()
    return row


async def submit(db, user, conversation_id, data: MessageCreate):
    org, actor = str(user.current_organization_id), str(user.id)
    await authorize(db, org, actor)
    await UsageService(db).lock(org)
    conv = await conversation(db, org, actor, conversation_id, lock=True)
    payload = {"conversation_id": conversation_id, **data.model_dump(mode="json")}
    digest = fingerprint(payload)
    prior = await db.scalar(
        select(AgentRun).where(
            AgentRun.organization_id == org,
            AgentRun.user_id == actor,
            AgentRun.operation_id == str(data.operation_id),
        )
    )
    if prior:
        if prior.fingerprint != digest:
            raise HTTPException(409, "Operation ID belongs to a different message")
        return prior, True
    active = (
        await db.scalars(
            select(AgentRun)
            .where(
                AgentRun.organization_id == org,
                AgentRun.user_id == actor,
                AgentRun.conversation_id == conversation_id,
                AgentRun.status.in_(["PENDING", "RUNNING"]),
            )
            .with_for_update()
        )
    ).all()
    for run in active:
        if aware(run.expires_at) > datetime.now(timezone.utc):
            raise HTTPException(
                409, "Stop the current response before starting another"
            )
        run.status, run.error_code = "FAILED", "run_expired"
        await event(db, run, "done", {"status": "FAILED", "code": "run_expired"})
        await UsageService(db).settle(
            run.usage_operation_id, org, success=False, outcome="outcome_unknown"
        )
    count = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.organization_id == org,
            Message.user_id == actor,
        )
    )
    if (count or 0) >= 400:
        raise HTTPException(
            402, "Conversation message limit reached; start a new conversation"
        )
    if data.replaces_message_id:
        previous = await db.scalar(
            select(Message.id).where(
                Message.id == str(data.replaces_message_id),
                Message.conversation_id == conversation_id,
                Message.organization_id == org,
                Message.user_id == actor,
                Message.role == "user",
            )
        )
        if previous is None:
            raise HTTPException(404, "Original prompt not found")
    usage, replay = await UsageService(db).reserve(
        org,
        actor,
        "ai_tool" if data.tool else "ai_run",
        str(data.operation_id),
        payload,
    )
    if replay:
        raise HTTPException(409, "This operation has already been recorded")
    message = Message(
        id=str(uuid4()),
        organization_id=org,
        user_id=actor,
        conversation_id=conversation_id,
        sequence=(count or 0) + 1,
        role="user",
        content=data.content,
        replaces_message_id=(
            str(data.replaces_message_id) if data.replaces_message_id else None
        ),
    )
    db.add(message)
    await db.flush()
    run = AgentRun(
        id=str(uuid4()),
        organization_id=org,
        user_id=actor,
        conversation_id=conversation_id,
        message_id=message.id,
        operation_id=str(data.operation_id),
        fingerprint=digest,
        status="PENDING",
        request=data.model_dump(mode="json"),
        usage_operation_id=str(usage.id),
        session_family=user.current_session_family,
        session_version=user.session_version,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
    db.add(run)
    await db.flush()
    for attachment in data.attachments:
        await attach(db, run, attachment)
    conv.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await event(db, run, "queued", {"run_id": run.id, "status": run.status})
    await AuditService(db).log(
        AuditAction.WRITING_SUGGESTIONS,
        "agent_run",
        run.id,
        details={
            "tool": data.tool.name if data.tool else None,
            "policy_revision": "verity-agent-1",
        },
        user_id=actor,
        organization_id=org,
    )
    return run, False


async def get_run(db, org, actor, run_id, *, lock=False):
    query = select(AgentRun).where(
        AgentRun.id == run_id,
        AgentRun.organization_id == org,
        AgentRun.user_id == actor,
    )
    if lock:
        query = query.with_for_update()
    run = await db.scalar(query.execution_options(populate_existing=True))
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


async def cancel(db, org, actor, run_id):
    await authorize(db, org, actor)
    await UsageService(db).lock(org)
    run = await get_run(db, org, actor, run_id, lock=True)
    if run.status not in TERMINAL:
        pending = run.status == "PENDING"
        run.status = "CANCELLED"
        run.completed_at = datetime.now(timezone.utc)
        await event(db, run, "done", {"status": "CANCELLED"})
        if pending:
            await UsageService(db).settle(
                run.usage_operation_id, org, success=False, outcome="cancelled"
            )
    return run_view(run)


async def expire_run(db, org, actor, run):
    """Reconcile a crashed worker on read/reconnect without repeating its work."""
    if run.status in TERMINAL or aware(run.expires_at) > datetime.now(timezone.utc):
        return run
    await UsageService(db).lock(org)
    run = await get_run(db, org, actor, run.id, lock=True)
    if run.status not in TERMINAL and aware(run.expires_at) <= datetime.now(
        timezone.utc
    ):
        run.status, run.error_code = "FAILED", "run_expired"
        run.completed_at = datetime.now(timezone.utc)
        await UsageService(db).settle(
            run.usage_operation_id, org, success=False, outcome="outcome_unknown"
        )
        await event(
            db,
            run,
            "done",
            {
                "status": "FAILED",
                "code": "run_expired",
                "discard_provisional_output": True,
            },
        )
    return run


async def detail(db, org, actor, identifier):
    conv = await conversation(db, org, actor, identifier)
    result = view(conv)
    for name, model in (
        ("messages", Message),
        ("runs", AgentRun),
        ("attachments", DocumentAttachment),
    ):
        rows = (
            await db.scalars(
                select(model)
                .where(
                    model.organization_id == org,
                    model.user_id == actor,
                    model.conversation_id == identifier,
                )
                .order_by(
                    Message.sequence if model is Message else model.created_at, model.id
                )
                .limit(500)
            )
        ).all()
        if name == "runs":
            rows = [await expire_run(db, org, actor, row) for row in rows]
        result[name] = [run_view(row) if name == "runs" else view(row) for row in rows]
    run_ids = [row["id"] for row in result["runs"]]
    calls = (
        await db.scalars(
            select(ToolCall)
            .where(
                ToolCall.organization_id == org,
                ToolCall.user_id == actor,
                ToolCall.run_id.in_(run_ids),
            )
            .order_by(ToolCall.created_at, ToolCall.id)
        )
    ).all()
    result["tool_calls"] = [view(row) for row in calls]
    results = (
        await db.scalars(
            select(ToolResult).where(
                ToolResult.organization_id == org,
                ToolResult.user_id == actor,
                ToolResult.tool_call_id.in_([row.id for row in calls]),
            )
        )
    ).all()
    result["tool_results"] = [view(row) for row in results]
    return result
