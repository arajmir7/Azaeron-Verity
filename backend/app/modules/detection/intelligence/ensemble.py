"""Ensemble orchestration, abstention, and report-safe aggregation."""

from collections import defaultdict
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from app.modules.detection.intelligence.calibration import CalibrationLayer
from app.modules.detection.intelligence.contract import (
    AnalysisSegment,
    Classification,
    DetectorDecision,
    InferenceContext,
    InferenceResult,
    ModelPrediction,
    SignalEvidence,
    SignalStatus,
    ProviderOutput,
)
from app.modules.detection.intelligence.providers import (
    SignalProvider,
    default_signal_providers,
)


class ClassifierModel(Protocol):
    model_id: str
    model_version: str

    def predict(
        self,
        context: InferenceContext,
        segments: Sequence[AnalysisSegment],
        features: Mapping[str, Any],
    ) -> ModelPrediction: ...


class EnsembleOrchestrator:
    model_id = "ai-writing-ensemble"
    pipeline_version = "detector-ensemble-v1"
    feature_version = "signal-features-v1"
    model_version = "ensemble-orchestrator-v1"

    def __init__(
        self,
        providers: Sequence[SignalProvider] | None = None,
        classifiers: Sequence[ClassifierModel] | None = None,
        calibration: CalibrationLayer | None = None,
    ) -> None:
        self.providers = list(providers or default_signal_providers())
        self.classifiers = list(classifiers or [])
        self.calibration = calibration or CalibrationLayer()

    def infer(
        self, context: InferenceContext, segments: Sequence[AnalysisSegment]
    ) -> InferenceResult:
        outputs: list[ProviderOutput] = []
        provider_failures: list[dict[str, str]] = []
        for provider in self.providers:
            try:
                output = provider.extract(context, segments)
                if output.provider_id != provider.provider_id:
                    raise ValueError(
                        "provider output identity does not match the registered provider"
                    )
                outputs.append(output)
            except Exception as error:
                provider_id = getattr(
                    provider, "provider_id", provider.__class__.__name__
                )
                family = getattr(provider, "family", "unknown")
                provider_version = getattr(provider, "provider_version", "unknown")
                provider_failures.append(
                    {"provider_id": provider_id, "error_type": type(error).__name__}
                )
                outputs.append(
                    ProviderOutput(
                        provider_id=provider_id,
                        provider_version=provider_version,
                        family=family,
                        status=SignalStatus.ABSTAINED,
                        features={},
                        evidence=[
                            SignalEvidence(
                                family=family,
                                scope="document",
                                signal_name="provider_failure",
                                summary="The provider failed; its signal was withheld from inference.",
                                status=SignalStatus.ABSTAINED,
                                metadata={"error_type": type(error).__name__},
                            )
                        ],
                    )
                )
        features = {
            output.provider_id: {
                "provider_version": output.provider_version,
                "model_version": output.model_version,
                "family": output.family,
                "status": output.status.value,
                "signal": output.signal,
                "score": output.score,
                "confidence": output.confidence,
                "features": dict(output.features),
                "evidence": [item.as_dict() for item in output.evidence],
            }
            for output in outputs
        }
        evidence = [item for output in outputs for item in output.evidence]
        calibrated = []
        withheld_models = []
        classifier_failures: list[dict[str, str]] = []
        for classifier in self.classifiers:
            try:
                prediction = classifier.predict(context, segments, features)
                calibrated_prediction = self.calibration.calibrate(prediction)
            except Exception as error:
                classifier_failures.append(
                    {
                        "model_id": getattr(classifier, "model_id", "unknown"),
                        "model_version": getattr(
                            classifier, "model_version", "unknown"
                        ),
                        "error_type": type(error).__name__,
                    }
                )
                continue
            if calibrated_prediction is None:
                withheld_models.append(
                    {
                        "model_id": prediction.model_id,
                        "model_version": prediction.model_version,
                    }
                )
            else:
                calibrated.append(calibrated_prediction)

        provider_statuses = {
            output.provider_id: output.status.value for output in outputs
        }
        metadata = {
            "deterministic": True,
            "random_seed": context.metadata.get("random_seed", 0),
            "provider_statuses": provider_statuses,
            "classifier_count": len(self.classifiers),
            "calibrated_classifier_count": len(calibrated),
            "withheld_uncalibrated_models": withheld_models,
            "provider_failures": provider_failures,
            "classifier_failures": classifier_failures,
            "model_id": self.model_id,
            "registry_status": "EXPERIMENTAL",
        }

        if not calibrated:
            limitations = [
                "No calibrated classifier is registered for this environment.",
                "Confidence is unavailable because uncalibrated model output is withheld.",
                "Observed linguistic signals describe text properties; they do not prove who authored the text.",
                "Semantic analysis is unavailable until a validated model is registered.",
                "Authorship consistency was not tested without a validated author baseline.",
            ]
            if provider_failures:
                limitations.append(
                    "One or more signal providers failed and were withheld from inference."
                )
            if classifier_failures:
                limitations.append(
                    "One or more classifier providers failed and were withheld from inference."
                )
            decision = DetectorDecision(
                classification=Classification.INSUFFICIENT_EVIDENCE,
                confidence=None,
                confidence_reliability="UNAVAILABLE",
                abstained=True,
                summary="Independent writing signals were extracted, but the calibrated ensemble abstained from classification.",
                evidence=evidence,
                limitations=limitations,
                feature_data=features,
                calibrator_version=None,
                uncertainty_method=None,
                abstention_reason="CALIBRATED_MODEL_UNAVAILABLE",
                inference_metadata=metadata,
            )
            return InferenceResult(context, decision)

        probabilities: dict[Classification, float] = defaultdict(float)
        for item in calibrated:
            for classification, probability in item.prediction.probabilities.items():
                probabilities[classification] += probability / len(calibrated)
        classification = max(probabilities, key=probabilities.__getitem__)
        confidence = probabilities[classification]
        uncertainty = sum(item.uncertainty for item in calibrated) / len(calibrated)
        abstained = (
            uncertainty >= 0.35
            or confidence < 0.60
            or classification
            in {Classification.UNCERTAIN, Classification.INSUFFICIENT_EVIDENCE}
        )
        if abstained and classification is not Classification.INSUFFICIENT_EVIDENCE:
            classification = Classification.UNCERTAIN
        reliability = (
            "VALIDATED_HELD_OUT"
            if all(item.reliability == "VALIDATED_HELD_OUT" for item in calibrated)
            else "LIMITED"
        )
        lifecycle_status = (
            "PRODUCTION"
            if all(item.lifecycle_status == "PRODUCTION" for item in calibrated)
            else "CANDIDATE"
        )
        metadata.update(
            {
                "registry_status": lifecycle_status,
                "calibrated_models": [
                    {
                        "model_id": item.prediction.model_id,
                        "model_version": item.prediction.model_version,
                        "lifecycle_status": item.lifecycle_status,
                        "calibrator_version": item.calibrator_version,
                    }
                    for item in calibrated
                ],
            }
        )
        limitations = [
            "This calibrated statistical classification is not proof of authorship intent."
        ]
        if provider_failures:
            limitations.append(
                "One or more signal providers failed and were withheld from inference."
            )
        if classifier_failures:
            limitations.append(
                "One or more classifier providers failed and were withheld from inference."
            )
        decision = DetectorDecision(
            classification=classification,
            confidence=round(confidence, 6),
            confidence_reliability=reliability,
            abstained=abstained,
            summary="A calibrated ensemble aggregated registered model outputs with uncertainty estimation.",
            evidence=evidence,
            limitations=limitations,
            feature_data=features,
            calibrator_version=",".join(
                sorted({item.calibrator_version for item in calibrated})
            ),
            uncertainty_method="mean_complement_of_max_probability",
            abstention_reason="ENSEMBLE_UNCERTAINTY" if abstained else None,
            inference_metadata={
                **metadata,
                "probability_states": [item.value for item in probabilities],
            },
        )
        return InferenceResult(context, decision)


def build_default_orchestrator() -> EnsembleOrchestrator:
    """Build the safe default: real signals and explicit operational abstention."""
    return EnsembleOrchestrator()


def create_context(
    organization_id: str,
    document_id: str,
    document_version_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> InferenceContext:
    return InferenceContext(
        organization_id=organization_id,
        document_id=document_id,
        document_version_id=document_version_id,
        pipeline_version=EnsembleOrchestrator.pipeline_version,
        model_version=EnsembleOrchestrator.model_version,
        feature_version=EnsembleOrchestrator.feature_version,
        inference_id=str(uuid4()),
        metadata=dict(metadata or {}),
    )
