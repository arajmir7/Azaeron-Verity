"""Typed tools selected by authenticated UI intent, never by retrieved instructions."""

import difflib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.orm import lazyload

from app.core.permissions import Permission, require_member_permission
from app.modules.agent.models import DocumentAttachment, Message, AgentEvent, AgentRun
from app.modules.agent.receipts import propose, sha
from app.modules.agent.schemas import (
    Attachment,
    SearchTool,
    CompareTool,
    ReadTool,
    RefineTool,
    ResolveTool,
    VersionTool,
)
from app.modules.documents.models import Document, DocumentStatus
from app.modules.documents.target import AnalysisTarget
from app.core.database import apply_tenant_context
from app.modules.similarity.review import ExclusionPolicy
from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.service import gateway
from app.modules.verification.service import verify_text


async def attach(db, run, attachment: Attachment):
    target = await AnalysisTarget.resolve(
        db,
        run.organization_id,
        str(attachment.document_id),
        str(attachment.document_version_id),
        lock=True,
    )
    if (
        target.document.erasure_pending
        or target.document.status == DocumentStatus.ARCHIVED
    ):
        raise HTTPException(404, "Document not found")
    processed = await target.processed(db)
    text = processed.cleaned_text or ""
    if len(text) > 60_000:
        raise HTTPException(422, "This document exceeds the agent context limit")
    existing = await db.scalar(
        select(DocumentAttachment).where(
            DocumentAttachment.organization_id == run.organization_id,
            DocumentAttachment.user_id == run.user_id,
            DocumentAttachment.conversation_id == run.conversation_id,
            DocumentAttachment.document_version_id == str(target.version.id),
        )
    )
    if existing is None:
        db.add(
            DocumentAttachment(
                organization_id=run.organization_id,
                user_id=run.user_id,
                conversation_id=run.conversation_id,
                document_id=str(target.document.id),
                document_version_id=str(target.version.id),
                input_sha256=sha(text),
            )
        )
        await db.flush()
    elif existing.input_sha256 != sha(text):
        raise HTTPException(409, "Attachment integrity check failed")
    return target, text


