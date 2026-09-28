"""Auditable authorship consistency analysis.

The service compares a document with a minimum-quality historical baseline.
It reports stylistic distance separately from AI-writing analysis and never
turns either signal into an identity claim.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.authorship.intelligence import (
    AuthorshipFeatureAnalyzer,
    MIN_DOCUMENT_WORDS,
    data_adequacy_confidence,
)
from app.modules.authorship.models import AuthorshipProfile, AuthorshipSignal
from app.modules.evidence.models import EvidenceNodeType
from app.modules.evidence.service import EvidenceService
from app.modules.processing.models import ProcessedDocument
from app.modules.documents.target import require_processed_target

logger = get_logger(__name__)

PIPELINE_VERSION = "authorship-consistency-v3"
MODEL_VERSION = "authorship-statistics-v2"
AI_SIGNAL_VERSION = "ai-writing-signal-not-tested-v1"


class AuthorshipService:
    """Build profiles and compare documents without identifying authors."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.analyzer = AuthorshipFeatureAnalyzer()

    async def build_profile(
        self,
        profile: AuthorshipProfile,
        baseline_documents: Sequence[ProcessedDocument],
    ) -> AuthorshipProfile:
        texts = [
            (
                f"{processed.document_id}:{processed.document_version_id}",
                processed.cleaned_text or processed.raw_text or "",
            )
            for processed in baseline_documents
        ]
        structures = {
            f"{p.document_id}:{p.document_version_id}": p.structure_json
            for p in baseline_documents
        }
        bundle = self.analyzer.build_baseline(texts, structures)
        policies = {self._boundary_policy(p) for p in baseline_documents}
        bundle["boundary_policy"] = (
            next(iter(policies)) if len(policies) == 1 else "MIXED"
        )
        bundle["structure_fingerprints"] = [
            p.structure_fingerprint for p in baseline_documents
        ]
        profile.baseline_document_ids = [
            str(processed.document_id) for processed in baseline_documents
        ]
        bundle["baseline_version_ids"] = [
            str(processed.document_version_id) for processed in baseline_documents
        ]
        profile.stylometric_features = bundle
        distributions = bundle.get("distributions") or {}
        profile.vocabulary_distribution = distributions.get("lexical_distribution")
        profile.punctuation_patterns = distributions.get("punctuation_distribution")
        profile.syntax_patterns = {
            key: value
            for key, value in (bundle.get("scalar_stats") or {}).items()
            if key
            in {
                "clause_marker_rate",
                "subordination_marker_rate",
                "sentence_complexity_proxy",
            }
        }
        await self.db.flush()
        return profile

    async def analyze_authorship(
        self,
        document_id: str,
        processed: ProcessedDocument,
        profile_id: Optional[str] = None,
    ) -> AuthorshipSignal:
        self._require_lineage(processed)
        require_processed_target(document_id, processed)
        text = processed.cleaned_text or processed.raw_text or ""
        target = self.analyzer.extract(
            text,
            f"document:{document_id}:version:{processed.document_version_id}",
            processed.structure_json,
        )
        profile = await self._load_profile(profile_id, str(processed.organization_id))
        baseline = await self._load_baseline(profile, processed)
        if profile and baseline.get(
            "boundary_policy", "legacy-authorship-boundaries"
        ) != self._boundary_policy(processed):
            baseline = {
                **baseline,
                "baseline_quality": "INSUFFICIENT",
                "quality_reasons": [
                    "The frozen baseline uses different document boundaries; create a baseline from compatible parsed versions."
                ],
            }
        comparison = self.analyzer.compare(target, baseline)
        eligible = bool(comparison.get("eligible"))
        deviation = comparison.get("stylistic_deviation")
        verdict = self._verdict(deviation) if eligible else "INSUFFICIENT_DATA"
        confidence = (
            data_adequacy_confidence(baseline, target.word_count) if eligible else None
        )

        stylistic_deviation = {
            "status": "MEASURED" if eligible else "INSUFFICIENT_DATA",
            "score": deviation,
            "verdict": verdict,
            "signals": comparison.get("signals", []),
            "family_scores": comparison.get("family_scores", {}),
            "method": comparison.get("comparison_method", "baseline_quality_gate-v1"),
        }
        ai_writing_signal = self._ai_writing_signal()
        limitations = self._limitations(baseline, target.word_count, eligible)
        explanation = self._explanation(verdict, baseline, eligible)
        feature_data = {
            "feature_version": self.analyzer.feature_version,
            "boundary_policy": self._boundary_policy(processed),
            "parser_version": processed.parser_version,
            "structure_fingerprint": processed.structure_fingerprint,
            "target": target.as_dict(),
            "baseline": self._public_baseline(baseline),
            "signals": comparison.get("signals", []),
            "family_scores": comparison.get("family_scores", {}),
            "separation": {
                "stylistic_deviation": stylistic_deviation,
                "ai_writing_signal": ai_writing_signal,
                "authorship_conclusion": {
                    "verdict": verdict,
                    "confidence_type": (
                        "data_adequacy_not_identity_probability"
                        if confidence is not None
                        else None
                    ),
                },
            },
        }

        signal = AuthorshipSignal(
            document_id=document_id,
            organization_id=str(processed.organization_id),
            document_version_id=str(processed.document_version_id),
            pipeline_version=PIPELINE_VERSION,
            model_version=MODEL_VERSION,
            profile_id=profile_id,
            consistency_score=(
                round(1.0 - float(deviation), 6) if deviation is not None else None
            ),
            confidence=confidence,
            verdict=verdict,
            baseline_quality=str(
                baseline.get("baseline_quality") or "MISSING_BASELINE"
            ),
            feature_data=feature_data,
            stylistic_deviation=stylistic_deviation,
            ai_writing_signal=ai_writing_signal,
            confidence_type=(
                "data_adequacy_not_identity_probability"
                if confidence is not None
                else None
            ),
            stylistic_drift_score=deviation,
            unusual_segments=[],
            explanation=explanation,
            limitations=json.dumps(limitations),
        )
        self.db.add(signal)
        await self.db.flush()

        evidence = await EvidenceService(self.db).add_node(
            document_id=document_id,
            node_type=EvidenceNodeType.AUTHORSHIP,
            title="Authorship consistency statistics",
            description=explanation,
            confidence=confidence or 0.0,
            metadata={
                "signal_id": str(signal.id),
                "baseline_quality": signal.baseline_quality,
                "authorship_conclusion": verdict,
                "stylistic_deviation": stylistic_deviation,
                "ai_writing_signal": ai_writing_signal,
                "limitations": limitations,
                "identity_claim_not_made": True,
            },
            document_version_id=str(processed.document_version_id),
            finding_type="authorship_consistency",
            source_id=str(signal.id),
            model_id="authorship-consistency",
            model_version=MODEL_VERSION,
            pipeline_version=PIPELINE_VERSION,
        )
        signal.evidence_id = str(evidence.id)
        await self.db.flush()
        await self.db.refresh(signal)

        logger.info(
            "authorship_consistency_analyzed",
            document_id=document_id,
            profile_id=profile_id,
            verdict=verdict,
            baseline_quality=signal.baseline_quality,
        )
        return signal

    @staticmethod
    def _boundary_policy(processed: ProcessedDocument) -> str:
        return (
            f"stored:{processed.parser_version}"
            if processed.structure_json
            else "legacy-authorship-boundaries"
        )

    async def _load_profile(
        self, profile_id: str | None, organization_id: str
    ) -> AuthorshipProfile | None:
        if not profile_id:
            return None
        return (
            await self.db.execute(
                select(AuthorshipProfile).where(
                    AuthorshipProfile.id == profile_id,
                    AuthorshipProfile.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()

    async def _load_baseline(
        self,
        profile: AuthorshipProfile | None,
        processed: ProcessedDocument,
    ) -> dict[str, Any]:
        if profile is None:
            return {
                "baseline_quality": "MISSING_BASELINE",
                "quality_reasons": ["A historical writing baseline was not supplied."],
                "sample_count": 0,
                "total_words": 0,
            }
        if str(processed.document_id) in (profile.baseline_document_ids or []):
            return {
                "baseline_quality": "INSUFFICIENT",
                "quality_reasons": [
                    "The analysis target cannot be its own historical baseline."
                ],
                "sample_count": 0,
                "total_words": 0,
            }
        if profile.stylometric_features:
            return dict(profile.stylometric_features)
        return {
            "baseline_quality": "INSUFFICIENT",
            "quality_reasons": [
                "The selected baseline documents have not been processed."
            ],
            "sample_count": 0,
            "total_words": 0,
        }

    @staticmethod
    def _verdict(deviation: float | None) -> str:
        if deviation is None:
            return "INSUFFICIENT_DATA"
        if deviation < 0.25:
            return "CONSISTENT"
        if deviation < 0.50:
            return "DEVIATION"
        return "STRONG_DEVIATION"

    @staticmethod
    def _ai_writing_signal() -> dict[str, Any]:
        return {
            "status": "NOT_TESTED",
            "classification": "INSUFFICIENT_EVIDENCE",
            "confidence": None,
            "model_version": AI_SIGNAL_VERSION,
            "summary": "Stylistic deviation was not converted into an AI-writing signal.",
            "evidence": [],
            "limitations": [
                "No validated AI-writing classifier was invoked by authorship consistency analysis.",
                "A style difference does not establish AI assistance or generation.",
            ],
        }

    @staticmethod
    def _public_baseline(baseline: dict[str, Any]) -> dict[str, Any]:
        return {
            key: baseline.get(key)
            for key in (
                "feature_version",
                "baseline_quality",
                "quality_reasons",
                "sample_count",
                "total_words",
                "min_document_words",
                "source_fingerprint",
                "scalar_stats",
            )
            if key in baseline
        }

    @staticmethod
    def _limitations(
        baseline: dict[str, Any], target_words: int, eligible: bool
    ) -> list[str]:
        limitations = [
            "This compares writing style with a supplied baseline; it does not identify a person.",
            "A deviation is not a deterministic authorship accusation and is not proof of AI use.",
            "Topic, genre, language, editing, translation, collaboration, and writing context can change stylistic statistics.",
            "Syntax is represented by conservative surface proxies; no validated parser or authorship classifier is used.",
            "Confidence is data-adequacy confidence, not the probability that a person authored the document.",
        ]
        if not eligible:
            limitations.append(
                "The minimum baseline or target quality gate was not met; authorship consistency abstained."
            )
        limitations.extend(baseline.get("quality_reasons") or [])
        if target_words < MIN_DOCUMENT_WORDS:
            limitations.append(
                f"Target text has fewer than {MIN_DOCUMENT_WORDS} words for stable comparison."
            )
        return list(dict.fromkeys(limitations))

    @staticmethod
    def _explanation(verdict: str, baseline: dict[str, Any], eligible: bool) -> str:
        if not eligible:
            return (
                "Authorship consistency abstained because the supplied historical baseline or target text did not meet "
                "the minimum quality gate. No identity or AI-writing conclusion was made."
            )
        return (
            f"The target document was statistically compared with a {baseline.get('baseline_quality', 'unknown').lower()} "
            f"historical baseline and classified as {verdict}. This is a style-consistency result only; it does not identify an author."
        )

    @staticmethod
    def _require_lineage(processed: ProcessedDocument) -> None:
        if (
            not processed.organization_id
            or not processed.document_version_id
            or not processed.pipeline_version
        ):
            raise ValueError("Authorship analysis requires complete document lineage")
