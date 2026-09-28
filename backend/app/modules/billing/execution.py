"""Persist a receipt before returning a metered synchronous operation."""

import asyncio
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.core.database import apply_tenant_context
from app.modules.billing.usage import UsageService, collect_model_calls


async def execute_metered(
    db, user, task, operation_id, payload, execute, *, document_id=None
):
    from opentelemetry import trace

    trace.get_current_span().set_attribute("operation.id", str(operation_id))
    org, actor = str(user.current_organization_id), str(user.id)
    service = UsageService(db)
    record, replay = await service.reserve(
        org,
        actor,
        task,
        str(operation_id),
        payload,
        api_key_id=user.current_api_key_id,
        document_id=document_id,
    )
    if replay:
        body, status = service.replay(record)
        return JSONResponse(
            body, status_code=status, headers={"Idempotent-Replay": "true"}
        )
    record_id = str(record.id)
    await db.commit()
    await apply_tenant_context(db, org, actor)
    started = time.monotonic()
    with collect_model_calls() as calls:
        try:
            result = await execute()
            body = (
                result.model_dump(mode="json")
                if hasattr(result, "model_dump")
                else result
            )
            unavailable = isinstance(body, dict) and (
                body.get("outcome") == "UNAVAILABLE"
                or body.get("verification", {}).get("outcome") == "UNAVAILABLE"
            )
            settled = await service.settle(
                record_id,
                org,
                success=not unavailable,
                outcome="unavailable" if unavailable else "completed",
                response=body,
                calls=calls,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            if settled.outcome not in {"completed", "unavailable"}:
                raise HTTPException(
                    409, "Operation expired before completion; retry with a new ID"
                )
            await db.commit()
            return JSONResponse(body)
        except (Exception, asyncio.CancelledError) as error:
            await db.rollback()
            await apply_tenant_context(db, org, actor)
            # Persist only bounded public HTTP error details. Unexpected exception
            # values can contain customer text and never enter the receipt.
            status = error.status_code if isinstance(error, HTTPException) else 503
            body = {
                "detail": (
                    error.detail
                    if isinstance(error, HTTPException)
                    else "Operation could not complete"
                )
            }
            await service.settle(
                record_id,
                org,
                success=False,
                outcome="failed",
                response=body,
                response_status=status,
                calls=calls,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
            await db.commit()
            raise