async def execute_tool(db, run, tool):
    # Durable membership is checked again in the worker for every tool, including reads.
    await require_member_permission(
        db, run.organization_id, run.user_id, Permission.EDITORIAL_WRITE
    )
    if isinstance(tool, SearchTool):
        # Literal substring search is bounded, tenant scoped, parameterized and never semantic by implication.
        docs = (
            await db.scalars(
                select(Document)
                .options(lazyload("*"))
                .where(
                    Document.organization_id == run.organization_id,
                    Document.erasure_pending.is_(False),
                    Document.status == DocumentStatus.COMPLETED,
                    or_(
                        Document.title.contains(tool.query, autoescape=True),
                        Document.original_filename.contains(
                            tool.query, autoescape=True
                        ),
                    ),
                )
                .order_by(Document.updated_at.desc(), Document.id)
                .limit(10)
            )
        ).all()
        items = []
        for doc in docs:
            target = await AnalysisTarget.resolve(db, run.organization_id, str(doc.id))
            await attach(
                db,
                run,
                Attachment(
                    document_id=UUID(str(doc.id)),
                    document_version_id=UUID(str(target.version.id)),
                ),
            )
            items.append(
                {
                    "document_id": str(doc.id),
                    "document_version_id": str(target.version.id),
                    "title": doc.title or doc.original_filename,
                }
            )
        return {"method": "private-workspace-title-search-v1", "items": items}
    target, original = await attach(db, run, tool)
    identity = {
        "document_id": str(target.document.id),
        "document_version_id": str(target.version.id),
        "input_sha256": sha(original),
    }
    if isinstance(tool, CompareTool):
        other, other_text = await attach(db, run, tool.other)
        return {
            **identity,
            "other_version_id": str(other.version.id),
            "method": "text-diff-v1",
            "diff": "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    other_text.splitlines(keepends=True),
                    fromfile="source",
                    tofile="comparison",
                )
            ),
        }
    if isinstance(tool, ReadTool):
        if tool.name == "document.read":
            return {**identity, "text": original, "trust": "UNTRUSTED_DOCUMENT_DATA"}
        if tool.name == "document.summarize":
            await db.commit()
            await apply_tenant_context(db, run.organization_id, run.user_id)
            result = await gateway().run(
                AzaeronInferenceJob(
                    operation_id=UUID(run.id),
                    organization_id=UUID(run.organization_id),
                    user_id=UUID(run.user_id),
                    task="summarize",
                    text=json.dumps({"untrusted_document": original}),
                )
            )
            run.model_evidence = result.model_dump(mode="json", exclude={"output"})
            return {
                **identity,
                "summary": result.output,
                "model_evidence": run.model_evidence,
                "limitations": [
                    "Generated summary requires review against the cited version."
                ],
            }
        if tool.name == "detection.analyze":
            from app.modules.detection.intelligence.ensemble import (
                build_default_orchestrator,
                create_context,
            )
            from app.modules.detection.service import DetectionService

            context = create_context(
                run.organization_id, str(target.document.id), str(target.version.id)
            )
            inference = build_default_orchestrator().infer(
                context, DetectionService._build_segments(original)
            )
            from dataclasses import asdict

            decision = asdict(inference.decision)
            # Keep public probabilities withheld without calibrated production approval.
            return {
                **identity,
                "label": "Uncertain",
                "calibrated_probability": None,
                "status": "EXPERIMENTAL",
                "evidence": json.loads(json.dumps(decision, default=str)),
                "limitation": "Evidence, not an accusation. No calibrated production classifier is available.",
            }
        if tool.name == "citation.inspect":
            from app.modules.citations.models import Citation, Reference

            citations = (
                await db.scalars(
                    select(Citation).where(
                        Citation.organization_id == run.organization_id,
                        Citation.document_version_id == str(target.version.id),
                    )
                )
            ).all()
            references = (
                await db.scalars(
                    select(Reference).where(
                        Reference.organization_id == run.organization_id,
                        Reference.document_version_id == str(target.version.id),
                    )
                )
            ).all()
            return {
                **identity,
                "citations": [
                    {
                        "id": c.id,
                        "text": c.raw_text,
                        "support_status": c.support_status.value,
                    }
                    for c in citations
                ],
                "references": [
                    {"id": r.id, "title": r.title, "doi": r.doi, "url": r.url}
                    for r in references
                ],
                "limitation": "Recorded evidence only; arbitrary URLs are never fetched.",
            }
        from app.modules.similarity.service import SimilarityService
        from app.modules.similarity.report import SimilarityReportService

        await SimilarityService(db).analyze_similarity(
            str(target.document.id), await target.processed(db)
        )
        report = await SimilarityReportService(db).build(
            str(target.document.id),
            run.organization_id,
            str(target.version.id),
            ExclusionPolicy(),
        )
        for match in report.matches.items:
            await attach(
                db,
                run,
                Attachment(
                    document_id=UUID(match.source_document_id),
                    document_version_id=UUID(match.source_document_version_id),
                ),
            )
        return {**identity, "analysis": report.model_dump(mode="json")}
    evidence = {}
    verification = {
        "outcome": "USER_REVIEW_REQUIRED",
        "semantic_checked": False,
        "limitations": ["Saving generated text does not verify its factual accuracy."],
    }
    locked = []
    before = None
    if isinstance(tool, RefineTool):
        voice = None
        if tool.voice_profile_id:
            from app.modules.agent.voice import resolve_profile
            from app.modules.inference.gateway import VoiceStyle

            profile = await resolve_profile(
                db, run.organization_id, run.user_id, tool.voice_profile_id
            )
            voice = VoiceStyle.model_validate(profile.style)
            for sample in profile.samples:
                await attach(
                    db,
                    run,
                    Attachment(
                        document_id=UUID(sample["document_id"]),
                        document_version_id=UUID(sample["document_version_id"]),
                    ),
                )
        start, end = tool.selection or (0, len(original))
        if not 0 <= start < end <= len(original) or any(
            not 0 <= a < b <= len(original) for a, b in tool.locked_spans
        ):
            raise HTTPException(422, "Selection or locked span is outside this version")
        locked = list(tool.locked_spans)
        if start:
            locked.append((0, start))
        if end < len(original):
            locked.append((end, len(original)))
        from app.modules.aegiswrite.invariants import protected_spans

        invariants = protected_spans(original, locked)
        await db.commit()
        await apply_tenant_context(db, run.organization_id, run.user_id)
        private = gateway()
        result = await private.run(
            AzaeronInferenceJob(
                operation_id=UUID(run.id),
                organization_id=UUID(run.organization_id),
                user_id=UUID(run.user_id),
                task="refine",
                text=original[start:end],
                focus=tool.focus,
                voice_style=voice,
            )
        )
        candidate = original[:start] + result.output + original[end:]
        verified = await verify_text(
            original,
            candidate,
            operation_id=UUID(run.id),
            organization_id=UUID(run.organization_id),
            user_id=UUID(run.user_id),
            locked_spans=locked,
            gateway=private,
            writing_model_id=result.model_id,
            writing_model_revision=result.model_revision,
        )
        verification = verified.model_dump(mode="json")
        evidence = result.model_dump(mode="json", exclude={"output"})
        if tool.voice_profile_id:
            evidence["voice_profile_id"] = str(tool.voice_profile_id)
            evidence["voice_policy"] = "voice-style-statistics-1"
        evidence["invariants_extracted_before_generation"] = len(invariants)
        run.model_evidence = evidence
    elif isinstance(tool, VersionTool):
        message = await db.scalar(
            select(Message).where(
                Message.id == str(tool.message_id),
                Message.organization_id == run.organization_id,
                Message.user_id == run.user_id,
                Message.conversation_id == run.conversation_id,
                Message.role == "assistant",
            )
        )
        if message is None:
            raise HTTPException(404, "Assistant message not found")
        candidate = message.content
        source_run = await db.scalar(
            select(AgentRun)
            .join(AgentEvent, AgentEvent.run_id == AgentRun.id)
            .where(
                AgentRun.organization_id == run.organization_id,
                AgentRun.user_id == run.user_id,
                AgentRun.conversation_id == run.conversation_id,
                AgentEvent.organization_id == run.organization_id,
                AgentEvent.user_id == run.user_id,
                AgentEvent.kind == "message",
                AgentEvent.payload["message_id"].as_string() == str(message.id),
            )
            .limit(1)
        )
        if source_run is None or not source_run.model_evidence:
            raise HTTPException(
                409, "This assistant message has no recorded model evidence"
            )
        evidence = {
            **source_run.model_evidence,
            "source_message_id": str(message.id),
            "source_run_id": str(source_run.id),
        }
    elif isinstance(tool, ResolveTool):
        from app.modules.similarity.models import SimilarityMatch
        from app.modules.similarity.report import SimilarityReportService

        match = await db.scalar(
            select(SimilarityMatch).where(
                SimilarityMatch.id == str(tool.match_id),
                SimilarityMatch.organization_id == run.organization_id,
                SimilarityMatch.document_id == str(target.document.id),
                SimilarityMatch.document_version_id == str(target.version.id),
            )
        )
        if match is None:
            raise HTTPException(404, "Match not found")
        await attach(
            db,
            run,
            Attachment(
                document_id=UUID(str(match.source_document_id)),
                document_version_id=UUID(str(match.source_document_version_id)),
            ),
        )
        start, end = match.document_span_start, match.document_span_end
        if not 0 <= start < end <= len(original):
            raise HTTPException(409, "Match offsets are unavailable")
        if (
            tool.action
            in {"add_citation", "quote_and_cite", "paraphrase_with_attribution"}
            and not tool.citation.strip()
        ):
            raise HTTPException(422, "A source citation is required")
        before = (
            await SimilarityReportService(db).build(
                str(target.document.id),
                run.organization_id,
                str(target.version.id),
                ExclusionPolicy(),
            )
        ).model_dump(mode="json")
        passage = original[start:end]
        if tool.action == "paraphrase_with_attribution":
            await db.commit()
            await apply_tenant_context(db, run.organization_id, run.user_id)
            private = gateway()
            result = await private.run(
                AzaeronInferenceJob(
                    operation_id=UUID(run.id),
                    organization_id=UUID(run.organization_id),
                    user_id=UUID(run.user_id),
                    task="refine",
                    text=passage,
                )
            )
            verified = await verify_text(
                passage,
                result.output,
                operation_id=UUID(run.id),
                organization_id=UUID(run.organization_id),
                user_id=UUID(run.user_id),
                gateway=private,
                writing_model_id=result.model_id,
                writing_model_revision=result.model_revision,
            )
            verification = verified.model_dump(mode="json")
            evidence = result.model_dump(mode="json", exclude={"output"})
            replacement = result.output + " " + tool.citation.strip()
        else:
            replacement = {
                "add_citation": passage + " " + tool.citation.strip(),
                "quote_and_cite": "“" + passage + "” " + tool.citation.strip(),
                "remove_duplicate": "",
                "keep_legitimate": passage,
            }[tool.action]
            verification = {
                "outcome": "ATTRIBUTION_REVIEW",
                "semantic_checked": False,
                "limitations": [
                    "User must review the source, citation accuracy and the reason for this resolution."
                ],
                "rationale": tool.rationale,
            }
        candidate = original[:start] + replacement + original[end:]
    else:
        raise HTTPException(422, "Unknown tool")
    receipt = await propose(
        db,
        org=run.organization_id,
        actor=run.user_id,
        target=target,
        original=original,
        candidate=candidate,
        verification=verification,
        model_evidence=evidence,
        tool_calls=[tool.model_dump(mode="json")],
        run_id=str(run.id),
        locked_spans=locked,
        similarity_before=before,
    )
    return {
        **identity,
        "receipt_id": str(receipt.id),
        "candidate": candidate,
        "candidate_sha256": receipt.candidate_sha256,
        "verification": verification,
        "confirmation_required": True,
    }
