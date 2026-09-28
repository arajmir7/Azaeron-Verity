"""Composable, fail-closed intelligence primitives for AI-writing analysis."""

from app.modules.detection.intelligence.contract import (
    AnalysisSegment,
    Classification,
    DetectorDecision,
    InferenceContext,
    InferenceResult,
    ProviderOutput,
    SignalEvidence,
    SignalStatus,
)
from app.modules.detection.intelligence.ensemble import (
    EnsembleOrchestrator,
    build_default_orchestrator,
    create_context,
)

__all__ = [
    "AnalysisSegment",
    "Classification",
    "DetectorDecision",
    "EnsembleOrchestrator",
    "InferenceContext",
    "InferenceResult",
    "ProviderOutput",
    "SignalEvidence",
    "SignalStatus",
    "build_default_orchestrator",
    "create_context",
]
