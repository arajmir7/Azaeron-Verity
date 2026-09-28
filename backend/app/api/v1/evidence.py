"""AZAERON evidence graph API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.evidence.schemas import EvidenceGraphResponse
from app.modules.evidence.service import EvidenceService
from app.modules.documents.service import DocumentService
from fastapi import HTTPException, status

router = APIRouter(prefix="/evidence", tags=["Evidence Graph"])


@router.get("/documents/{doc_id}/graph", response_model=EvidenceGraphResponse)
async def get_evidence_graph(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not current_user.current_organization_id or not await DocumentService(
        db
    ).get_document(doc_id, current_user.current_organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    evidence_service = EvidenceService(db)
    try:
        # The graph endpoint is the canonical repair/materialization boundary:
        # historical provider rows are linked idempotently before they are
        # exposed, so callers never receive a known partial graph.
        return await evidence_service.materialize_document_graph(
            doc_id, current_user.current_organization_id, document_version_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
