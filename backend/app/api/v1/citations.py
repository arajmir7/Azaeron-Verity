"""Tenant-scoped citation and source intelligence."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.citations.models import Citation, CitationFinding, Reference, Source
from app.modules.citations.schemas import (
    CitationAnalysisResponse,
    CitationFindingResponse,
    CitationResponse,
    ReferenceResponse,
    SourceResponse,
)
from app.modules.documents.service import DocumentService
from app.modules.documents.target import AnalysisTarget

router = APIRouter(prefix="/citations", tags=["Citation Intelligence"])


@router.get("/documents/{doc_id}/analysis", response_model=CitationAnalysisResponse)
async def get_citation_analysis(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    target = await AnalysisTarget.resolve(
        db, organization_id, doc_id, document_version_id
    )
    version_id = str(target.version.id)
    finding_result = await db.execute(
        select(CitationFinding)
        .where(
            CitationFinding.document_id == doc_id,
            CitationFinding.organization_id == organization_id,
            CitationFinding.document_version_id == version_id,
        )
        .order_by(CitationFinding.created_at.asc())
    )
    citation_result = await db.execute(
        select(Citation)
        .where(
            Citation.document_id == doc_id,
            Citation.organization_id == organization_id,
            Citation.document_version_id == version_id,
        )
        .order_by(Citation.span_start.asc())
    )
    reference_result = await db.execute(
        select(Reference)
        .where(
            Reference.document_id == doc_id,
            Reference.organization_id == organization_id,
            Reference.document_version_id == version_id,
        )
        .order_by(Reference.created_at.asc())
    )
    findings = finding_result.scalars().all()
    citations = citation_result.scalars().all()
    references = reference_result.scalars().all()
    linked_items: list[CitationFinding | Citation | Reference] = [
        *findings,
        *citations,
        *references,
    ]
    source_ids = {str(item.source_id) for item in linked_items if item.source_id}
    sources: list[Source] = []
    if source_ids:
        source_result = await db.execute(
            select(Source).where(
                Source.organization_id == organization_id,
                Source.id.in_(source_ids),
                Source.document_id == doc_id,
                Source.document_version_id == version_id,
            )
        )
        sources = list(source_result.scalars())
    return CitationAnalysisResponse(
        document_id=doc_id,
        document_version_id=version_id,
        findings=[CitationFindingResponse.model_validate(item) for item in findings],
        citations=[CitationResponse.model_validate(item) for item in citations],
        references=[ReferenceResponse.model_validate(item) for item in references],
        sources=[SourceResponse.model_validate(item) for item in sources],
        limitations=[
            "A source is not claimed to support a statement without retrieved evidence.",
            "UNVERIFIABLE means source content was unavailable or could not be assessed.",
            "Support assessment uses retrieved abstract lexical evidence and is not semantic entailment.",
            "Arbitrary URLs are preserved but are not fetched by the default resolver.",
        ],
    )
