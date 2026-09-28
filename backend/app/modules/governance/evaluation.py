"""Small, dependency-light evaluation and leakage checks.

The functions operate on metadata rows rather than raw user documents so a
dataset can be frozen and reproduced without copying sensitive text into the
application database.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from app.modules.governance.validation import (
    AI_INVOLVEMENT_LABELS,
    DATASET_LABELS,
    DatasetRow,
    PredictionRow,
    ReproducibilityMetadata,
    build_dataset_manifest,
    build_model_evaluation_record,
    evaluate_predictions,
    validate_dataset_rows,
    validate_provenance,
    validation_gate,
)


@dataclass(frozen=True)
class EvaluationRow:
    example_key: str
    split: str
    label: str
    text_sha256: str
    author_key_hash: str | None = None
    domain: str | None = None


def validate_no_leakage(rows: Iterable[EvaluationRow]) -> dict[str, Any]:
    """Reject text or author overlap between evaluation splits.

    Author overlap is disallowed because stylometric and source models can
    otherwise memorize a writer. Duplicate text is disallowed for every
    split, including within a split.
    """
    materialized = list(rows)
    errors: list[str] = []
    seen_text: dict[str, str] = {}
    seen_author: dict[str, str] = {}
    for row in materialized:
        prior_split = seen_text.get(row.text_sha256)
        if prior_split is not None:
            errors.append(
                f"text hash {row.text_sha256} appears in {prior_split} and {row.split}"
            )
        else:
            seen_text[row.text_sha256] = row.split
        if row.author_key_hash:
            prior_author = seen_author.get(row.author_key_hash)
            if prior_author is not None and prior_author != row.split:
                errors.append(
                    f"author hash {row.author_key_hash} appears in {prior_author} and {row.split}"
                )
            else:
                seen_author[row.author_key_hash] = row.split
    return {
        "valid": not errors,
        "row_count": len(materialized),
        "split_counts": dict(Counter(row.split for row in materialized)),
        "errors": errors,
    }


def binary_metrics(
    labels: Sequence[int], scores: Sequence[float], threshold: float = 0.5
) -> dict[str, float | None]:
    """Compute threshold metrics without making a calibration claim."""
    if len(labels) != len(scores) or not labels:
        raise ValueError("labels and scores must have the same non-zero length")
    predictions = [score >= threshold for score in scores]
    positives = sum(labels)
    negatives = len(labels) - positives
    tp = sum(pred and label == 1 for pred, label in zip(predictions, labels))
    fp = sum(pred and label == 0 for pred, label in zip(predictions, labels))
    fn = sum((not pred) and label == 1 for pred, label in zip(predictions, labels))
    tn = sum((not pred) and label == 0 for pred, label in zip(predictions, labels))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        (2 * precision * recall / (precision + recall))
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": fp / negatives if negatives else None,
        "false_negative_rate": fn / positives if positives else None,
        "accuracy": (tp + tn) / len(labels),
    }


def production_gate(report: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """Return whether an evaluation report has enough evidence to promote."""
    # Structured reports use the strict gate. The compact branch preserves
    # compatibility with early governance checks that only exercised the
    # original five required evidence flags.
    if any(
        key in report
        for key in (
            "dataset_status",
            "leakage_free",
            "confidence_reliability",
            "reproducibility_complete",
        )
    ):
        return validation_gate(report)
    required = {
        "held_out_test": "held-out test results",
        "calibration": "calibration analysis",
        "error_analysis": "error analysis",
        "reproducible": "reproducibility metadata",
        "limitations": "documented limitations",
    }
    missing = [label for key, label in required.items() if not report.get(key)]
    return not missing, missing
