"""AI-writing intelligence service with fail-closed classification."""

from dataclasses import replace
import json
import re
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import timed_ml_inference
from app.modules.detection.intelligence.contract import AnalysisSegment, Classification
from app.modules.detection.intelligence.ensemble import (
    EnsembleOrchestrator,
    build_default_orchestrator,
    create_context,
)
from app.modules.detection.models import (
    DetectionResult,
    DetectionSegment,
    DetectionVerdict,
)
from app.modules.documents.models import Document
from app.modules.processing.models import ProcessedDocument
from app.modules.documents.target import require_processed_target
from app.modules.processing.structure import sentence_spans

logger = get_logger(__name__)


class DetectionService:
    PIPELINE_VERSION = "detector-ensemble-v1"
    MODEL_ID = "ai-writing-ensemble"
    MODEL_VERSION = "ensemble-orchestrator-v1"
    FEATURE_VERSION = "signal-features-v1"

    def __init__(
        self, db: AsyncSession, orchestrator: EnsembleOrchestrator | None = None
    ):
        self.db = db
        # Dependency injection is intentional: serving code can load a
        # registry-approved orchestrator, while the default remains the safe
        # no-classifier configuration that abstains.
        self.orchestrator = orchestrator or build_default_orchestrator()

    async def analyze_document(
        self,
        document_id: str,
        processed: ProcessedDocument,
        job_id: str,
        document_version_id: str | None = None,
        analysis_run_id: str | None = None,
        organization_id: str | None = None,
        inference_metadata: Dict[str, Any] | None = None,
    ) -> DetectionResult:
        document_version_id = document_version_id or processed.document_version_id
        organization_id = organization_id or processed.organization_id
        if not organization_id or not document_version_id:
            raise ValueError(
                "Detection requires organization and document version lineage"
            )

        require_processed_target(
            document_id, processed, organization_id, document_version_id
        )
        text = processed.cleaned_text or ""
        segments = self._build_segments(text, processed.structure_json)
        context = create_context(
            organization_id,
            document_id,
            document_version_id,
            metadata={
                "random_seed": 0,
                "revision_count": 1,
                "parser_version": processed.parser_version,
                "normalized_content_hash": processed.normalized_content_hash,
                "structure_fingerprint": processed.structure_fingerprint,
                **(inference_metadata or {}),
            },
        )
        with timed_ml_inference("ai-writing-ensemble"):
            inference = self.orchestrator.infer(context, segments)
        decision = inference.decision
        if len(text) < settings.MIN_DOCUMENT_LENGTH_FOR_ANALYSIS:
            decision = replace(
                decision,
                limitations=tuple(decision.limitations)
                + (
                    f"Documents shorter than {settings.MIN_DOCUMENT_LENGTH_FOR_ANALYSIS} characters are insufficient for reliable classification.",
                ),
                abstention_reason="SHORT_DOCUMENT",
            )
        result = await self._persist_result(
            document_id=document_id,
            job_id=job_id,
            organization_id=organization_id,
            document_version_id=document_version_id,
            analysis_run_id=analysis_run_id,
            context=context,
            decision=decision,
            text=text,
            segments=segments,
        )
        logger.info(
            "detection_analysis_complete",
            document_id=document_id,
            verdict=result.overall_verdict.value,
            abstained=result.abstained,
        )
        return result

    async def _persist_result(
        self,
        document_id: str,
        job_id: str,
        organization_id: str,
        document_version_id: str,
        analysis_run_id: str | None,
        context,
        decision,
        text: str,
        segments: list[AnalysisSegment],
    ) -> DetectionResult:
        result = DetectionResult(
            document_id=document_id,
            job_id=job_id,
            organization_id=organization_id,
            document_version_id=document_version_id,
            analysis_run_id=analysis_run_id,
            model_version=context.model_version,
            pipeline_version=context.pipeline_version,
            feature_version=context.feature_version,
            inference_id=context.inference_id,
            overall_verdict=self._to_db_verdict(decision.classification),
            confidence=decision.confidence,
            calibration_score=(
                decision.confidence if decision.calibrator_version else None
            ),
            human_probability=None,
            ai_probability=None,
            mixed_probability=None,
            uncertain_probability=None,
            explanation=decision.summary,
            limitations=json.dumps(list(decision.limitations)),
            release_status=str(
                decision.inference_metadata.get("registry_status", "EXPERIMENTAL")
            ),
            abstained=decision.abstained,
            feature_data=dict(decision.feature_data),
            calibrator_version=decision.calibrator_version,
            uncertainty_method=decision.uncertainty_method,
            confidence_reliability=decision.confidence_reliability,
            inference_metadata_json=dict(decision.inference_metadata),
            evidence_json=[item.as_dict() for item in decision.evidence],
            abstention_reason=decision.abstention_reason,
        )
        self.db.add(result)
        await self.db.flush()
        await self.db.refresh(result)
        await self._persist_segments(result, text, decision, segments)
        return result

    @staticmethod
    def _to_db_verdict(classification: Classification) -> DetectionVerdict:
        return {
            Classification.HUMAN: DetectionVerdict.HUMAN,
            Classification.AI_GENERATED: DetectionVerdict.AI_GENERATED,
            Classification.AI_ASSISTED: DetectionVerdict.AI_ASSISTED,
            Classification.MIXED: DetectionVerdict.MIXED,
            Classification.UNCERTAIN: DetectionVerdict.UNCERTAIN,
            Classification.INSUFFICIENT_EVIDENCE: DetectionVerdict.INSUFFICIENT_EVIDENCE,
        }[classification]

    @staticmethod
    def _build_segments(
        text: str, structure: dict | None = None
    ) -> list[AnalysisSegment]:
        segments = [
            AnalysisSegment(
                (structure or {}).get("id", "document-0"),
                "document",
                0,
                text,
                0,
                len(text),
            )
        ]
        if structure:
            for key, kind in (("paragraphs", "paragraph"), ("sentences", "sentence")):
                for index, item in enumerate(structure.get(key, [])):
                    segments.append(
                        AnalysisSegment(
                            item["id"],
                            kind,
                            index,
                            text[item["start"] : item["end"]],
                            item["start"],
                            item["end"],
                        )
                    )
            return segments
        # Legacy/test inputs without a persisted structure use the same boundary rules.
        for index, (start, end) in enumerate(sentence_spans(text)):
            segments.append(
                AnalysisSegment(
                    f"sentence-{index}", "sentence", index, text[start:end], start, end
                )
            )
        for index, match in enumerate(re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text)):
            segments.append(
                AnalysisSegment(
                    f"paragraph-{index}",
                    "paragraph",
                    index,
                    match.group(),
                    match.start(),
                    match.end(),
                )
            )
        return segments

    async def _persist_segments(
        self,
        result: DetectionResult,
        text: str,
        decision,
        segments: list[AnalysisSegment],
    ) -> None:
        document_features = dict(
            decision.feature_data.get("document-signals", {}).get("features", {})
        )
        segment_features = dict(
            decision.feature_data.get("segment-signals", {}).get("features", {})
        )
        sentence_segments = [
            segment for segment in segments if segment.segment_type == "sentence"
        ]
        lineage = {
            "organization_id": result.organization_id,
            "document_id": result.document_id,
            "document_version_id": result.document_version_id,
        }
        self.db.add(
            DetectionSegment(
                **lineage,
                detection_result_id=result.id,
                segment_type="document",
                segment_index=0,
                text=text,
                span_start=0,
                span_end=len(text),
                verdict=DetectionVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                feature_scores=document_features,
                explanation="Document-level signals were extracted; no authorship classification was asserted.",
            )
        )
        for index, item in enumerate(
            segment_features.get("segments", [])[:50], start=1
        ):
            segment = (
                sentence_segments[index - 1]
                if index - 1 < len(sentence_segments)
                else None
            )
            self.db.add(
                DetectionSegment(
                    **lineage,
                    detection_result_id=result.id,
                    segment_type="sentence",
                    segment_index=index,
                    text=segment.text if segment else "",
                    span_start=segment.start_char if segment else 0,
                    span_end=segment.end_char if segment else 0,
                    verdict=DetectionVerdict.INSUFFICIENT_EVIDENCE,
                    confidence=0.0,
                    feature_scores=item,
                    explanation="Segment-level signal extracted; classification abstained.",
                )
            )
        await self.db.flush()
