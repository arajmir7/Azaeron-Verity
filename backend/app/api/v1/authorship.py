"""Tenant-scoped authorship consistency analysis."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.authorship.models import AuthorshipProfile, AuthorshipSignal
from app.modules.authorship.schemas import (
    AuthorshipProfileCreate,
    AuthorshipProfileResponse,
    AuthorshipSignalResponse,
)
from app.modules.authorship.service import AuthorshipService
from app.modules.documents.models import Document
from app.modules.documents.service import DocumentService
from app.modules.documents.target import AnalysisTarget
from app.modules.processing.models import ProcessedDocument

router = APIRouter(prefix="/authorship", tags=["Authorship Consistency"])


def _profile_response(profile: AuthorshipProfile) -> AuthorshipProfileResponse:
    snapshot = profile.stylometric_features or {}
    return AuthorshipProfileResponse(
        id=str(profile.id),
        user_id=str(profile.user_id),
        name=profile.name,
        description=profile.description,
        baseline_document_ids=profile.baseline_document_ids,
        baseline_quality=snapshot.get("baseline_quality"),
        baseline_summary={
            key: snapshot.get(key)
            for key in (
                "feature_version",
                "sample_count",
                "total_words",
                "min_document_words",
                "quality_reasons",
                "source_fingerprint",
            )
            if key in snapshot
        },
        created_at=profile.created_at,
    )


@router.post(
    "/profiles",
    response_model=AuthorshipProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_authorship_profile(
    payload: AuthorshipProfileCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    if not organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an organization before creating a baseline",
        )
    document_ids = list(dict.fromkeys(payload.baseline_document_ids))
    result = await db.execute(
        select(Document).where(
            Document.id.in_(document_ids),
            Document.organization_id == organization_id,
            Document.owner_id == str(current_user.id),
        )
    )
    documents = result.scalars().all()
    if len(documents) != len(document_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more baseline documents were not found or are not owned by the current user",
        )
    processed = []
    for document_id in document_ids:
        target = await AnalysisTarget.resolve(db, organization_id, document_id)
        processed.append(await target.processed(db))
    profile = AuthorshipProfile(
        organization_id=organization_id,
        user_id=str(current_user.id),
        name=payload.name,
        description=payload.description,
        baseline_document_ids=document_ids,
    )
    db.add(profile)
    await db.flush()
    await AuthorshipService(db).build_profile(profile, processed)
    return _profile_response(profile)


@router.post("/documents/{doc_id}/analysis", response_model=AuthorshipSignalResponse)
async def analyze_authorship(
    doc_id: str,
    profile_id: str | None = None,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    target = await AnalysisTarget.resolve(
        db, organization_id, doc_id, document_version_id, lock=True
    )
    await DocumentService(db)._require_mutation_access(
        target.document, str(current_user.id)
    )
    if profile_id:
        profile = (
            await db.execute(
                select(AuthorshipProfile).where(
                    AuthorshipProfile.id == profile_id,
                    AuthorshipProfile.user_id == str(current_user.id),
                    AuthorshipProfile.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Authorship baseline profile not found",
            )
    processed = await target.processed(db)
    signal = await AuthorshipService(db).analyze_authorship(
        doc_id, processed, profile_id=profile_id
    )
    return AuthorshipSignalResponse.model_validate(signal)


@router.get("/documents/{doc_id}/analysis", response_model=AuthorshipSignalResponse)
async def get_authorship_analysis(
    doc_id: str,
    document_version_id: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    organization_id = current_user.current_organization_id
    target = await AnalysisTarget.resolve(
        db, organization_id, doc_id, document_version_id
    )
    signal = (
        await db.execute(
            select(AuthorshipSignal)
            .where(
                AuthorshipSignal.document_id == doc_id,
                AuthorshipSignal.organization_id == organization_id,
                AuthorshipSignal.document_version_id == str(target.version.id),
            )
            .order_by(AuthorshipSignal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authorship analysis is not available",
        )
    return AuthorshipSignalResponse.model_validate(signal)
