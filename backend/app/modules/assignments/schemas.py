"""AZAERON assignment schemas."""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from app.modules.assignments.models import AssignmentStatus, SubmissionStatus


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    instructions: Optional[str] = None
    due_date: Optional[datetime] = None
    max_file_size_mb: int = 100
    allowed_extensions: list[str] = [".pdf", ".docx", ".txt", ".md"]
    rubric: Optional[Dict[str, Any]] = None


class AssignmentResponse(AssignmentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    organization_id: str
    created_by_id: Optional[str]
    status: AssignmentStatus
    created_at: datetime
    updated_at: datetime


class SubmissionCreate(BaseModel):
    assignment_id: str
    document_id: Optional[str] = None


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    assignment_id: str
    student_id: str
    document_id: Optional[str] = None
    status: SubmissionStatus
    submitted_at: Optional[datetime] = None
    late_submission: bool
    grade: Optional[float] = None
    feedback: Optional[str] = None
    graded_at: Optional[datetime] = None


class GradeAssignment(BaseModel):
    grade: float = Field(..., ge=0, le=100)
    feedback: Optional[str] = None
