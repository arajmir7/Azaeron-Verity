"""Customer-facing Azaeron model API over existing auth, quota and private routing."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.text import RefineRequest, RefineResponse, refine
from app.core.database import get_db, apply_tenant_context
from app.core.dependencies import get_current_user, require_active_organization
from app.modules.agent.service import authorize
from app.modules.auth.models import ApiKey, User
from app.modules.billing.entitlements import EntitlementService
from app.modules.billing.execution import execute_metered
from app.modules.documents.models import DocumentStatus
from app.modules.documents.target import AnalysisTarget
from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable
from app.modules.inference.service import gateway
from app.modules.verification.service import SemanticAssessment

router = APIRouter(tags=["Azaeron AI"])


class HumanizeRequest(RefineRequest):
    focus: Literal["humanise"] = "humanise"


@router.post("/humanize", response_model=RefineResponse)
async def humanize(
    data: HumanizeRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await refine(data, user, organization_id, db)


class ChatRequest(RefineRequest):
    max_output_tokens: int = Field(default=512, ge=1, le=4096)


class DocumentRequest(RefineRequest):
    text: str = Field(
        default="Summarize this document faithfully.", min_length=1, max_length=8000
    )
    document_version_id: UUID


class PlagiarismRequest(RefineRequest):
    text: str = Field(default="", max_length=0)
    document_id: UUID
    document_version_id: UUID


class AskRequest(DocumentRequest):
    text: str = Field(min_length=1, max_length=8000)


async def reauthorize(db, user):
    """Recheck erasure, membership, session or key revocation before release."""
    await apply_tenant_context(db, str(user.current_organization_id), str(user.id))
    await authorize(
        db,
        str(user.current_organization_id),
        str(user.id),
        family=user.current_session_family if not user.current_api_key_id else None,
        version=user.session_version if not user.current_api_key_id else None,
    )
    if user.current_api_key_id:
        key = await db.scalar(
            select(ApiKey)
            .where(
                ApiKey.id == user.current_api_key_id,
                ApiKey.organization_id == user.current_organization_id,
            )
            .execution_options(populate_existing=True)
        )
        if (
            not key
            or not key.is_active
            or key.revoked_at
            or (
                key.expires_at
                and key.expires_at.replace(tzinfo=timezone.utc)
                <= datetime.now(timezone.utc)
            )
        ):
            raise HTTPException(401, "Credential revoked or expired")


def unavailable(error):
    return HTTPException(
        503,
        {"code": error.code, "message": "An approved Azaeron model is unavailable."},
    )


def independent(private, task):
    writer, verifier = private.router.route(task), private.router.route("verify")
    if writer.model_id == verifier.model_id or writer.revision == verifier.revision:
        raise InferenceUnavailable("independent_verifier_required")


async def generate_verified(
    private, data, user, *, task="chat", source=None, on_delta=None
):
    independent(private, task)
    identity = dict(
        operation_id=data.operation_id,
        organization_id=UUID(str(user.current_organization_id)),
        user_id=UUID(str(user.id)),
    )
    prompt = (
        data.text
        if source is None
        else json.dumps(
            {"request": data.text, "untrusted_document": source}, ensure_ascii=False
        )
    )
    result = await private.run(
        AzaeronInferenceJob(
            **identity,
            task=task,
            text=prompt,
            max_output_tokens=getattr(data, "max_output_tokens", 512),
        ),
        on_delta=on_delta,
    )
    review = await private.run(
        AzaeronInferenceJob(
            **identity,
            task="verify",
            text=json.dumps(
                {
                    "mode": (
                        "grounded_support" if source is not None else "answer_support"
                    ),
                    "original": source if source is not None else data.text,
                    "candidate": result.output,
                    "policy": "Assess whether every factual claim is supported by the supplied source. Omissions are allowed for summaries. Without sufficient evidence return uncertain. Do not infer access to outside sources.",
                },
                ensure_ascii=False,
            ),
            max_output_tokens=256,
        )
    )
    try:
        assessment = SemanticAssessment.model_validate_json(review.output)
    except ValueError:
        raise InferenceUnavailable("verifier_invalid_output") from None
    accepted = assessment.equivalent and not (
        assessment.contradiction
        or assessment.unsupported_additions
        or assessment.uncertain
    )
    # General chat cannot establish external facts absent supplied evidence.
    return {
        "operation_id": str(data.operation_id),
        "result": result.model_dump(mode="json"),
        "verification": {
            "outcome": "VERIFIED" if accepted else "REJECTED",
            "model_id": review.model_id,
            "model_revision": review.model_revision,
            **assessment.model_dump(),
        },
        "accepted": accepted,
        "limitations": [
            "Verification covers supplied evidence; it does not establish external factual truth."
        ],
    }


@router.post("/ai/chat")
async def chat(
    data: ChatRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await reauthorize(db, user)
    await EntitlementService(db).require_write(organization_id, len(data.text))

    async def execute():
        try:
            result = await generate_verified(gateway(), data, user)
            await reauthorize(db, user)
            return result
        except InferenceUnavailable as error:
            raise unavailable(error) from None

    return await execute_metered(
        db,
        user,
        "ai_run",
        data.operation_id,
        {"endpoint": "chat", **data.model_dump(mode="json")},
        execute,
    )


@router.post("/ai/chat/stream")
async def chat_stream(
    data: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db),
):
    await reauthorize(db, user)
    await EntitlementService(db).require_write(organization_id, len(data.text))
    try:
        private = gateway()
        independent(private, "chat")
    except InferenceUnavailable as error:
        raise unavailable(error) from None

    async def events():
        queue: asyncio.Queue = asyncio.Queue(maxsize=16)

        async def delta(content):
            await reauthorize(db, user)
            await queue.put(("delta", {"text": content, "provisional": True}))

        async def execute():
            try:
                result = await generate_verified(private, data, user, on_delta=delta)
                await reauthorize(db, user)
                return result
            except InferenceUnavailable as error:
                raise unavailable(error) from None

        async def produce():
            try:
                response = await execute_metered(
                    db,
                    user,
                    "ai_run",
                    data.operation_id,
                    {"endpoint": "chat/stream", **data.model_dump(mode="json")},
                    execute,
                )
                body = json.loads(response.body)
                await queue.put(
                    ("completed" if response.status_code == 200 else "error", body)
                )
            except Exception:
                await queue.put(
                    (
                        "error",
                        {
                            "code": "inference_unavailable",
                            "provisional_output_rejected": True,
                        },
                    )
                )
            finally:
                # Cancellation must not block trying to publish to a full queue.
                current = asyncio.current_task()
                if current is not None and not current.cancelling():
                    await queue.put(None)

        pending = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                name, body = item
                yield f"event: {name}\ndata: {json.dumps(body, allow_nan=False)}\n\n"
        finally:
            if not pending.done():
                pending.cancel()
            try:
                await pending
            except asyncio.CancelledError:
                pass

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/detect")
async def detect(
    data: RefineRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    await reauthorize(db, user)
    await EntitlementService(db).require_write(organization_id, len(data.text))

    async def execute():
        try:
            result = await gateway().run(
                AzaeronInferenceJob(
                    operation_id=data.operation_id,
                    organization_id=UUID(organization_id),
                    user_id=UUID(str(user.id)),
                    task="classify",
                    text=data.text,
                    max_output_tokens=1,
                )
            )
            await reauthorize(db, user)
            return {
                "operation_id": str(data.operation_id),
                "model_id": result.model_id,
                "model_revision": result.model_revision,
                **json.loads(result.output),
            }
        except InferenceUnavailable as error:
            raise unavailable(error) from None

    return await execute_metered(
        db,
        user,
        "text_analyze",
        data.operation_id,
        {"endpoint": "detect", **data.model_dump(mode="json")},
        execute,
    )


async def document_generation(document_id, data, user, db, task):
    await reauthorize(db, user)
    target = await AnalysisTarget.resolve(
        db,
        user.current_organization_id,
        str(document_id),
        str(data.document_version_id),
    )
    if (
        target.document.erasure_pending
        or target.document.status == DocumentStatus.ARCHIVED
    ):
        raise HTTPException(404, "Document not found")
    processed = await target.processed(db)
    source = processed.cleaned_text or ""
    if not source or len(source) > 60_000:
        raise HTTPException(422, "Document context unavailable or too large")
    await EntitlementService(db).require_write(
        str(user.current_organization_id), len(source) + len(data.text)
    )
    source_hash = hashlib.sha256(source.encode()).hexdigest()

    async def execute():
        try:
            private = gateway()
            context, retrieval = source, None
            if task == "chat":
                from app.modules.model_platform.retrieval import document_context

                context, retrieval = await document_context(
                    private,
                    {
                        "operation_id": data.operation_id,
                        "organization_id": UUID(str(user.current_organization_id)),
                        "user_id": UUID(str(user.id)),
                    },
                    data.text,
                    source,
                )
            result = await generate_verified(
                private, data, user, task=task, source=context
            )
            await reauthorize(db, user)
            await db.refresh(target.document)
            if target.document.erasure_pending:
                raise HTTPException(404, "Document not found")
            return {
                **result,
                "document_id": str(document_id),
                "document_version_id": str(data.document_version_id),
                "source_sha256": source_hash,
                "retrieval": retrieval,
            }
        except InferenceUnavailable as error:
            raise unavailable(error) from None

    return await execute_metered(
        db,
        user,
        "ai_run",
        data.operation_id,
        {
            "endpoint": task,
            "document_id": str(document_id),
            "source_sha256": source_hash,
            **data.model_dump(mode="json"),
        },
        execute,
        document_id=str(document_id),
    )


@router.post("/documents/{id}/summarize")
async def summarize(
    id: UUID,
    data: DocumentRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await document_generation(id, data, user, db, "summarize")


@router.post("/documents/{id}/ask")
async def ask(
    id: UUID,
    data: AskRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    return await document_generation(id, data, user, db, "chat")


@router.post("/plagiarism/check")
async def plagiarism(
    data: PlagiarismRequest,
    user: User = Depends(get_current_user),
    organization_id: str = Depends(require_active_organization),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    from app.modules.similarity.report import SimilarityReportService
    from app.modules.similarity.review import ExclusionPolicy
    from app.modules.similarity.service import SimilarityService
    from app.modules.documents.service import DocumentService

    await reauthorize(db, user)
    report = SimilarityReportService(db)
    document, version, processed = await report.context(
        str(data.document_id), organization_id, str(data.document_version_id)
    )
    await DocumentService(db)._require_mutation_access(document, str(user.id))
    await EntitlementService(db).require_write(
        organization_id, len(processed.cleaned_text or "")
    )

    async def execute():
        await SimilarityService(db).analyze_similarity(str(document.id), processed)
        await reauthorize(db, user)
        return await report.build(
            str(document.id), organization_id, str(version.id), ExclusionPolicy()
        )

    return await execute_metered(
        db,
        user,
        "text_analyze",
        data.operation_id,
        {"endpoint": "plagiarism/check", **data.model_dump(mode="json")},
        execute,
        document_id=str(document.id),
    )
