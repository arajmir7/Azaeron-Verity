"""Reproducible calibration protocol; test/OOD labels never select parameters.

Input consists of provenance-labelled metadata and frozen model scores. This
module does not train a detector, create a dataset, or grant production approval.
"""

from dataclasses import asdict, replace
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Sequence

from app.modules.governance.validation import (
    AI_INVOLVEMENT_LABELS,
    DatasetRow,
    PredictionRow,
    evaluate_predictions,
    validate_dataset_rows,
    validate_provenance,
)

SPLITS = frozenset({"train", "validation", "calibration", "test", "ood"})
FPR_TARGETS = (0.001, 0.01, 0.05)
REQUIRED_CLASSES = frozenset(
    {"HUMAN", "AI_GENERATED", "AI_ASSISTED", "HUMAN_EDITED_AI", "MIXED"}
)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def logit(score: float) -> float:
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Scores must be finite probabilities")
    clipped = min(1 - 1e-8, max(1e-8, score))
    return math.log(clipped / (1 - clipped))


def calibrated(score: float, a: float, b: float) -> float:
    z = max(-35, min(35, a * logit(score) + b))
    return 1 / (1 + math.exp(-z))


def fit_calibrator(rows: Sequence[PredictionRow]) -> dict[str, Any]:
    if not rows or any(row.split != "calibration" for row in rows):
        raise ValueError("Fit exclusively on the calibration split")
    labels = [int(row.expected_label in AI_INVOLVEMENT_LABELS) for row in rows]
    if set(labels) != {0, 1} or any(row.expected_label == "OOD" for row in rows):
        raise ValueError("Calibration requires known positive and negative examples")
    a, b = 1.0, 0.0
    inputs = [logit(row.score) for row in rows]
    # Deterministic monotonic logistic calibration. Hyperparameters are fixed,
    # never selected using final-test labels or metrics.
    for _ in range(500):
        residuals = [
            calibrated(row.score, a, b) - label for row, label in zip(rows, labels)
        ]
        a = max(
            0.0,
            a
            - 0.05 * sum(error * x for error, x in zip(residuals, inputs)) / len(rows),
        )
        b -= 0.05 * sum(residuals) / len(rows)
    return {
        "method": "monotonic-logistic-v1",
        "a": a,
        "b": b,
        "fit_split": "calibration",
        "fit_predictions_sha256": canonical_hash([asdict(r) for r in rows]),
    }


def freeze_thresholds(rows: Sequence[PredictionRow]) -> dict[str, Any]:
    if not rows or any(row.split != "validation" for row in rows):
        raise ValueError("Thresholds must be selected exclusively on validation")
    negatives = sorted(
        (r.score for r in rows if r.expected_label == "HUMAN"), reverse=True
    )
    if not negatives:
        raise ValueError("Validation requires human negative examples")
    thresholds = {}
    for rate in FPR_TARGETS:
        allowed = math.floor(rate * len(negatives))
        value = math.nextafter(negatives[allowed], math.inf)
        thresholds[str(rate)] = value if value <= 1 else None
    return {
        "selection_split": "validation",
        "validation_predictions_sha256": canonical_hash([asdict(r) for r in rows]),
        "negative_count": len(negatives),
        "thresholds": thresholds,
    }


def fixed_operating_metrics(
    rows: Sequence[PredictionRow], artifact: dict[str, Any]
) -> dict[str, Any]:
    if artifact.get("selection_split") != "validation":
        raise ValueError("Frozen validation thresholds required")
    known = [r for r in rows if r.expected_label != "OOD"]
    negatives = [r for r in known if r.expected_label == "HUMAN"]
    positives = [r for r in known if r.expected_label in AI_INVOLVEMENT_LABELS]
    output = {}
    for target, threshold in artifact["thresholds"].items():

        def hit(row: PredictionRow) -> bool:
            return threshold is not None and row.score >= threshold

        output[target] = {
            "threshold": threshold,
            "tpr": (
                sum(hit(r) for r in positives) / len(positives) if positives else None
            ),
            "observed_fpr": (
                sum(hit(r) for r in negatives) / len(negatives) if negatives else None
            ),
            "negative_count": len(negatives),
            "positive_count": len(positives),
            "empirical_resolution_supported": len(negatives)
            >= math.ceil(1 / float(target)),
        }
    return output


