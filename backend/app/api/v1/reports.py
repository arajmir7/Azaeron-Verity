"""Evidence-first primary analysis reports."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.evidence.report_service import EvidenceFirstReportService
from app.modules.evidence.schemas import EvidenceFirstReportResponse

router = APIRouter(prefix="/reports", tags=["Evidence-first Reports"])


@router.get("/documents/{doc_id}", response_model=EvidenceFirstReportResponse)
async def get_evidence_first_report(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    try:
        return await EvidenceFirstReportService(db).build(
            doc_id, organization_id, document_version_id
        )
    except ValueError as error:
        if str(error).startswith("Document ") and str(error).endswith(" not found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            ) from error
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
