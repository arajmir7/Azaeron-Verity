"""One bounded run per queued message. Redelivery never repeats generation."""

import asyncio
from datetime import datetime, timezone
import json
import time
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, func

from app.core.database import AsyncSessionLocal, apply_tenant_context
from app.modules.agent.models import (
    AgentRun,
    Message,
    ToolCall,
    ToolResult,
    DocumentAttachment,
)
from app.modules.agent.schemas import MessageCreate, Attachment
from app.modules.agent.service import authorize, get_run, event, TERMINAL
from app.modules.agent.tools import attach, execute_tool
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.billing.usage import UsageService, collect_model_calls, aware
from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable
from app.modules.inference.service import gateway
from app.modules.agent.metrics import (
    QUEUE_WAIT,
    FIRST_TOKEN,
    RUN_DURATION,
    TOOL_DURATION,
    TOKENS,
    FAILURES,
)


async def execute_run(run_id, org, actor, *, session_factory=AsyncSessionLocal):
    started = time.monotonic()
    async with session_factory() as db:
        await apply_tenant_context(db, org, actor)
        await UsageService(db).lock(org)
        try:
            run = await get_run(db, org, actor, run_id, lock=True)
        except HTTPException:
            return  # An erased conversation must never be recreated by redelivery.
        if run.status != "PENDING":
            return
        QUEUE_WAIT.observe(
            max(0, (datetime.now(timezone.utc) - aware(run.created_at)).total_seconds())
        )
        run.status = "RUNNING"
        await event(db, run, "started", {"status": "RUNNING"})
        await db.commit()
        await apply_tenant_context(db, org, actor)
        calls = []
        call_id = None
        status, code, output = "COMPLETED", None, None
        try:
            await authorize(
                db, org, actor, family=run.session_family, version=run.session_version
            )
            if aware(run.expires_at) <= datetime.now(timezone.utc):
                raise InferenceUnavailable("run_expired")
            data = MessageCreate.model_validate(run.request)
            if data.tool:
                call = ToolCall(
                    id=str(uuid4()),
                    organization_id=org,
                    user_id=actor,
                    run_id=run_id,
                    name=data.tool.name,
                    arguments=data.tool.model_dump(mode="json"),
                    status="RUNNING",
                )
                db.add(call)
                await db.flush()
                call_id = str(call.id)
                await AuditService(db).log(
                    AuditAction.WRITING_SUGGESTIONS,
                    "agent_tool",
                    call_id,
                    details={"name": data.tool.name, "phase": "authorized"},
                    user_id=actor,
                    organization_id=org,
                )
                await event(
                    db, run, "tool", {"name": data.tool.name, "tool_call_id": call_id}
                )
                await db.commit()
                await apply_tenant_context(db, org, actor)

            async def check_active():
                async with session_factory() as check:
                    await apply_tenant_context(check, org, actor)
                    current = await get_run(check, org, actor, run_id)
                    await authorize(
                        check,
                        org,
                        actor,
                        family=current.session_family,
                        version=current.session_version,
                    )
                    if current.status != "RUNNING" or aware(
                        current.expires_at
                    ) <= datetime.now(timezone.utc):
                        raise InferenceUnavailable("run_stopped")

            buffered = ""
            last_emit = time.monotonic()
            first_token = True

            async def delta(content, *, flush=False):
                nonlocal buffered, last_emit, first_token
                if content and first_token:
                    FIRST_TOKEN.observe(time.monotonic() - started)
                    first_token = False
                buffered += content
                if (
                    not flush
                    and len(buffered) < 256
                    and time.monotonic() - last_emit < 0.2
                ):
                    return
                if not buffered:
                    return
                async with session_factory() as live:
                    await apply_tenant_context(live, org, actor)
                    current = await get_run(live, org, actor, run_id, lock=True)
                    await authorize(
                        live,
                        org,
                        actor,
                        family=current.session_family,
                        version=current.session_version,
                    )
                    if current.status != "RUNNING":
                        raise InferenceUnavailable("run_stopped")
                    await event(
                        live, current, "delta", {"text": buffered, "provisional": True}
                    )
                    await live.commit()
                buffered, last_emit = "", time.monotonic()

            async def generate():
                if data.tool:
                    tool_start = time.monotonic()
                    try:
                        return await execute_tool(db, run, data.tool)
                    finally:
                        TOOL_DURATION.labels(data.tool.name).observe(
                            time.monotonic() - tool_start
                        )
                references = (
                    await db.scalars(
                        select(DocumentAttachment)
                        .where(
                            DocumentAttachment.organization_id == org,
                            DocumentAttachment.user_id == actor,
                            DocumentAttachment.conversation_id == run.conversation_id,
                        )
                        .order_by(DocumentAttachment.created_at.desc())
                        .limit(8)
                    )
                ).all()
                documents = []
                for reference in references:
                    target, source = await attach(
                        db,
                        run,
                        Attachment(
                            document_id=UUID(reference.document_id),
                            document_version_id=UUID(reference.document_version_id),
                        ),
                    )
                    documents.append(
                        {
                            "document_id": str(target.document.id),
                            "version_id": str(target.version.id),
                            "untrusted_content": source,
                        }
                    )
                history = (
                    await db.scalars(
                        select(Message)
                        .where(
                            Message.organization_id == org,
                            Message.user_id == actor,
                            Message.conversation_id == run.conversation_id,
                            Message.id != run.message_id,
                            Message.role.in_(["user", "assistant"]),
                        )
                        .order_by(Message.sequence.desc())
                        .limit(12)
                    )
                ).all()
                context = json.dumps(
                    {
                        "current_request": data.content,
                        "untrusted_history": [
                            {"role": msg.role, "text": msg.content}
                            for msg in reversed(history)
                        ],
                        "untrusted_documents": documents,
                    },
                    ensure_ascii=False,
                )
                await db.commit()
                await apply_tenant_context(db, org, actor)
                response = await gateway().run(
                    AzaeronInferenceJob(
                        operation_id=UUID(run_id),
                        organization_id=UUID(org),
                        user_id=UUID(actor),
                        task="chat",
                        text=context,
                    ),
                    on_delta=delta,
                )
                await delta("", flush=True)
                run.model_evidence = response.model_dump(
                    mode="json", exclude={"output"}
                )
                return {"text": response.output, "model_evidence": run.model_evidence}

            with collect_model_calls() as collected:
                task = asyncio.create_task(generate())
                try:
                    while not task.done():
                        done, _ = await asyncio.wait({task}, timeout=0.5)
                        if not done:
                            await check_active()
                    output = await task
                finally:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    calls = list(collected)
            # Recheck permission and cancellation before any completed message or receipt commits.
            await check_active()
            evidence = dict(run.model_evidence or {})
            await UsageService(db).lock(org)
            current = await get_run(db, org, actor, run_id, lock=True)
            if current.status != "RUNNING":
                raise InferenceUnavailable("run_stopped")
            current.model_evidence = evidence
            if call_id:
                call = await db.scalar(
                    select(ToolCall).where(
                        ToolCall.id == call_id,
                        ToolCall.organization_id == org,
                        ToolCall.user_id == actor,
                    )
                )
                if call:
                    call.status = "COMPLETED"
                    db.add(
                        ToolResult(
                            organization_id=org,
                            user_id=actor,
                            tool_call_id=call_id,
                            content=output,
                        )
                    )
            text = output.get("text") or output.get("summary") if output else None
            if text:
                sequence = (
                    await db.scalar(
                        select(func.max(Message.sequence)).where(
                            Message.conversation_id == current.conversation_id,
                            Message.organization_id == org,
                            Message.user_id == actor,
                        )
                    )
                    or 0
                ) + 1
                message = Message(
                    organization_id=org,
                    user_id=actor,
                    conversation_id=current.conversation_id,
                    sequence=sequence,
                    role="assistant",
                    content=text,
                )
                db.add(message)
                await db.flush()
                await event(
                    db, current, "message", {"message_id": message.id, "text": text}
                )
            elif output:
                await event(db, current, "result", output)
            current.status, current.completed_at = "COMPLETED", datetime.now(
                timezone.utc
            )
            settlement = await UsageService(db).settle(
                current.usage_operation_id,
                org,
                success=True,
                outcome="completed",
                calls=calls,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            if settlement.status != "COMMITTED":
                raise InferenceUnavailable("run_expired")
            await event(db, current, "done", {"status": "COMPLETED"})
            await db.commit()
            RUN_DURATION.labels("completed").observe(time.monotonic() - started)
            for usage_call in calls:
                TOKENS.labels("input").inc(usage_call["input_tokens"])
                TOKENS.labels("output").inc(usage_call["output_tokens"])
            return
        except InferenceUnavailable as error:
            status, code = "UNAVAILABLE", error.code
        except HTTPException as error:
            status, code = "FAILED", (
                "authorization_changed"
                if error.status_code in {401, 403, 404}
                else "tool_request_rejected"
            )
        except Exception:
            status, code = "FAILED", "agent_execution_failed"
        await db.rollback()
        await apply_tenant_context(db, org, actor)
        await UsageService(db).lock(org)
        try:
            current = await get_run(db, org, actor, run_id, lock=True)
        except HTTPException:
            return
        if current.status == "CANCELLED":
            status, code = "CANCELLED", "cancelled"
        elif current.status in TERMINAL:
            return  # An expiry/queue failure is already durably reconciled.
        current.status, current.error_code = status, code
        current.completed_at = datetime.now(timezone.utc)
        if call_id:
            call = await db.scalar(
                select(ToolCall).where(
                    ToolCall.id == call_id,
                    ToolCall.organization_id == org,
                    ToolCall.user_id == actor,
                )
            )
            if call:
                call.status = status
                db.add(
                    ToolResult(
                        organization_id=org,
                        user_id=actor,
                        tool_call_id=call_id,
                        content={"status": status, "code": code},
                    )
                )
        await UsageService(db).settle(
            current.usage_operation_id,
            org,
            success=False,
            outcome=code,
            calls=calls,
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        await event(
            db,
            current,
            "done",
            {"status": status, "code": code, "discard_provisional_output": True},
        )
        await db.commit()
        RUN_DURATION.labels(status.lower()).observe(time.monotonic() - started)
        FAILURES.labels(status).inc()
        for usage_call in calls:
            TOKENS.labels("input").inc(usage_call["input_tokens"])
            TOKENS.labels("output").inc(usage_call["output_tokens"])
