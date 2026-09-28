"""Calibration registry for detector predictions.

Registration is intentionally strict: a model cannot participate in an
ensemble without a held-out evaluation record and a declared calibrator.
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Callable, Mapping, Optional

from app.modules.detection.intelligence.contract import (
    CalibratedPrediction,
    Classification,
    ModelPrediction,
)
from app.modules.governance.validation import validation_gate


@dataclass(frozen=True)
class CalibrationSpec:
    model_id: str
    model_version: str
    calibrator_version: str
    evaluation_dataset_version: str
    uncertainty_method: str
    held_out: bool
    lifecycle_status: str = "CANDIDATE"
    validation_report: Mapping[str, Any] = field(default_factory=dict)


CalibratorFunction = Callable[
    [Mapping[Classification, float]], Mapping[Classification, float]
]


class CalibrationLayer:
    def __init__(self) -> None:
        self._registry: dict[
            tuple[str, str], tuple[CalibrationSpec, CalibratorFunction]
        ] = {}

    def register(self, spec: CalibrationSpec, calibrator: CalibratorFunction) -> None:
        if not spec.held_out:
            raise ValueError(
                "A detector calibrator requires a held-out evaluation dataset"
            )
        if not spec.evaluation_dataset_version:
            raise ValueError(
                "A detector calibrator requires an evaluation dataset version"
            )
        if not spec.calibrator_version:
            raise ValueError("A detector calibrator requires a version")
        if spec.lifecycle_status not in {"CANDIDATE", "PRODUCTION"}:
            raise ValueError(
                "Only CANDIDATE or PRODUCTION models may be loaded for inference"
            )
        if spec.lifecycle_status == "PRODUCTION":
            report = dict(
                spec.validation_report.get("evaluation_report")
                or spec.validation_report
            )
            promotion_allowed, blockers = validation_gate(report)
            if (
                spec.validation_report.get("promotion_allowed") is not True
                or not promotion_allowed
            ):
                blocker_text = (
                    "; ".join(blockers) or "held-out validation gate did not pass"
                )
                raise ValueError(
                    "A PRODUCTION calibrator requires a passing held-out validation gate: "
                    f"{blocker_text}"
                )
        self._registry[(spec.model_id, spec.model_version)] = (spec, calibrator)

    def calibrate(self, prediction: ModelPrediction) -> Optional[CalibratedPrediction]:
        registered = self._registry.get((prediction.model_id, prediction.model_version))
        if not registered:
            return None
        spec, calibrator = registered
        expected = set(Classification)
        if set(prediction.probabilities) != expected:
            raise ValueError(
                "Model prediction must provide all six classification states"
            )
        if any(
            not isfinite(float(value)) or value < 0 or value > 1
            for value in prediction.probabilities.values()
        ):
            raise ValueError(
                "Model prediction probabilities must be finite values in [0, 1]"
            )
        input_total = sum(float(value) for value in prediction.probabilities.values())
        if not 0.999 <= input_total <= 1.001:
            raise ValueError("Model prediction probabilities must sum to one")
        calibrated = dict(calibrator(prediction.probabilities))
        if set(calibrated) != expected:
            raise ValueError("Calibrator must return all six classification states")
        if any(value < 0 or value > 1 for value in calibrated.values()):
            raise ValueError("Calibrator returned a probability outside [0, 1]")
        total = sum(calibrated.values())
        if not 0.999 <= total <= 1.001:
            raise ValueError("Calibrator probabilities must sum to one")
        normalized = {key: value / total for key, value in calibrated.items()}
        uncertainty = 1 - max(normalized.values())
        return CalibratedPrediction(
            prediction=ModelPrediction(
                prediction.model_id,
                prediction.model_version,
                normalized,
                prediction.raw_evidence,
            ),
            calibrator_version=spec.calibrator_version,
            uncertainty=uncertainty,
            reliability="VALIDATED_HELD_OUT",
            lifecycle_status=spec.lifecycle_status,
        )

    def describe(self) -> list[dict[str, str]]:
        return [
            {
                "model_id": spec.model_id,
                "model_version": spec.model_version,
                "calibrator_version": spec.calibrator_version,
                "evaluation_dataset_version": spec.evaluation_dataset_version,
                "uncertainty_method": spec.uncertainty_method,
                "lifecycle_status": spec.lifecycle_status,
            }
            for spec, _ in self._registry.values()
        ]
