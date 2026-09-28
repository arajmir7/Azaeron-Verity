"""Compatibility exports for the versioned detector intelligence contracts."""

from app.modules.detection.intelligence.calibration import (
    CalibrationLayer,
    CalibrationSpec,
)
from app.modules.detection.intelligence.contract import (
    AnalysisSegment,
    CalibratedPrediction,
    Classification,
    DetectorDecision,
    InferenceContext,
    InferenceResult,
    ModelPrediction,
    ProviderOutput,
    SignalEvidence,
    SignalStatus,
)
from app.modules.detection.intelligence.ensemble import (
    ClassifierModel,
    EnsembleOrchestrator,
)
from app.modules.detection.intelligence.providers import SignalProvider

__all__ = [
    "AnalysisSegment",
    "CalibrationLayer",
    "CalibrationSpec",
    "CalibratedPrediction",
    "Classification",
    "ClassifierModel",
    "DetectorDecision",
    "EnsembleOrchestrator",
    "InferenceContext",
    "InferenceResult",
    "ModelPrediction",
    "ProviderOutput",
    "SignalEvidence",
    "SignalProvider",
    "SignalStatus",
]