def metrics(
    rows: Sequence[PredictionRow], thresholds: dict[str, Any]
) -> dict[str, Any]:
    report = evaluate_predictions(rows, held_out=all(r.split == "test" for r in rows))
    known = [r for r in rows if r.expected_label != "OOD"]
    report["metrics"]["brier_score"] = (
        sum(
            (r.score - int(r.expected_label in AI_INVOLVEMENT_LABELS)) ** 2
            for r in known
        )
        / len(known)
        if known
        else None
    )
    report["metrics"]["ece"] = report["calibration"]["expected_calibration_error"]
    report["metrics"]["confusion_matrix"] = {
        name: report["metrics"][name]
        for name in (
            "true_negative",
            "false_positive",
            "false_negative",
            "true_positive",
        )
    }
    report["fixed_fpr_operating_points"] = fixed_operating_metrics(rows, thresholds)
    report["coverage"] = sum(not r.abstained for r in rows) / len(rows)
    report["binary_target"] = (
        "any AI involvement; not proof of fully machine-written text"
    )
    return report


def evaluate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    provenance = bundle["provenance"]
    if any(
        not isinstance(provenance.get(key), str) or not provenance[key].strip()
        for key in ("source", "collection_method", "license", "curator", "created_at")
    ):
        raise ValueError("Dataset provenance/license metadata is incomplete")
    if not validate_provenance(provenance)["valid"]:
        raise ValueError("Dataset provenance/license metadata is incomplete")
    dataset = [DatasetRow(**row) for row in bundle["dataset"]]
    if any(
        row.label not in REQUIRED_CLASSES | {"OOD"}
        or (row.label == "OOD" and row.split != "ood")
        or not re.fullmatch(r"[a-f0-9]{64}", row.text_sha256)
        for row in dataset
    ):
        raise ValueError("Known-origin labels and SHA-256 text identities are required")
    validation = validate_dataset_rows(dataset)
    if not validation["valid"]:
        raise ValueError("Dataset split leakage or provenance validation failed")
    if set(row.split for row in dataset) != SPLITS:
        raise ValueError(
            "Separate train, validation, calibration, test and ood splits are required"
        )
    keys = {row.example_key: row for row in dataset}
    raw = [PredictionRow(**row) for row in bundle["predictions"]]
    if len({row.example_key for row in raw}) != len(raw):
        raise ValueError("Duplicate prediction identities")
    expected = {row.example_key for row in dataset if row.split != "train"}
    if {row.example_key for row in raw} != expected:
        raise ValueError("Predictions must cover exactly the non-training examples")
    for row in raw:
        source = keys.get(row.example_key)
        if (
            source is None
            or row.split != source.split
            or row.expected_label != source.label
        ):
            raise ValueError("Prediction does not match the frozen dataset")
        if (
            isinstance(row.score, bool)
            or not math.isfinite(row.score)
            or not 0 <= row.score <= 1
        ):
            raise ValueError("Invalid model score")
    for name in (
        "model_revision",
        "pipeline_version",
        "runtime",
        "hardware",
        "dataset_version",
    ):
        if not bundle.get(name):
            raise ValueError("Missing reproducibility metadata: " + name)
    calibrator = fit_calibrator([r for r in raw if r.split == "calibration"])
    adjusted = [
        replace(row, score=calibrated(row.score, calibrator["a"], calibrator["b"]))
        for row in raw
    ]
    thresholds = freeze_thresholds([r for r in adjusted if r.split == "validation"])
    test = [r for r in adjusted if r.split == "test"]
    ood = [r for r in adjusted if r.split == "ood"]
    report = metrics(test, thresholds)
    blockers = [
        "Production promotion requires independent approval and reviewed error/fairness/robustness evidence."
    ]
    classes = {r.expected_label for r in test}
    if not REQUIRED_CLASSES.issubset(classes):
        blockers.append(
            "Required human, generated, assisted, edited and mixed test classes are incomplete."
        )
    if any(
        not row["empirical_resolution_supported"]
        for row in report["fixed_fpr_operating_points"].values()
    ):
        blockers.append(
            "Insufficient human examples to resolve every requested FPR target."
        )
    if bundle.get("purpose") != "LICENSED_EVALUATION":
        blockers.append("Input is not a licensed production evaluation corpus.")
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "status": "EXPERIMENTAL",
        "production_approved": False,
        "input_sha256": canonical_hash(bundle),
        "dataset_manifest_sha256": canonical_hash(bundle["dataset"]),
        "metadata": {
            name: bundle[name]
            for name in (
                "model_revision",
                "pipeline_version",
                "runtime",
                "hardware",
                "dataset_version",
            )
        },
        "provenance": provenance,
        "calibrator": calibrator,
        "operating_thresholds": thresholds,
        "test": report,
        "ood": metrics(ood, thresholds),
        "release_blockers": blockers,
        "limitations": [
            "Fixed-FPR thresholds are selected on validation; final-test observed FPR may exceed the target.",
            "Empirical resolution is not a statistical confidence bound.",
            "Synthetic fixtures establish implementation correctness only, never detector quality.",
        ],
    }
