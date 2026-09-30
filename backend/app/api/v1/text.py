"""Azaeron text API; model engines and protocols never become public endpoints."""

from uuid import UUID
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_active_organization
from app.core.permissions import Permission, require_member_permission
from app.modules.auth.models import User
from app.modules.billing.entitlements import EntitlementService
from app.modules.billing.execution import execute_metered
from app.modules.inference.gateway import AzaeronInferenceJob, AzaeronInferenceResult
from app.modules.inference.registry import InferenceUnavailable
from app.modules.inference.service import gateway
from app.modules.verification.service import VerificationResult, verify_text

router = APIRouter(prefix="/text", tags=["Text"])


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    original: str = Field(min_length=1, max_length=60_000)
    candidate: str = Field(min_length=1, max_length=60_000)
    locked_spans: list[tuple[int, int]] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def bounded_locks(self):
        if any(
            not 0 <= start < end <= len(self.original)
            for start, end in self.locked_spans
        ):
            raise ValueError("Locked spans must be within the original text")
        return self


class RefineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    text: str = Field(min_length=1, max_length=60_000)


class RefineResponse(BaseModel):
    candidate: AzaeronInferenceResult
    verification: VerificationResult
    accepted: bool = False


@router.post("/verify", response_model=VerificationResult)
async def verify(
    data: VerifyRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await EntitlementService(db).require_write(
        organization_id, len(data.original) + len(data.candidate)
    )

    async def execute():
        try:
            private = gateway()
        except InferenceUnavailable:
            private = None
        return await verify_text(
            data.original,
            data.candidate,
            operation_id=data.operation_id,
            organization_id=UUID(organization_id),
            user_id=UUID(str(user.id)),
            locked_spans=data.locked_spans,
            gateway=private,
        )

    return await execute_metered(
        db,
        user,
        "text_verify",
        data.operation_id,
        data.model_dump(mode="json"),
        execute,
    )


@router.post("/refine", response_model=RefineResponse)
async def refine(
    data: RefineRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await require_member_permission(
        db, organization_id, str(user.id), Permission.EDITORIAL_WRITE
    )
    await EntitlementService(db).require_write(organization_id, len(data.text))

    async def execute():
        try:
            private = gateway()
            # Do not spend a rewrite call when independent verification cannot run.
            writer, verifier = private.router.route("refine"), private.router.route(
                "verify"
            )
            if (
                writer.revision == verifier.revision
                or writer.model_id == verifier.model_id
            ):
                raise InferenceUnavailable("independent_verifier_required")
            result = await private.run(
                AzaeronInferenceJob(
                    operation_id=data.operation_id,
                    organization_id=UUID(organization_id),
                    user_id=UUID(str(user.id)),
                    task="refine",
                    text=data.text,
                    focus=getattr(data, "focus", "clarity"),
                )
            )
        except InferenceUnavailable as error:
            raise HTTPException(
                503,
                {
                    "code": error.code,
                    "message": "Approved private inference is unavailable; your text has not been changed.",
                },
            ) from None
        verification = await verify_text(
            data.text,
            result.output,
            operation_id=data.operation_id,
            organization_id=UUID(organization_id),
            user_id=UUID(str(user.id)),
            gateway=private,
            writing_model_id=result.model_id,
            writing_model_revision=result.model_revision,
        )
        return RefineResponse(candidate=result, verification=verification)

    return await execute_metered(
        db,
        user,
        "text_refine",
        data.operation_id,
        data.model_dump(mode="json"),
        execute,
    )


class AnalyzeResponse(BaseModel):
    operation_id: UUID
    method: str = "deterministic-text-statistics-v1"
    characters: int
    words: int
    paragraphs: int
    detector_status: str = "EXPERIMENTAL"
    authorship_verdict: str = "INDETERMINATE"
    calibrated_probability: float | None = None
    limitations: list[str] = [
        "Text statistics do not establish authorship or factual accuracy. No calibrated detector is available."
    ]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    data: RefineRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await EntitlementService(db).require_write(organization_id, len(data.text))

    async def execute():
        return AnalyzeResponse(
            operation_id=data.operation_id,
            characters=len(data.text),
            words=len(re.findall(r"\b\w+\b", data.text)),
            paragraphs=len(
                [value for value in re.split(r"\n\s*\n", data.text) if value.strip()]
            ),
        )

    return await execute_metered(
        db,
        user,
        "text_analyze",
        data.operation_id,
        data.model_dump(mode="json"),
        execute,
    )
