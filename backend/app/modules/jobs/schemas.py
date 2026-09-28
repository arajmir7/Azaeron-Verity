"""AZAERON job schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from app.modules.jobs.models import JobStatus, JobType


class JobBase(BaseModel):
    job_type: JobType
    priority: int = 0
    input_data: Optional[dict] = None


class JobCreate(JobBase):
    document_id: str
    document_version_id: str


class JobResponse(JobBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    document_id: str
    document_version_id: str
    status: JobStatus
    progress_percent: int
    result_data: Optional[dict] = None
    error_message: Optional[str] = None
    retry_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    celery_task_id: Optional[str] = None


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    page_size: int


class JobCancelResponse(BaseModel):
    id: str
    status: JobStatus
    cancelled: bool
    message: str
