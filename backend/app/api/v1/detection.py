"""AZAERON detection API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.detection.schemas import (
    DetectionResultResponse,
    DetectionExplainability,
)
from app.modules.detection.service import DetectionService
from app.modules.documents.service import DocumentService
from app.modules.documents.target import AnalysisTarget

router = APIRouter(prefix="/detection", tags=["AI Detection"])


@router.get("/documents/{doc_id}", response_model=DetectionResultResponse)
async def get_detection_result(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    target = await AnalysisTarget.resolve(
        db, current_user.current_organization_id, doc_id, document_version_id
    )
    from sqlalchemy import select
    from app.modules.detection.models import DetectionResult

    result = await db.execute(
        select(DetectionResult)
        .where(
            DetectionResult.document_id == doc_id,
            DetectionResult.organization_id == target.organization_id,
            DetectionResult.document_version_id == str(target.version.id),
        )
        .order_by(DetectionResult.created_at.desc(), DetectionResult.id)
        .limit(1)
    )
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Detection result not found"
        )
    return detection


@router.get("/documents/{doc_id}/explain", response_model=DetectionExplainability)
async def explain_detection(
    doc_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not current_user.current_organization_id or not await DocumentService(
        db
    ).get_document(doc_id, current_user.current_organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    return DetectionExplainability(
        what_this_means="This report describes observed writing signals and whether the calibrated analysis pipeline could classify them.",
        how_this_was_calculated="Independent linguistic, stylometric, syntactic, segment-level, document-level, semantic, authorship-consistency, and revision/provenance providers report versioned evidence.",
        evidence_used=[
            "Independent signal providers",
            "Sentence and paragraph segmentation",
            "Calibration and abstention metadata",
        ],
        what_this_does_not_prove="It does not prove who authored the document or that an author used AI. Unavailable or uncalibrated capabilities remain explicitly untested.",
        known_limitations=[
            "Classifier ensemble requires training on validated datasets",
            "Short documents have higher uncertainty",
            "Edited AI text may appear human-like",
            "Domain-specific writing may trigger false signals",
        ],
    )
