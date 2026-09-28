"""Authenticated AZAERON WRITE editorial APIs."""

from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import Permission, require_permission
from app.core.dependencies import editorial_rate_limiter, get_current_active_user
from app.modules.auth.models import User
from app.modules.aegiswrite.schemas import (
    AegisChangeResponse,
    AegisEditApplyRequest,
    AegisEditRequest,
    AegisEditResponse,
    AegisHistoryResponse,
    AegisRefineRequest,
    AegisRefineResponse,
)
from app.modules.aegiswrite.service import AegisWriteService
from app.modules.billing.entitlements import EntitlementService
from app.modules.billing.execution import execute_metered
from app.modules.billing.usage import fingerprint
from app.modules.documents.target import AnalysisTarget

router = APIRouter(prefix="/aegiswrite", tags=["AZAERON WRITE"])

EDITORIAL_DISCLAIMER = (
    "Editorial assistance improves observable writing mechanics and clarity. "
    "It does not remove provenance, target detectors, or guarantee any third-party result."
)


def _response(edit) -> AegisEditResponse:
    return AegisEditResponse(
        id=str(edit.id),
        edit_type=edit.edit_type,
        dimension=edit.dimension,
        original=edit.original_text,
        revision=edit.suggested_text,
        change_reason=edit.explanation,
        span_start=edit.span_start,
        span_end=edit.span_end,
        applied=edit.applied,
        ai_generated=edit.ai_generated,
        document_id=str(edit.document_id),
        document_version_id=str(edit.document_version_id),
        preserve_voice=edit.preserve_voice,
        engine_version=edit.engine_version,
        created_at=edit.created_at,
    )


def _service_error(error: ValueError) -> HTTPException:
    message = str(error)
    code = (
        status.HTTP_404_NOT_FOUND
        if message in {"Document not found", "Edit not found"}
        else status.HTTP_422_UNPROCESSABLE_ENTITY
    )
    return HTTPException(status_code=code, detail=message)


@router.post(
    "/suggest",
    response_model=list[AegisEditResponse],
    dependencies=[Depends(editorial_rate_limiter)],
)
async def suggest_edits(
    data: AegisEditRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Persist transparent, version-bound suggestions for a selected text range."""
    require_permission(current_user, Permission.EDITORIAL_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    target = await AnalysisTarget.resolve(
        db, organization_id, data.document_id, data.document_version_id
    )
    data.document_version_id = str(target.version.id)
    payload = {
        **data.model_dump(mode="json", exclude={"operation_id"}),
        "action": "suggest_edits",
    }
    operation_id = data.operation_id or uuid5(
        NAMESPACE_URL, "editorial:" + fingerprint(payload)
    )

    async def execute():
        try:
            await EntitlementService(db).require_write(organization_id, len(data.text))
            run = await AegisWriteService(db).suggest(
                document_id=data.document_id,
                organization_id=organization_id,
                user_id=str(current_user.id),
                text=data.text,
                document_version_id=data.document_version_id,
                span_start=data.span_start,
                span_end=data.span_end,
                edit_types=data.edit_types,
                preserve_voice=data.preserve_voice,
                locked_spans=data.locked_spans,
            )
        except ValueError as error:
            raise _service_error(error) from error
        return [_response(edit).model_dump(mode="json") for edit in run.edits]

    return await execute_metered(
        db,
        current_user,
        "editorial",
        operation_id,
        payload,
        execute,
        document_id=data.document_id,
    )


@router.post(
    "/refine",
    response_model=AegisRefineResponse,
    dependencies=[Depends(editorial_rate_limiter)],
)
async def refine_draft(
    data: AegisRefineRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Return a deterministic editorial pass plus a persisted change ledger."""
    require_permission(current_user, Permission.EDITORIAL_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    target = await AnalysisTarget.resolve(
        db, organization_id, data.document_id, data.document_version_id
    )
    data.document_version_id = str(target.version.id)
    payload = {
        **data.model_dump(mode="json", exclude={"operation_id"}),
        "action": "refine_draft",
    }
    operation_id = data.operation_id or uuid5(
        NAMESPACE_URL, "editorial:" + fingerprint(payload)
    )

    async def execute():
        try:
            await EntitlementService(db).require_write(organization_id, len(data.text))
            run = await AegisWriteService(db).refine(
                document_id=data.document_id,
                organization_id=organization_id,
                user_id=str(current_user.id),
                text=data.text,
                document_version_id=data.document_version_id,
                edit_types=data.edit_types,
                preserve_voice=data.preserve_voice,
                locked_spans=data.locked_spans,
            )
        except ValueError as error:
            raise _service_error(error) from error
        return AegisRefineResponse(
            document_id=str(run.document.id),
            document_version_id=str(run.version.id),
            original_text=run.original_text,
            revised_text=run.revised_text,
            changes=[
                AegisChangeResponse(
                    id=str(edit.id),
                    dimension=edit.dimension,
                    original=edit.original_text,
                    revision=edit.suggested_text,
                    change_reason=edit.explanation,
                    span_start=edit.span_start,
                    span_end=edit.span_end,
                    applied=edit.applied,
                )
                for edit in run.edits
            ],
            disclaimer=EDITORIAL_DISCLAIMER,
        )

    return await execute_metered(
        db,
        current_user,
        "editorial",
        operation_id,
        payload,
        execute,
        document_id=data.document_id,
    )


@router.post(
    "/apply",
    response_model=AegisEditResponse,
    dependencies=[Depends(editorial_rate_limiter)],
)
async def apply_edit(
    data: AegisEditApplyRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Record an authenticated accept/reject decision for a persisted edit."""
    require_permission(current_user, Permission.EDITORIAL_WRITE)
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    try:
        edit = await AegisWriteService(db).apply_edit(
            data.edit_id,
            organization_id,
            str(current_user.id),
            data.apply,
        )
    except ValueError as error:
        raise _service_error(error) from error
    return _response(edit)


@router.get(
    "/history/{document_id}",
    response_model=AegisHistoryResponse,
    dependencies=[Depends(editorial_rate_limiter)],
)
async def edit_history(
    document_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    """Return the tenant-scoped editorial ledger without exposing other workspaces."""
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    try:
        service = AegisWriteService(db)
        _, version = await service._context(
            document_id, organization_id, document_version_id
        )
        edits = await service.history(document_id, organization_id, str(version.id))
    except ValueError as error:
        raise _service_error(error) from error
    return AegisHistoryResponse(
        document_id=document_id,
        document_version_id=str(version.id),
        items=[_response(edit) for edit in edits],
    )
