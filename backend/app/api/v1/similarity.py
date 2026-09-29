"""Version-scoped similarity evidence and reproducible review views."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.documents.service import DocumentService
from app.modules.similarity.models import SimilarityMatch
from app.modules.similarity.report import SimilarityReportService
from app.modules.similarity.review import ExclusionPolicy, GROUPS
from app.modules.similarity.schemas import (
    SimilarityMatchListResponse,
    SimilarityMatchResponse,
    SimilarityWorkflowResponse,
    SimilarityReviewMatch,
)
from app.modules.similarity.service import SimilarityService

router = APIRouter(prefix="/similarity", tags=["Similarity Evidence"])


@router.get("/corpora")
async def corpus_coverage(current_user: User = Depends(get_current_active_user)):
    from app.modules.similarity.corpus import coverage

    active_org(current_user)
    return {"corpora": coverage(), "web_wide_search": False}


def active_org(user: User) -> str:
    if not user.current_organization_id:
        raise HTTPException(404, "Document not found")
    return user.current_organization_id


def exclusion_policy(
    exclude_quotes: bool = False,
    exclude_cited: bool = False,
    exclude_bibliography: bool = True,
    min_match_words: int = Query(5, ge=5, le=100),
    excluded_source_version_ids: list[str] | None = Query(None, max_length=100),
) -> ExclusionPolicy:
    return ExclusionPolicy(
        exclude_quotes=exclude_quotes,
        exclude_cited=exclude_cited,
        exclude_bibliography=exclude_bibliography,
        min_match_words=min_match_words,
        excluded_source_version_ids=excluded_source_version_ids or [],
    )


@router.get("/documents/{doc_id}/analysis", response_model=SimilarityWorkflowResponse)
async def get_similarity_analysis(
    doc_id: str,
    document_version_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_page: int = Query(1, ge=1),
    source_page_size: int = Query(10, ge=1, le=100),
    group: str | None = None,
    source_version_id: str | None = None,
    show_excluded: bool = True,
    policy: ExclusionPolicy = Depends(exclusion_policy),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if group and group not in GROUPS:
        raise HTTPException(422, "Unknown similarity match group")
    return await SimilarityReportService(db).build(
        doc_id,
        active_org(current_user),
        document_version_id,
        policy,
        page,
        page_size,
        source_page,
        source_page_size,
        group,
        source_version_id,
        show_excluded,
    )


@router.post("/documents/{doc_id}/analysis", response_model=SimilarityWorkflowResponse)
async def run_similarity_analysis(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    org = active_org(current_user)
    report = SimilarityReportService(db)
    document, version, processed = await report.context(
        doc_id, org, document_version_id
    )
    await DocumentService(db)._require_mutation_access(document, str(current_user.id))
    await SimilarityService(db).analyze_similarity(doc_id, processed)
    return await report.build(doc_id, org, str(version.id), ExclusionPolicy())


@router.get(
    "/documents/{doc_id}/matches/{match_id}", response_model=SimilarityReviewMatch
)
async def get_similarity_evidence(
    doc_id: str,
    match_id: str,
    document_version_id: str,
    policy: ExclusionPolicy = Depends(exclusion_policy),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    report = await SimilarityReportService(db).build(
        doc_id, active_org(current_user), document_version_id, policy, match_id=match_id
    )
    return report.matches.items[0]


@router.get("/documents/{doc_id}/matches", response_model=SimilarityMatchListResponse)
async def get_similarity_matches(
    doc_id: str,
    document_version_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    org = active_org(current_user)
    _, version, _ = await SimilarityReportService(db).context(
        doc_id, org, document_version_id
    )
    where = (
        SimilarityMatch.document_id == doc_id,
        SimilarityMatch.organization_id == org,
        SimilarityMatch.document_version_id == version.id,
    )
    total = await db.scalar(select(func.count(SimilarityMatch.id)).where(*where)) or 0
    matches = (
        await db.execute(
            select(SimilarityMatch)
            .where(*where)
            .order_by(SimilarityMatch.document_span_start, SimilarityMatch.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    return SimilarityMatchListResponse(
        matches=[SimilarityMatchResponse.model_validate(match) for match in matches],
        total=int(total),
        document_version_id=str(version.id),
        page=page,
        page_size=page_size,
        limitations=[
            "Similarity is evidence of overlap, not a plagiarism determination.",
            "Historical matches without a frozen analysis are not included in the new similarity summary.",
        ],
    )
