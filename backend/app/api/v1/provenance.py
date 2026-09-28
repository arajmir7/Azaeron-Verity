"""Tenant-authorized provenance timeline and secure export."""

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.documents.service import DocumentService
from app.modules.provenance.schemas import ProvenanceTimelineResponse
from app.modules.provenance.service import ProvenanceService

router = APIRouter(prefix="/provenance", tags=["Document Provenance"])


@router.get("/documents/{doc_id}/timeline", response_model=ProvenanceTimelineResponse)
async def get_provenance_timeline(
    doc_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    if not organization_id or not await DocumentService(db).get_document(
        doc_id, organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    try:
        timeline = await ProvenanceService(db).build_timeline(doc_id, organization_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return ProvenanceTimelineResponse.model_validate(timeline)


@router.post("/documents/{doc_id}/export")
async def export_provenance_history(
    doc_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    if not organization_id or not await DocumentService(db).get_document(
        doc_id, organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    try:
        export, payload = await ProvenanceService(db).export_history(
            doc_id, organization_id, str(current_user.id)
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    body = json.dumps(payload, sort_keys=True, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{doc_id}-provenance.json"',
            "X-Provenance-Export-Id": str(export.id),
            "X-Provenance-Export-Hash": export.export_hash,
        },
    )
