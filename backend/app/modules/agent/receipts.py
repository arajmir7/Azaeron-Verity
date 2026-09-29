"""Reviewable candidates and one-way, conflict-safe human decisions."""

from dataclasses import asdict
from datetime import datetime, timezone
import difflib
import hashlib
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.permissions import Permission, require_member_permission
from app.modules.agent.models import ActionReceipt, DocumentAttachment
from app.modules.similarity.review import ExclusionPolicy
from app.modules.aegiswrite.invariants import protected_spans
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.billing.entitlements import EntitlementService
from app.modules.billing.usage import UsageService
from app.modules.documents.editor import EditorRevisionService
from app.modules.documents.target import AnalysisTarget

POLICY_REVISION = "verity-agent-1"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def receipt_view(receipt):
    return {
        column.name: getattr(receipt, column.name)
        for column in receipt.__table__.columns
    }


async def propose(
    db,
    *,
    org,
    actor,
    target,
    original,
    candidate,
    verification,
    model_evidence,
    tool_calls,
    run_id=None,
    locked_spans=(),
    similarity_before=None
):
    await require_member_permission(db, org, actor, Permission.EDITORIAL_WRITE)
    await EntitlementService(db).require_write(org, len(candidate))
    if not candidate.strip():
        raise HTTPException(422, "The proposed document cannot be empty")
    dependencies = []
    if run_id:
        from app.modules.agent.models import AgentRun

        run = await db.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.organization_id == org,
                AgentRun.user_id == actor,
            )
        )
        if run:
            dependencies = list(
                (
                    await db.scalars(
                        select(DocumentAttachment.document_id).where(
                            DocumentAttachment.organization_id == org,
                            DocumentAttachment.user_id == actor,
                            DocumentAttachment.conversation_id == run.conversation_id,
                        )
                    )
                ).all()
            )
    model_evidence = {
        **model_evidence,
        "source_dependencies": sorted(set(dependencies)),
    }
    receipt = ActionReceipt(
        organization_id=org,
        user_id=actor,
        run_id=run_id,
        operation_id=str(uuid4()),
        document_id=str(target.document.id),
        source_version_id=str(target.version.id),
        input_sha256=sha(original),
        candidate_sha256=sha(candidate),
        candidate_text=candidate,
        candidate_diff="".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                candidate.splitlines(keepends=True),
                fromfile="source",
                tofile="candidate",
            )
        ),
        model_evidence=model_evidence,
        policy_revision=POLICY_REVISION,
        tool_calls=tool_calls,
        protected_spans=[
            asdict(span) for span in protected_spans(original, locked_spans)
        ],
        verification=verification,
        decision="PENDING",
        similarity_before=similarity_before,
    )
    db.add(receipt)
    await db.flush()
    return receipt


async def decide(db, org, actor, receipt_id, decision, candidate_sha256, storage):
    await require_member_permission(db, org, actor, Permission.EDITORIAL_WRITE)
    # Match the existing usage -> document lock order; receipt follows usage.
    await UsageService(db).lock(org)
    receipt = await db.scalar(
        select(ActionReceipt)
        .where(
            ActionReceipt.id == receipt_id,
            ActionReceipt.organization_id == org,
            ActionReceipt.user_id == actor,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    if (
        candidate_sha256 != receipt.candidate_sha256
        or sha(receipt.candidate_text) != candidate_sha256
    ):
        raise HTTPException(409, "The candidate has changed; review it again")
    if receipt.decision != "PENDING":
        if receipt.decision != decision:
            raise HTTPException(409, "This receipt already has a final decision")
        return receipt_view(receipt)
    target = await AnalysisTarget.resolve(
        db, org, receipt.document_id, receipt.source_version_id
    )
    if decision == "ACCEPTED":
        if receipt.verification.get("outcome") not in {
            "VERIFIED",
            "ATTRIBUTION_REVIEW",
            "USER_REVIEW_REQUIRED",
        }:
            raise HTTPException(
                409, "This candidate did not pass the required verification"
            )
        source = (await target.processed(db)).cleaned_text or ""
        if sha(source) != receipt.input_sha256:
            raise HTTPException(409, "Source text failed its integrity check")
        version = await EditorRevisionService(db, storage).save(
            receipt.document_id,
            org,
            actor,
            receipt.source_version_id,
            receipt.operation_id,
            receipt.candidate_text,
            [],
        )
        receipt.result_version_id = str(version.id)
        receipt.result_sha256 = version.content_hash
        if receipt.similarity_before is not None:
            from app.modules.similarity.service import SimilarityService
            from app.modules.similarity.report import SimilarityReportService

            after = await AnalysisTarget.resolve(
                db, org, receipt.document_id, str(version.id)
            )
            await SimilarityService(db).analyze_similarity(
                receipt.document_id, await after.processed(db)
            )
            report = await SimilarityReportService(db).build(
                receipt.document_id, org, str(version.id), ExclusionPolicy()
            )
            receipt.similarity_after = report.model_dump(mode="json")
    receipt.decision = decision
    receipt.decided_at = datetime.now(timezone.utc)
    await AuditService(db).log(
        (
            AuditAction.WRITING_EDIT_APPLIED
            if decision == "ACCEPTED"
            else AuditAction.WRITING_EDIT_REJECTED
        ),
        "verity_receipt",
        receipt.id,
        details={
            "candidate_sha256": candidate_sha256,
            "result_version_id": receipt.result_version_id,
        },
        user_id=actor,
        organization_id=org,
    )
    await db.flush()
    return receipt_view(receipt)
