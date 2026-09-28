import pytest

from app.modules.detection.intelligence.calibration import (
    CalibrationLayer,
    CalibrationSpec,
)
from app.modules.detection.intelligence.contract import (
    AnalysisSegment,
    Classification,
    InferenceContext,
    ModelPrediction,
    ProviderOutput,
    SignalStatus,
)
from app.modules.detection.intelligence.ensemble import (
    EnsembleOrchestrator,
    create_context,
)
from app.modules.detection.intelligence.providers import LinguisticSignalProvider


def _segments() -> list[AnalysisSegment]:
    text = "A measured sentence describes the input. A second sentence records a separate observation."
    return [
        AnalysisSegment("document-0", "document", 0, text, 0, len(text)),
        AnalysisSegment("paragraph-1", "paragraph", 1, text, 0, len(text)),
        AnalysisSegment("sentence-0", "sentence", 0, text.split(". ")[0] + ".", 0, 40),
        AnalysisSegment(
            "sentence-1", "sentence", 1, text.split(". ")[1], 41, len(text)
        ),
    ]


def test_default_ensemble_extracts_signals_and_abstains_without_calibration():
    context = create_context("org-1", "doc-1", "version-1")
    result = EnsembleOrchestrator().infer(context, _segments())
    decision = result.decision

    assert set(Classification) == {
        Classification.HUMAN,
        Classification.AI_GENERATED,
        Classification.AI_ASSISTED,
        Classification.MIXED,
        Classification.UNCERTAIN,
        Classification.INSUFFICIENT_EVIDENCE,
    }
    assert decision.classification is Classification.INSUFFICIENT_EVIDENCE
    assert decision.abstained is True
    assert decision.confidence is None
    assert decision.confidence_reliability == "UNAVAILABLE"
    assert decision.abstention_reason == "CALIBRATED_MODEL_UNAVAILABLE"
    assert decision.inference_metadata["deterministic"] is True
    assert "probabilities" not in decision.feature_data
    assert {item.family for item in decision.evidence} == {
        "linguistic",
        "stylometric",
        "syntactic",
        "segment-level",
        "document-level",
        "semantic",
        "authorship-consistency",
        "revision/provenance",
    }


def test_calibration_requires_held_out_dataset():
    layer = CalibrationLayer()
    with pytest.raises(ValueError, match="held-out"):
        layer.register(
            CalibrationSpec(
                "model", "v1", "cal-v1", "dataset-v1", "entropy", held_out=False
            ),
            lambda probabilities: probabilities,
        )


def test_production_calibration_requires_a_passing_validation_gate():
    layer = CalibrationLayer()
    with pytest.raises(ValueError, match="passing held-out validation gate"):
        layer.register(
            CalibrationSpec(
                "model",
                "v1",
                "cal-v1",
                "dataset-v1",
                "entropy",
                held_out=True,
                lifecycle_status="PRODUCTION",
                validation_report={"promotion_allowed": False},
            ),
            lambda probabilities: probabilities,
        )


class UncalibratedClassifier:
    model_id = "unvalidated-model"
    model_version = "v0"

    def predict(self, context, segments, features):
        return ModelPrediction(
            self.model_id,
            self.model_version,
            {
                classification: 1 / len(Classification)
                for classification in Classification
            },
            {"private_raw_signal": "withheld"},
        )


def test_uncalibrated_classifier_output_is_withheld():
    result = EnsembleOrchestrator(classifiers=[UncalibratedClassifier()]).infer(
        create_context("org-1", "doc-1", "version-1"), _segments()
    )
    assert result.decision.abstained is True
    assert result.decision.inference_metadata["calibrated_classifier_count"] == 0
    assert result.decision.inference_metadata["withheld_uncalibrated_models"] == [
        {"model_id": "unvalidated-model", "model_version": "v0"}
    ]
    assert "private_raw_signal" not in str(result.decision.feature_data)


def test_provider_contract_preserves_signal_identity_without_fabricating_confidence():
    output = LinguisticSignalProvider().extract(
        create_context("org-1", "doc-1", "version-1"), _segments()
    )

    assert output.signal == "linguistic"
    assert output.score is None
    assert output.confidence is None
    assert output.model_version == output.provider_version
    assert output.evidence
    assert all(item.provider_id == output.provider_id for item in output.evidence)
    assert all(item.model_version == output.model_version for item in output.evidence)


class ValidatedClassifier:
    model_id = "validated-model"
    model_version = "v1"

    def predict(self, context, segments, features):
        return ModelPrediction(
            self.model_id,
            self.model_version,
            {
                Classification.HUMAN: 0.05,
                Classification.AI_GENERATED: 0.70,
                Classification.AI_ASSISTED: 0.05,
                Classification.MIXED: 0.05,
                Classification.UNCERTAIN: 0.10,
                Classification.INSUFFICIENT_EVIDENCE: 0.05,
            },
        )


def test_calibrated_candidate_model_serves_confidence_and_registry_status():
    layer = CalibrationLayer()
    layer.register(
        CalibrationSpec(
            "validated-model",
            "v1",
            "cal-v1",
            "frozen-v1",
            "ensemble_entropy",
            held_out=True,
        ),
        lambda probabilities: probabilities,
    )
    result = EnsembleOrchestrator(
        classifiers=[ValidatedClassifier()], calibration=layer
    ).infer(create_context("org-1", "doc-1", "version-1"), _segments())

    assert result.decision.abstained is False
    assert result.decision.classification is Classification.AI_GENERATED
    assert result.decision.confidence == 0.7
    assert result.decision.confidence_reliability == "VALIDATED_HELD_OUT"
    assert result.decision.inference_metadata["registry_status"] == "CANDIDATE"
    assert result.decision.feature_data["linguistic-signals"]["evidence"]


def test_provider_failure_is_withheld_and_abstains():
    class ExplodingProvider:
        provider_id = "broken-provider"
        provider_version = "broken-v1"
        family = "semantic"

        def extract(self, context, segments):
            raise RuntimeError("model unavailable")

    result = EnsembleOrchestrator(providers=[ExplodingProvider()]).infer(
        create_context("org-1", "doc-1", "version-1"), _segments()
    )

    assert result.decision.abstained is True
    assert result.decision.classification is Classification.INSUFFICIENT_EVIDENCE
    assert result.decision.inference_metadata["provider_failures"] == [
        {"provider_id": "broken-provider", "error_type": "RuntimeError"}
    ]
    assert result.decision.evidence[0].status is SignalStatus.ABSTAINED
