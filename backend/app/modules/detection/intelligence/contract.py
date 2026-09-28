"""Stable contracts shared by signal providers, models, and reports.

The public contract deliberately separates observed evidence from a model
decision. Provider features are not authorship claims and model probabilities
never leave the orchestration/calibration boundary unmarked.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import Any, Dict, Mapping, Optional, Sequence


class Classification(str, Enum):
    HUMAN = "human"
    AI_GENERATED = "ai_generated"
    AI_ASSISTED = "ai_assisted"
    MIXED = "mixed"
    UNCERTAIN = "uncertain"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SignalStatus(str, Enum):
    OBSERVED = "observed"
    UNAVAILABLE = "unavailable"
    EXPERIMENTAL = "experimental"
    ABSTAINED = "abstained"


@dataclass(frozen=True)
class AnalysisSegment:
    segment_id: str
    segment_type: str
    index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class InferenceContext:
    organization_id: str
    document_id: str
    document_version_id: str
    pipeline_version: str
    model_version: str
    feature_version: str
    inference_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalEvidence:
    family: str
    scope: str
    signal_name: str
    summary: str
    status: SignalStatus
    value: Optional[float] = None
    segment_index: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provider_id: Optional[str] = None
    provider_version: Optional[str] = None
    model_version: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "scope": self.scope,
            "signal_name": self.signal_name,
            "summary": self.summary,
            "status": self.status.value,
            "value": self.value,
            "segment_index": self.segment_index,
            "metadata": dict(self.metadata),
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "model_version": self.model_version,
        }


@dataclass(frozen=True)
class ProviderOutput:
    provider_id: str
    provider_version: str
    family: str
    status: SignalStatus
    features: Mapping[str, Any]
    evidence: Sequence[SignalEvidence]
    # A provider may expose a normalized score only when it has a defined,
    # validated interpretation. Descriptive feature extractors leave score and
    # confidence unset rather than inventing an AI probability.
    signal: str = ""
    score: Optional[float] = None
    confidence: Optional[float] = None
    model_version: Optional[str] = None

    def __post_init__(self) -> None:
        for name, value in (("score", self.score), ("confidence", self.confidence)):
            if value is not None and (
                not isfinite(float(value)) or not 0 <= float(value) <= 1
            ):
                raise ValueError(f"Provider {name} must be a finite value in [0, 1]")
        object.__setattr__(self, "signal", self.signal or self.family)
        object.__setattr__(
            self, "model_version", self.model_version or self.provider_version
        )
        object.__setattr__(
            self,
            "evidence",
            tuple(
                replace(
                    item,
                    provider_id=item.provider_id or self.provider_id,
                    provider_version=item.provider_version or self.provider_version,
                    model_version=item.model_version or self.model_version,
                )
                for item in self.evidence
            ),
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "family": self.family,
            "status": self.status.value,
            "signal": self.signal,
            "score": self.score,
            "confidence": self.confidence,
            "model_version": self.model_version,
            "features": dict(self.features),
            "evidence": [item.as_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class ModelPrediction:
    """Private ensemble input; never serialize this object directly."""

    model_id: str
    model_version: str
    probabilities: Mapping[Classification, float]
    raw_evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibratedPrediction:
    prediction: ModelPrediction
    calibrator_version: str
    uncertainty: float
    reliability: str
    lifecycle_status: str = "CANDIDATE"


@dataclass(frozen=True)
class DetectorDecision:
    classification: Classification
    confidence: Optional[float]
    confidence_reliability: str
    abstained: bool
    summary: str
    evidence: Sequence[SignalEvidence]
    limitations: Sequence[str]
    feature_data: Mapping[str, Any]
    calibrator_version: Optional[str]
    uncertainty_method: Optional[str]
    abstention_reason: Optional[str]
    inference_metadata: Mapping[str, Any]


@dataclass(frozen=True)
class InferenceResult:
    context: InferenceContext
    decision: DetectorDecision
