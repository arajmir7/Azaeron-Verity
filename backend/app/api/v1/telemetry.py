"""Self-hosted browser reports: closed metadata schema, authenticated and bounded."""

from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from app.core.dependencies import get_current_user, RateLimiter
from app.core.observability import FRONTEND_ERRORS, safe_span
from app.modules.auth.models import User

router = APIRouter(tags=["Telemetry"])
limiter = RateLimiter(requests=10, window=60)


class BrowserReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["render", "unhandled_error", "unhandled_rejection"]
    route: Literal[
        "editor", "documents", "settings", "upload", "auth", "workspace", "other"
    ]
    event_id: UUID


@router.post("/telemetry/browser", status_code=202, response_class=Response)
async def browser_report(
    report: BrowserReport, request: Request, user: User = Depends(get_current_user)
):
    await limiter.check_key(f"browser-error:{user.id}")
    with safe_span(
        "browser.error",
        attributes={
            "browser.event.id": str(report.event_id),
            "browser.error.kind": report.kind,
            "browser.route": report.route,
        },
    ):
        FRONTEND_ERRORS.labels(report.kind, report.route).inc()
    return Response(status_code=202)
