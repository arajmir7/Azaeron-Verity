"""AZAERON job API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import Permission, require_permission
from app.core.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.jobs.schemas import JobResponse, JobListResponse, JobCancelResponse
from app.modules.jobs.models import JobStatus, JobType
from app.modules.jobs.service import JobService

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=JobListResponse)
async def list_jobs(
    job_status: Optional[JobStatus] = None,
    job_type: Optional[JobType] = None,
    page: int = Query(default=1, ge=1, le=100_000),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    job_service = JobService(db)
    items, total = await job_service.list_jobs(
        org_id=current_user.current_organization_id,
        status=job_status,
        job_type=job_type,
        page=page,
        page_size=page_size,
    )
    return JobListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    job_service = JobService(db)
    job = await job_service.get_job(job_id, current_user.current_organization_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return job


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    require_permission(current_user, Permission.JOB_CANCEL)
    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    job_service = JobService(db)
    job = await job_service.cancel_job(
        job_id=job_id,
        org_id=current_user.current_organization_id,
        user_id=str(current_user.id),
    )
    return JobCancelResponse(
        id=job_id,
        status=job.status,
        cancelled=True,
        message="Job cancelled successfully",
    )
