"""Dataset and model validation contracts for the production promotion gate.

This module is deliberately dependency-light. It evaluates metadata and
probability outputs without copying raw document text into the registry.
Every report is explicit about unavailable measurements; missing evidence is
never converted into a passing score.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence, TypeGuard

DATASET_LABELS = frozenset(
    {
        "HUMAN",
        "AI_GENERATED",
        "AI_ASSISTED",
        "MIXED",
        "HUMAN_EDITED_AI",
        "TRANSLATED",
        "PARAPHRASED",
        "OOD",
    }
)
AI_INVOLVEMENT_LABELS = frozenset(
    {
        "AI_GENERATED",
        "AI_ASSISTED",
        "MIXED",
        "HUMAN_EDITED_AI",
    }
)
REPRODUCIBILITY_FIELDS = (
    "random_seed",
    "code_version",
    "feature_version",
    "pipeline_version",
    "dataset_manifest_sha256",
    "inference_config_hash",
)
STRATIFICATION_DIMENSIONS = (
    "language",
    "domain",
    "genre",
    "document_length",
    "writing_proficiency",
    "generation_source",
    "editing_intensity",
)


@dataclass(frozen=True)
class DatasetRow:
    example_key: str
    split: str
    label: str
    text_sha256: str
    author_key_hash: str | None = None
    document_key_hash: str | None = None
    source_document_hash: str | None = None
    language: str | None = None
    domain: str | None = None
    genre: str | None = None
    document_length: int | None = None
    writing_proficiency: str | None = None
    generation_source: str | None = None
    editing_intensity: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionRow:
    example_key: str
    expected_label: str
    score: float
    predicted_label: str | None = None
    confidence: float | None = None
    abstained: bool = False
    split: str = "test"
    language: str | None = None
    domain: str | None = None
    genre: str | None = None
    document_length: int | None = None
    writing_proficiency: str | None = None
    generation_source: str | None = None
    editing_intensity: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReproducibilityMetadata:
    random_seed: int
    code_version: str
    feature_version: str
    pipeline_version: str
    dataset_manifest_sha256: str
    inference_config_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _nonempty(value: str | None) -> TypeGuard[str]:
    return bool(value and value.strip())


def validate_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    required = ("source", "collection_method", "license", "curator", "created_at")
    missing = [
        field for field in required if not _nonempty(str(provenance.get(field, "")))
    ]
    return {"valid": not missing, "missing": missing}


def validate_dataset_rows(
    rows: Iterable[DatasetRow],
    *,
    required_labels: Iterable[str] | None = None,
    require_group_keys: bool = True,
) -> dict[str, Any]:
    """Validate split integrity before a dataset can be frozen.

    Text hashes catch exact duplicates. Document/source hashes catch derived
    samples from one source document, while author hashes prevent writer
    leakage across splits. All three checks are performed independently.
    """
    materialized = list(rows)
    errors: list[str] = []
    seen_keys: set[str] = set()
    seen_text: dict[str, tuple[str, str]] = {}
    seen_author: dict[str, tuple[str, str]] = {}
    seen_document: dict[str, tuple[str, str]] = {}
    seen_source: dict[str, tuple[str, str]] = {}

    for row in materialized:
        if not _nonempty(row.example_key):
            errors.append("example_key is required")
        if row.example_key in seen_keys:
            errors.append(f"duplicate example key: {row.example_key}")
        seen_keys.add(row.example_key)
        if row.label not in DATASET_LABELS:
            errors.append(f"unsupported label {row.label!r} for {row.example_key}")
        if not _nonempty(row.split):
            errors.append(f"split is required for {row.example_key}")
        if not _nonempty(row.text_sha256):
            errors.append(f"text hash is required for {row.example_key}")
        elif row.text_sha256 in seen_text:
            prior_split, prior_key = seen_text[row.text_sha256]
            errors.append(
                f"duplicate text hash {row.text_sha256}: {prior_key}/{prior_split} and {row.example_key}/{row.split}"
            )
        else:
            seen_text[row.text_sha256] = (row.split, row.example_key)

        if require_group_keys and not _nonempty(row.author_key_hash):
            errors.append(
                f"author key hash is required to prevent author leakage: {row.example_key}"
            )
        if require_group_keys and not _nonempty(row.document_key_hash):
            errors.append(
                f"document key hash is required to prevent document leakage: {row.example_key}"
            )

        for name, value, seen in (
            ("author", row.author_key_hash, seen_author),
            ("document", row.document_key_hash, seen_document),
            ("source document", row.source_document_hash, seen_source),
        ):
            if not _nonempty(value):
                continue
            if value in seen:
                prior_split, prior_key = seen[value]
                if prior_split != row.split:
                    errors.append(
                        f"{name} leakage {value}: {prior_key}/{prior_split} and {row.example_key}/{row.split}"
                    )
                elif name != "author":
                    errors.append(
                        f"duplicate {name} group {value} within split {row.split}"
                    )
            else:
                seen[value] = (row.split, row.example_key)

    required = set(required_labels or ())
    present = {row.label for row in materialized}
    missing_labels = sorted(required - present)
    errors.extend(f"required label missing: {label}" for label in missing_labels)
    return {
        "valid": not errors,
        "row_count": len(materialized),
        "split_counts": dict(Counter(row.split for row in materialized)),
        "label_counts": dict(Counter(row.label for row in materialized)),
        "author_keys_complete": all(
            _nonempty(row.author_key_hash) for row in materialized
        ),
        "document_keys_complete": all(
            _nonempty(row.document_key_hash) for row in materialized
        ),
        "errors": errors,
        "missing_labels": missing_labels,
    }


def build_dataset_manifest(
    rows: Sequence[DatasetRow], provenance: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    provenance_report = validate_provenance(provenance)
    if not provenance_report["valid"]:
        raise ValueError(
            f"Dataset provenance is incomplete: {provenance_report['missing']}"
        )
    payload = {
        "provenance": dict(provenance),
        "rows": [
            {
                "example_key": row.example_key,
                "split": row.split,
                "label": row.label,
                "text_sha256": row.text_sha256,
                "author_key_hash": row.author_key_hash,
                "document_key_hash": row.document_key_hash,
                "source_document_hash": row.source_document_hash,
                "language": row.language,
                "domain": row.domain,
                "genre": row.genre,
                "document_length": row.document_length,
                "writing_proficiency": row.writing_proficiency,
                "generation_source": row.generation_source,
                "editing_intensity": row.editing_intensity,
                "metadata": dict(row.metadata),
            }
            for row in sorted(rows, key=lambda item: item.example_key)
        ],
    }
    manifest = sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return manifest, payload


def _length_bucket(length: int | None) -> str:
    if length is None:
        return "unknown"
    if length < 200:
        return "<200"
    if length < 500:
        return "200-499"
    if length < 1000:
        return "500-999"
    return "1000+"


def _dimension_value(row: PredictionRow, dimension: str) -> str:
    if dimension == "document_length":
        return _length_bucket(row.document_length)
    value = getattr(row, dimension, None)
    return str(value) if value not in (None, "") else "unknown"


def _binary_label(label: str, positive_labels: set[str]) -> int:
    return int(label in positive_labels)


def _threshold_metrics(
    labels: Sequence[int], scores: Sequence[float], threshold: float
) -> dict[str, float | int | None]:
    predictions = [score >= threshold for score in scores]
    positives = sum(labels)
    negatives = len(labels) - positives
    tp = sum(
        prediction and label == 1 for prediction, label in zip(predictions, labels)
    )
    fp = sum(
        prediction and label == 0 for prediction, label in zip(predictions, labels)
    )
    fn = sum(
        (not prediction) and label == 1
        for prediction, label in zip(predictions, labels)
    )
    tn = sum(
        (not prediction) and label == 0
        for prediction, label in zip(predictions, labels)
    )
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        (2 * precision * recall / (precision + recall))
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "sample_count": len(labels),
        "positive_count": positives,
        "negative_count": negatives,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fpr": fp / negatives if negatives else None,
        "fnr": fn / positives if positives else None,
        "false_positive_rate": fp / negatives if negatives else None,
        "false_negative_rate": fn / positives if positives else None,
        "accuracy": (tp + tn) / len(labels) if labels else None,
    }


def _auc_roc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    tp = fp = 0
    points = [(0.0, 0.0)]
    index = 0
    while index < len(ordered):
        score = ordered[index][0]
        while index < len(ordered) and ordered[index][0] == score:
            if ordered[index][1]:
                tp += 1
            else:
                fp += 1
            index += 1
        points.append((fp / negatives, tp / positives))
    return round(
        sum(
            (x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in zip(points, points[1:])
        ),
        8,
    )


def _auc_pr(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    positives = sum(labels)
    if not positives or positives == len(labels):
        return None
    ordered = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    tp = fp = 0
    previous_recall = 0.0
    area = 0.0
    index = 0
    while index < len(ordered):
        score = ordered[index][0]
        while index < len(ordered) and ordered[index][0] == score:
            if ordered[index][1]:
                tp += 1
            else:
                fp += 1
            index += 1
        recall = tp / positives
        precision = tp / (tp + fp) if tp + fp else 0.0
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return round(area, 8)


def _calibration(
    rows: Sequence[PredictionRow], labels: Sequence[int], bins: int = 10
) -> dict[str, Any]:
    if not rows:
        return {"status": "UNAVAILABLE", "expected_calibration_error": None, "bins": []}
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for row, label in zip(rows, labels):
        index = min(bins - 1, max(0, int(row.score * bins)))
        buckets[index].append((row.score, label))
    report = []
    weighted_error = 0.0
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        mean_score = sum(score for score, _ in bucket) / len(bucket)
        accuracy = sum(label for _, label in bucket) / len(bucket)
        gap = abs(mean_score - accuracy)
        weighted_error += gap * len(bucket) / len(rows)
        report.append(
            {
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "count": len(bucket),
                "mean_score": mean_score,
                "accuracy": accuracy,
                "gap": gap,
            }
        )
    return {
        "status": "AVAILABLE",
        "expected_calibration_error": round(weighted_error, 8),
        "bins": report,
    }


def _confidence_reliability(
    rows: Sequence[PredictionRow], positive_labels: set[str]
) -> dict[str, Any]:
    if any(row.confidence is None for row in rows):
        return {
            "status": "UNAVAILABLE",
            "reason": "Every prediction requires a confidence value",
            "bins": [],
        }
    buckets: list[list[tuple[PredictionRow, float]]] = [[] for _ in range(10)]
    for row in rows:
        if row.confidence is None:
            raise ValueError("Prediction confidence is required")
        index = min(9, max(0, int(row.confidence * 10)))
        buckets[index].append((row, row.confidence))
    report = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        correct = []
        for row, _ in bucket:
            predicted = (
                row.predicted_label in positive_labels
                if row.predicted_label is not None
                else row.score >= 0.5
            )
            correct.append(
                int(
                    predicted
                    == (_binary_label(row.expected_label, positive_labels) == 1)
                )
            )
        mean_confidence = sum(confidence for _, confidence in bucket) / len(bucket)
        accuracy = sum(correct) / len(correct)
        report.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": len(bucket),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "gap": abs(mean_confidence - accuracy),
            }
        )
    return {
        "status": "AVAILABLE",
        "bins": report,
        "coverage": sum(not row.abstained for row in rows) / len(rows),
    }


def _error_item(row: PredictionRow, positive_labels: set[str]) -> dict[str, Any]:
    predicted_positive = (
        row.predicted_label in positive_labels
        if row.predicted_label is not None
        else row.score >= 0.5
    )
    return {
        "example_key": row.example_key,
        "expected_label": row.expected_label,
        "predicted_label": row.predicted_label,
        "score": row.score,
        "confidence": row.confidence,
        "abstained": row.abstained,
        "predicted_positive": predicted_positive,
        "dimensions": {
            dimension: _dimension_value(row, dimension)
            for dimension in STRATIFICATION_DIMENSIONS
        },
    }


def _distribution_shift(rows: Sequence[PredictionRow]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for row in rows:
        for dimension in STRATIFICATION_DIMENSIONS:
            grouped[dimension][row.split][_dimension_value(row, dimension)] += 1
    comparisons: dict[str, Any] = {}
    for dimension, splits in grouped.items():
        train = splits.get("train", Counter())
        test = splits.get("test", Counter())
        if not train or not test:
            continue
        train_total = sum(train.values())
        test_total = sum(test.values())
        values = set(train) | set(test)
        comparisons[dimension] = {
            value: {
                "train_rate": train[value] / train_total,
                "test_rate": test[value] / test_total,
                "absolute_rate_delta": abs(
                    train[value] / train_total - test[value] / test_total
                ),
            }
            for value in sorted(values)
        }
    return {"available": bool(comparisons), "comparisons": comparisons}


def evaluate_predictions(
    rows: Sequence[PredictionRow],
    *,
    threshold: float = 0.5,
    positive_labels: Iterable[str] = AI_INVOLVEMENT_LABELS,
    held_out: bool = False,
    limitations: Sequence[str] | None = None,
    reproducibility: Mapping[str, Any] | None = None,
    reference_rows: Sequence[PredictionRow] | None = None,
    _include_breakdowns: bool = True,
) -> dict[str, Any]:
    """Evaluate a score-producing model and return an auditable report."""
    if not rows:
        raise ValueError("At least one prediction is required")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between zero and one")
    positives = set(positive_labels)
    if not positives:
        raise ValueError("At least one positive label is required")
    if any(not isfinite(row.score) or not 0 <= row.score <= 1 for row in rows):
        raise ValueError("Prediction scores must be finite probabilities in [0, 1]")
    if any(
        row.confidence is not None
        and (not isfinite(row.confidence) or not 0 <= row.confidence <= 1)
        for row in rows
    ):
        raise ValueError("Confidence values must be finite numbers in [0, 1]")

    scored_rows = [row for row in rows if row.expected_label != "OOD"]
    labels = [_binary_label(row.expected_label, positives) for row in scored_rows]
    scores = [row.score for row in scored_rows]
    metrics = _threshold_metrics(labels, scores, threshold)
    metrics.update(
        {
            "auroc": _auc_roc(labels, scores),
            "auprc": _auc_pr(labels, scores),
            "threshold": threshold,
        }
    )
    calibration = _calibration(scored_rows, labels)
    reliability = _confidence_reliability(scored_rows, positives)

    false_positives = []
    false_negatives = []
    confidence_failures = []
    for row, label in zip(scored_rows, labels):
        predicted = (
            row.predicted_label in positives
            if row.predicted_label is not None
            else row.score >= threshold
        )
        if predicted and not label:
            false_positives.append(_error_item(row, positives))
        if not predicted and label:
            false_negatives.append(_error_item(row, positives))
        if (
            row.confidence is not None
            and row.confidence >= 0.8
            and predicted != bool(label)
        ):
            confidence_failures.append(_error_item(row, positives))

    ood_rows = [row for row in rows if row.expected_label == "OOD"]
    ood_failures = [
        _error_item(row, positives)
        for row in ood_rows
        if not row.abstained or row.score >= threshold
    ]
    report: dict[str, Any] = {
        "held_out_test": held_out and all(row.split == "test" for row in rows),
        "row_count": len(rows),
        "positive_labels": sorted(positives),
        "metrics": metrics,
        "calibration": calibration,
        "confidence_reliability": reliability,
        "breakdowns": {},
        "error_analysis": {
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "confidence_failures": confidence_failures,
            "distribution_shift": _distribution_shift([*rows, *(reference_rows or [])]),
            "ood_failures": ood_failures,
            "ood_evaluated": bool(ood_rows),
            "ood_row_count": len(ood_rows),
        },
        "limitations": list(
            limitations
            or [
                "Metrics describe this frozen evaluation sample and do not establish universal authorship accuracy.",
                "Performance may vary under domain, language, genre, translation, and editing shifts.",
            ]
        ),
        "reproducibility": dict(reproducibility or {}),
    }
    metrics["calibration_error"] = calibration["expected_calibration_error"]
    metrics["confidence_reliability"] = reliability["status"]
    if _include_breakdowns:
        report["breakdowns"] = {
            dimension: {
                value: evaluate_predictions(
                    [
                        row
                        for row in scored_rows
                        if _dimension_value(row, dimension) == value
                    ],
                    threshold=threshold,
                    positive_labels=positives,
                    held_out=False,
                    limitations=[],
                    _include_breakdowns=False,
                )["metrics"]
                for value in sorted(
                    {_dimension_value(row, dimension) for row in scored_rows}
                )
            }
            for dimension in STRATIFICATION_DIMENSIONS
        }
    report["reproducibility_complete"] = all(
        report["reproducibility"].get(field) not in (None, "")
        for field in REPRODUCIBILITY_FIELDS
    )
    report["dataset_status"] = "FROZEN" if report["held_out_test"] else "UNKNOWN"
    return report


def validation_gate(
    report: Mapping[str, Any], *, max_fpr: float = 0.05
) -> tuple[bool, list[str]]:
    """Strict promotion gate; all missing evidence is a blocking condition."""
    missing: list[str] = []
    metrics = report.get("metrics") or {}
    required_metrics = ("precision", "recall", "f1", "fpr", "fnr", "auroc", "auprc")
    if report.get("held_out_test") is not True:
        missing.append("held-out test evaluation")
    if report.get("dataset_status") != "FROZEN":
        missing.append("frozen immutable dataset version")
    if report.get("leakage_free") is not True:
        missing.append("leakage and contamination checks")
    for key in required_metrics:
        if metrics.get(key) is None:
            missing.append(key)
    if metrics.get("fpr") is not None and metrics["fpr"] > max_fpr:
        missing.append(f"controlled false-positive rate <= {max_fpr}")
    calibration = report.get("calibration") or {}
    if (
        calibration.get("status") != "AVAILABLE"
        or calibration.get("expected_calibration_error") is None
    ):
        missing.append("calibration analysis")
    reliability = report.get("confidence_reliability") or {}
    if reliability.get("status") != "AVAILABLE":
        missing.append("confidence reliability")
    errors = report.get("error_analysis") or {}
    for error_field in (
        "false_positives",
        "false_negatives",
        "confidence_failures",
        "distribution_shift",
    ):
        if error_field not in errors:
            missing.append(f"error analysis: {error_field}")
    if not errors.get("ood_evaluated"):
        missing.append("OOD evaluation")
    if not (errors.get("distribution_shift") or {}).get("available"):
        missing.append("distribution shift analysis")
    if report.get("reproducibility_complete") is not True:
        missing.append("reproducibility metadata")
    if not report.get("limitations"):
        missing.append("documented limitations")
    return not missing, missing


def build_model_evaluation_record(
    *,
    model_id: str,
    model_version: str,
    dataset_version: str,
    pipeline_version: str,
    report: Mapping[str, Any],
    requested_status: str = "EXPERIMENTAL",
    max_fpr: float = 0.05,
) -> dict[str, Any]:
    allowed, missing = validation_gate(report, max_fpr=max_fpr)
    if requested_status == "PRODUCTION" and not allowed:
        raise ValueError(f"Production promotion blocked: {missing}")
    if requested_status not in {"EXPERIMENTAL", "CANDIDATE", "PRODUCTION", "RETIRED"}:
        raise ValueError(f"Unsupported lifecycle status: {requested_status}")
    return {
        "model_id": model_id,
        "model_version": model_version,
        "dataset_version": dataset_version,
        "pipeline_version": pipeline_version,
        "metrics": dict(report.get("metrics") or {}),
        "limitations": list(report.get("limitations") or []),
        "status": requested_status,
        "promotion_allowed": allowed,
        "promotion_blockers": missing,
        "evaluation_report": dict(report),
    }
