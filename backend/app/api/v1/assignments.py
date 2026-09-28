"""AZAERON assignment API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_active_user, require_role
from app.modules.auth.models import User
from app.modules.assignments.schemas import (
    AssignmentCreate,
    AssignmentResponse,
    SubmissionCreate,
    SubmissionResponse,
    GradeAssignment,
)
from app.modules.organizations.models import OrganizationRole

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    data: AssignmentCreate,
    current_user: User = Depends(
        require_role(
            [OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.FACULTY]
        )
    ),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.modules.assignments.models import Assignment

    assignment = Assignment(
        organization_id=current_user.current_organization_id,
        created_by_id=str(current_user.id),
        title=data.title,
        description=data.description,
        instructions=data.instructions,
        due_date=data.due_date,
        max_file_size_mb=data.max_file_size_mb,
        allowed_extensions=data.allowed_extensions,
        rubric=data.rubric,
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


@router.get("", response_model=list[AssignmentResponse])
async def list_assignments(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from sqlalchemy import select
    from app.modules.assignments.models import Assignment

    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    result = await db.execute(
        select(Assignment).where(
            Assignment.organization_id == current_user.current_organization_id
        )
    )
    return result.scalars().all()


@router.post("/{assignment_id}/submissions", response_model=SubmissionResponse)
async def create_submission(
    assignment_id: str,
    data: SubmissionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.modules.assignments.models import Assignment, Submission, SubmissionStatus
    from app.modules.documents.service import DocumentService
    from sqlalchemy import select
    from datetime import datetime, timezone

    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    assignment = (
        await db.execute(
            select(Assignment).where(
                Assignment.id == assignment_id,
                Assignment.organization_id == current_user.current_organization_id,
            )
        )
    ).scalar_one_or_none()
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    if data.assignment_id != assignment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment ID does not match path",
        )
    if data.document_id:
        document = await DocumentService(db).get_document(
            data.document_id, current_user.current_organization_id
        )
        if not document or str(document.owner_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )
    submission = Submission(
        assignment_id=assignment_id,
        student_id=str(current_user.id),
        document_id=data.document_id,
        status=SubmissionStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    await db.flush()
    await db.refresh(submission)
    return submission


@router.post(
    "/{assignment_id}/submissions/{submission_id}/grade",
    response_model=SubmissionResponse,
)
async def grade_submission(
    assignment_id: str,
    submission_id: str,
    data: GradeAssignment,
    current_user: User = Depends(
        require_role(
            [OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.FACULTY]
        )
    ),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from sqlalchemy import select
    from app.modules.assignments.models import Submission
    from datetime import datetime, timezone
    from app.modules.assignments.models import Assignment

    if not current_user.current_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active organization selected",
        )
    result = await db.execute(
        select(Submission)
        .join(Assignment)
        .where(
            Submission.id == submission_id,
            Submission.assignment_id == assignment_id,
            Assignment.organization_id == current_user.current_organization_id,
        )
    )
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    submission.grade = data.grade
    submission.feedback = data.feedback
    submission.graded_by_id = str(current_user.id)
    submission.graded_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(submission)
    return submission
