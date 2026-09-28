"""AZAERON job service."""

from datetime import datetime, timezone
from typing import Optional
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from fastapi import HTTPException, status

from app.modules.jobs.models import Job, JobStatus, JobType
from app.modules.jobs.schemas import JobCreate
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)

    async def create_job(self, job_data: JobCreate, org_id: str, user_id: str) -> Job:
        from app.modules.documents.target import AnalysisTarget

        target = await AnalysisTarget.resolve(
            self.db, org_id, job_data.document_id, job_data.document_version_id
        )
        inputs = {**(job_data.input_data or {})}
        if (
            inputs.get("document_version_id", job_data.document_version_id)
            != job_data.document_version_id
        ):
            raise ValueError("Job payload disagrees with its immutable version target")
        if (
            inputs.get("storage_key", target.version.storage_path)
            != target.version.storage_path
        ):
            raise ValueError("Job object does not match its immutable version")
        inputs["document_version_id"] = job_data.document_version_id
        from app.modules.billing.usage import UsageService

        # A version's processing identity is stable across HTTP retry and worker
        # delivery. Different versions still have independent analysis identities.
        job_id = str(
            uuid5(
                NAMESPACE_URL,
                f"verity-job:{org_id}:{job_data.document_version_id}:{job_data.job_type.value}",
            )
        )
        from opentelemetry import trace

        trace.get_current_span().set_attribute("job.id", job_id)
        trace.get_current_span().set_attribute("operation.id", job_id)
        usage = UsageService(self.db)
        record, replay = await usage.reserve(
            org_id,
            user_id,
            "document_processing",
            job_id,
            {"version": job_data.document_version_id, "type": job_data.job_type.value},
            api_key_id=self.db.info.get("api_key_id"),
            document_id=job_data.document_id,
            job_id=job_id,
        )
        if replay:
            existing = await self.get_job(job_id, org_id)
            if existing:
                return existing
            raise HTTPException(
                409, "Processing operation no longer has an available job"
            )
        job = Job(
            id=job_id,
            organization_id=org_id,
            document_id=job_data.document_id,
            document_version_id=job_data.document_version_id,
            job_type=job_data.job_type,
            status=JobStatus.PENDING,
            priority=job_data.priority,
            progress_percent=0,
            input_data=inputs,
        )
        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)
        await self.audit.log(
            AuditAction.JOB_CREATED,
            "job",
            str(job.id),
            details={
                "job_type": job_data.job_type.value,
                "document_id": job_data.document_id,
            },
            user_id=user_id,
            organization_id=org_id,
        )
        logger.info(
            "job_created",
            job_id=str(job.id),
            job_type=job_data.job_type.value,
            organization_id=org_id,
        )
        return job

    async def get_job(self, job_id: str, org_id: str) -> Optional[Job]:
        result = await self.db.execute(
            select(Job).where(and_(Job.id == job_id, Job.organization_id == org_id))
        )
        return result.scalar_one_or_none()

    async def list_jobs(
        self,
        org_id: str,
        status: Optional[JobStatus] = None,
        job_type: Optional[JobType] = None,
        page: int = 1,
        page_size: int = 20,
    ):
        query = select(Job).where(Job.organization_id == org_id)
        if status:
            query = query.where(Job.status == status)
        if job_type:
            query = query.where(Job.job_type == job_type)
        query = query.order_by(desc(Job.created_at))
        total = await self.db.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        return result.scalars().all(), total

    async def cancel_job(self, job_id: str, org_id: str, user_id: str) -> Job:
        job = await self.db.scalar(
            select(Job)
            .where(Job.id == job_id, Job.organization_id == org_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )
        if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel job with status '{job.status.value}'",
            )
        job.status = JobStatus.CANCELLED
        from app.modules.billing.usage import UsageService

        await UsageService(self.db).settle_job(
            job_id, org_id, success=False, outcome="cancelled"
        )
        if job.celery_task_id:
            from app.workers.celery_app import celery_app

            celery_app.control.revoke(job.celery_task_id, terminate=True)
        await self.db.flush()
        await self.audit.log(
            AuditAction.JOB_FAILED,
            "job",
            job_id,
            details={"reason": "cancelled_by_user"},
            user_id=user_id,
            organization_id=org_id,
        )
        return job
