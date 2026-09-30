"""Actor-private conversations, replayable SSE and explicit receipt decisions."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete

from app.core.database import get_db, AsyncSessionLocal, apply_tenant_context
from app.core.dependencies import (
    get_current_user,
    require_active_organization,
    editorial_rate_limiter,
)
from app.core.queue import QueueUnavailable, enqueue_with_retry
from app.modules.agent.models import (
    Conversation,
    AgentEvent,
    ActionReceipt,
    AgentRun,
    VoiceProfile,
)
from app.modules.agent.schemas import (
    ConversationCreate,
    MessageCreate,
    ReceiptDecision,
    VoiceCreate,
)
from app.modules.agent import service
from app.modules.agent.receipts import decide, receipt_view
from app.modules.billing.usage import UsageService
from app.modules.documents.target import AnalysisTarget

router = APIRouter(
    prefix="/ai",
    tags=["Azaeron AI"],
    dependencies=[
        Depends(require_active_organization),
        Depends(editorial_rate_limiter),
    ],
)


async def actor(user=Depends(get_current_user), db=Depends(get_db, scope="function")):
    if user.current_api_key_id:
        raise HTTPException(403, "Agent operations require an interactive user session")
    await service.authorize(db, user.current_organization_id, str(user.id))
    return user


@router.get("/conversations")
async def list_conversations(
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0, le=10000),
    user=Depends(actor),
    db=Depends(get_db, scope="function"),
):
    rows = (
        await db.scalars(
            select(Conversation)
            .where(
                Conversation.organization_id == user.current_organization_id,
                Conversation.user_id == str(user.id),
                Conversation.title.contains(q, autoescape=True),
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id)
            .offset(offset)
            .limit(50)
        )
    ).all()
    return {"items": [service.view(row) for row in rows], "offset": offset, "limit": 50}


@router.post("/conversations", status_code=201)
async def create_conversation(
    data: ConversationCreate, user=Depends(actor), db=Depends(get_db, scope="function")
):
    return service.view(
        await service.create_conversation(
            db, user.current_organization_id, str(user.id), data.title
        )
    )


@router.get("/conversations/{identifier}")
async def get_conversation(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    return await service.detail(
        db, user.current_organization_id, str(user.id), str(identifier)
    )


@router.patch("/conversations/{identifier}")
async def rename_conversation(
    identifier: UUID,
    data: ConversationCreate,
    user=Depends(actor),
    db=Depends(get_db, scope="function"),
):
    row = await service.conversation(
        db, user.current_organization_id, str(user.id), str(identifier), lock=True
    )
    row.title = data.title
    await db.flush()
    return service.view(row)


@router.delete("/conversations/{identifier}", status_code=204)
async def delete_conversation(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    org, uid = user.current_organization_id, str(user.id)
    await UsageService(db).lock(org)
    row = await service.conversation(db, org, uid, str(identifier), lock=True)
    runs = (
        await db.scalars(
            select(AgentRun)
            .where(
                AgentRun.organization_id == org,
                AgentRun.user_id == uid,
                AgentRun.conversation_id == str(identifier),
            )
            .with_for_update()
        )
    ).all()
    for run in runs:
        if run.status not in service.TERMINAL:
            await UsageService(db).settle(
                run.usage_operation_id,
                org,
                success=False,
                outcome="conversation_deleted",
            )
    # Explicit deletes also keep SQLite contract tests faithful to cascade semantics.
    from app.modules.agent.models import (
        ToolCall,
        ToolResult,
        Message,
        DocumentAttachment,
    )

    call_ids = select(ToolCall.id).where(
        ToolCall.run_id.in_([run.id for run in runs]),
        ToolCall.organization_id == org,
        ToolCall.user_id == uid,
    )
    await db.execute(
        delete(ToolResult).where(
            ToolResult.tool_call_id.in_(call_ids),
            ToolResult.organization_id == org,
            ToolResult.user_id == uid,
        )
    )
    await db.execute(delete(ToolCall).where(ToolCall.id.in_(call_ids)))
    await db.execute(
        delete(AgentEvent).where(
            AgentEvent.run_id.in_([run.id for run in runs]),
            AgentEvent.organization_id == org,
            AgentEvent.user_id == uid,
        )
    )
    for model in (AgentRun, Message, DocumentAttachment):
        await db.execute(
            delete(model).where(
                model.conversation_id == str(identifier),
                model.organization_id == org,
                model.user_id == uid,
            )
        )
    await db.delete(row)


@router.get("/conversations/{identifier}/messages")
async def messages(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    return {
        "items": (
            await service.detail(
                db, user.current_organization_id, str(user.id), str(identifier)
            )
        )["messages"]
    }


@router.post("/conversations/{identifier}/messages", status_code=202)
async def post_message(
    identifier: UUID,
    data: MessageCreate,
    user=Depends(actor),
    db=Depends(get_db, scope="function"),
):
    run, replay = await service.submit(db, user, str(identifier), data)
    await db.commit()
    if not replay:
        from app.workers.agent import run as task

        try:
            await asyncio.to_thread(
                enqueue_with_retry, task, (run.id, run.organization_id, run.user_id)
            )
        except QueueUnavailable:
            await apply_tenant_context(db, run.organization_id, run.user_id)
            await UsageService(db).lock(run.organization_id)
            run = await service.get_run(
                db, run.organization_id, run.user_id, run.id, lock=True
            )
            if run.status == "PENDING":
                run.status, run.error_code = "FAILED", "queue_unavailable"
                await UsageService(db).settle(
                    run.usage_operation_id,
                    run.organization_id,
                    success=False,
                    outcome="queue_unavailable",
                )
                await service.event(
                    db, run, "done", {"status": "FAILED", "code": "queue_unavailable"}
                )
            await db.commit()
    return {"run": service.run_view(run), "replayed": replay}


@router.post("/runs/{identifier}/cancel")
async def cancel_run(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    return await service.cancel(
        db, user.current_organization_id, str(user.id), str(identifier)
    )


@router.get("/conversations/{identifier}/stream")
async def stream(
    identifier: UUID,
    request: Request,
    run_id: UUID,
    after: int = Query(0, ge=0),
    last_event_id: str | None = Header(None),
    user=Depends(actor),
    db=Depends(get_db, scope="function"),
):
    org, uid = user.current_organization_id, str(user.id)
    await service.conversation(db, org, uid, str(identifier))
    run = await service.get_run(db, org, uid, str(run_id))
    if run.conversation_id != str(identifier):
        raise HTTPException(404, "Run not found")
    if last_event_id is not None:
        if not last_event_id.isdecimal() or len(last_event_id) > 10:
            raise HTTPException(422, "Invalid event cursor")
        after = max(after, int(last_event_id))
    factory = getattr(request.app.state, "test_session_factory", AsyncSessionLocal)
    family, version = user.current_session_family, user.session_version

    async def events():
        cursor = after
        # Short-lived streams reauthenticate browser credentials on reconnect.
        for _ in range(50):
            if await request.is_disconnected():
                return
            async with factory() as session:
                await apply_tenant_context(session, org, uid)
                try:
                    await service.authorize(
                        session, org, uid, family=family, version=version
                    )
                    current = await service.get_run(session, org, uid, str(run_id))
                    current = await service.expire_run(session, org, uid, current)
                except HTTPException:
                    yield 'event: access_revoked\ndata: {"code":"access_revoked"}\n\n'
                    return
                rows = (
                    await session.scalars(
                        select(AgentEvent)
                        .where(
                            AgentEvent.organization_id == org,
                            AgentEvent.user_id == uid,
                            AgentEvent.run_id == str(run_id),
                            AgentEvent.sequence > cursor,
                        )
                        .order_by(AgentEvent.sequence)
                        .limit(100)
                    )
                ).all()
                terminal = current.status in service.TERMINAL
                frames = [
                    (
                        row.sequence,
                        row.kind,
                        json.dumps(jsonable_encoder(row.payload), ensure_ascii=True),
                    )
                    for row in rows
                ]
                await session.commit()
            # Release DB connections before yielding to a slow client.
            for sequence, kind, payload in frames:
                cursor = sequence
                yield f"id: {sequence}\nevent: {kind}\ndata: {payload}\n\n"
            if terminal and len(frames) < 100:
                return
            yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents/{identifier}/receipts")
async def receipts(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    await AnalysisTarget.resolve(db, user.current_organization_id, str(identifier))
    rows = (
        await db.scalars(
            select(ActionReceipt)
            .where(
                ActionReceipt.organization_id == user.current_organization_id,
                ActionReceipt.user_id == str(user.id),
                ActionReceipt.document_id == str(identifier),
            )
            .order_by(ActionReceipt.created_at.desc())
            .limit(100)
        )
    ).all()
    return {"items": [receipt_view(row) for row in rows]}


@router.post("/receipts/{identifier}/decision")
async def receipt_decision(
    identifier: UUID,
    data: ReceiptDecision,
    user=Depends(actor),
    db=Depends(get_db, scope="function"),
):
    from app.api.v1.documents import get_storage_client

    return await decide(
        db,
        user.current_organization_id,
        str(user.id),
        str(identifier),
        data.decision,
        data.candidate_sha256,
        get_storage_client(),
    )


@router.get("/voice-profiles")
async def voice_profiles(user=Depends(actor), db=Depends(get_db, scope="function")):
    rows = (
        await db.scalars(
            select(VoiceProfile)
            .where(
                VoiceProfile.organization_id == user.current_organization_id,
                VoiceProfile.user_id == str(user.id),
            )
            .order_by(VoiceProfile.created_at.desc())
            .limit(10)
        )
    ).all()
    return {"items": [service.view(row) for row in rows]}


@router.post("/voice-profiles", status_code=201)
async def create_voice_profile(
    data: VoiceCreate, user=Depends(actor), db=Depends(get_db, scope="function")
):
    from app.modules.agent.voice import create_profile

    return service.view(
        await create_profile(db, user.current_organization_id, str(user.id), data)
    )


@router.delete("/voice-profiles/{identifier}", status_code=204)
async def delete_voice_profile(
    identifier: UUID, user=Depends(actor), db=Depends(get_db, scope="function")
):
    from app.modules.agent.voice import resolve_profile

    profile = await resolve_profile(
        db, user.current_organization_id, str(user.id), identifier
    )
    await db.delete(profile)
