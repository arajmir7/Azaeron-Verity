"""AZAERON detection schemas."""

from datetime import datetime
from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.modules.detection.models import DetectionVerdict


class DetectionFeatureScores(BaseModel):
    perplexity: Optional[float] = None
    burstiness: Optional[float] = None
    repetition_score: Optional[float] = None
    vocabulary_diversity: Optional[float] = None
    sentence_length_variance: Optional[float] = None
    punctuation_pattern_score: Optional[float] = None
    semantic_consistency: Optional[float] = None
    discourse_marker_score: Optional[float] = None


class DetectionSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    organization_id: str
    document_id: str
    document_version_id: str
    segment_type: str
    segment_index: int
    text: str
    span_start: int
    span_end: int
    verdict: DetectionVerdict
    confidence: Optional[float]
    perplexity: Optional[float] = None
    burstiness: Optional[float] = None
    feature_scores: Optional[DetectionFeatureScores] = None
    explanation: Optional[str] = None


class DetectionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: str
    document_id: str
    model_version: str
    pipeline_version: str
    document_version_id: Optional[str] = None
    release_status: str = "EXPERIMENTAL"
    abstained: bool = True
    overall_verdict: DetectionVerdict
    confidence: Optional[float]
    calibration_score: Optional[float] = None
    human_probability: Optional[float]
    ai_probability: Optional[float]
    mixed_probability: Optional[float]
    uncertain_probability: Optional[float]
    explanation: Optional[str] = None
    limitations: Optional[str] = None
    feature_data: Optional[Dict[str, Any]] = None
    feature_version: str
    calibrator_version: Optional[str] = None
    uncertainty_method: Optional[str] = None
    confidence_reliability: str = "UNAVAILABLE"
    inference_id: str
    inference_metadata_json: Optional[Dict[str, Any]] = None
    evidence_json: Optional[list[Dict[str, Any]]] = None
    abstention_reason: Optional[str] = None
    segments: list[DetectionSegmentResponse] = []
    created_at: datetime

    @model_validator(mode="after")
    def withhold_unvalidated_probabilities(self):
        if (
            self.release_status != "PRODUCTION"
            or self.abstained
            or self.confidence_reliability != "VALIDATED_HELD_OUT"
        ):
            self.abstained = True
            self.confidence = self.calibration_score = None
            self.human_probability = self.ai_probability = None
            self.mixed_probability = self.uncertain_probability = None
            self.overall_verdict = DetectionVerdict.INSUFFICIENT_EVIDENCE
            for segment in self.segments:
                segment.confidence = None
                segment.verdict = DetectionVerdict.INSUFFICIENT_EVIDENCE
        return self

    @computed_field
    def authorship_assessment(
        self,
    ) -> Literal["LIKELY_HUMAN", "LIKELY_MACHINE", "MIXED_OR_EDITED", "INDETERMINATE"]:
        if self.abstained:
            return "INDETERMINATE"
        if self.overall_verdict == DetectionVerdict.HUMAN:
            return "LIKELY_HUMAN"
        if self.overall_verdict in {DetectionVerdict.AI_GENERATED, DetectionVerdict.AI}:
            return "LIKELY_MACHINE"
        if self.overall_verdict in {
            DetectionVerdict.MIXED,
            DetectionVerdict.AI_ASSISTED,
        }:
            return "MIXED_OR_EDITED"
        return "INDETERMINATE"


class DetectionExplainability(BaseModel):
    what_this_means: str
    how_this_was_calculated: str
    evidence_used: list[str]
    what_this_does_not_prove: str
    confidence_interval: Optional[str] = None
    known_limitations: list[str] = []
