"""Detector metrics with calibration-only operating thresholds and region abstention.

AI and MIXED are positive for binary ranking metrics. Multiclass metrics and
per-domain reports remain separate; no percentage proves authorship.
"""

import math

from .evaluate import classification_metrics
from .policy import PolicyError


def operating_thresholds(calibration_scores, calibration_labels):
    if len(calibration_scores) != len(calibration_labels) or not calibration_scores:
        raise PolicyError("invalid_calibration_predictions")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in calibration_scores) or any(
        y not in {0, 1, 2} for y in calibration_labels
    ):
        raise PolicyError("invalid_calibration_predictions")
    human = [
        p for p, y in zip(calibration_scores, calibration_labels, strict=True) if y == 0
    ]
    if not human or not any(y != 0 for y in calibration_labels):
        raise PolicyError("calibration_classes_missing")
    # Ties are never split. nextafter(1, +inf) permits honest zero coverage.
    candidates = sorted({0.0, *calibration_scores, math.nextafter(1.0, math.inf)})
    return {
        str(rate): min(
            t for t in candidates if sum(p >= t for p in human) / len(human) <= rate
        )
        for rate in [0.001, 0.01, 0.05]
    }


def binary_ranking(scores, labels):
    positive, negative = sum(y != 0 for y in labels), sum(y == 0 for y in labels)
    if not positive or not negative:
        return {"auroc": None, "auprc": None, "reason": "both_classes_required"}
    grouped: dict[float, list[int]] = {}
    for score, label in zip(scores, labels, strict=True):
        counts = grouped.setdefault(score, [0, 0])
        counts[int(label != 0)] += 1
    tp, fp, auc, ap = 0, 0, 0.0, 0.0
    for score in sorted(grouped, reverse=True):
        negatives, positives = grouped[score]
        old_tp, old_fp = tp, fp
        tp += positives
        fp += negatives
        auc += (fp - old_fp) / negative * (tp + old_tp) / positive / 2
        ap += (tp - old_tp) / positive * tp / (tp + fp)
    return {"auroc": auc, "auprc": ap}


def detector_report(
    probabilities, labels, regions, validated_regions, thresholds, confidence=0.9
):
    if (
        not 0 <= confidence <= 1
        or set(thresholds) != {"0.001", "0.01", "0.05"}
        or any(
            not math.isfinite(v) or not 0 <= v <= math.nextafter(1.0, math.inf)
            for v in thresholds.values()
        )
    ):
        raise PolicyError("invalid_frozen_thresholds")
    if (
        len(regions) != len(labels)
        or any(len(p) != 3 for p in probabilities)
        or any(y not in {0, 1, 2} for y in labels)
    ):
        raise PolicyError("invalid_detector_predictions")
    summary = classification_metrics(probabilities, labels, confidence)
    scores = [1 - p[0] for p in probabilities]
    summary.update(binary_ranking(scores, labels))
    predictions = [max(range(3), key=p.__getitem__) for p in probabilities]
    accepted = [
        max(p) >= confidence and region in validated_regions
        for p, region in zip(probabilities, regions, strict=True)
    ]
    summary["coverage"] = sum(accepted) / len(labels)
    summary["abstention_rate"] = 1 - summary["coverage"]
    summary["multiclass"] = {}
    for cls in range(3):
        tp = sum(
            y == cls and p == cls and a
            for y, p, a in zip(labels, predictions, accepted, strict=True)
        )
        fp = sum(
            y != cls and p == cls and a
            for y, p, a in zip(labels, predictions, accepted, strict=True)
        )
        fn = sum(
            y == cls and (p != cls or not a)
            for y, p, a in zip(labels, predictions, accepted, strict=True)
        )
        precision, recall = tp / max(1, tp + fp), tp / max(1, tp + fn)
        summary["multiclass"][str(cls)] = {
            "precision": precision,
            "recall": recall,
            "f1": (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0
            ),
        }
    summary["operating_points"] = {}
    human, positive = labels.count(0), sum(y != 0 for y in labels)
    for target, threshold in thresholds.items():
        false = sum(
            y == 0 and s >= threshold and a
            for y, s, a in zip(labels, scores, accepted, strict=True)
        )
        true = sum(
            y != 0 and s >= threshold and a
            for y, s, a in zip(labels, scores, accepted, strict=True)
        )
        summary["operating_points"][target] = {
            "threshold_from_calibration": threshold,
            "test_fpr": false / human if human else None,
            "test_tpr": true / positive if positive else None,
            "human_examples": human,
            "positive_examples": positive,
            "fpr_resolution": 1 / human if human else None,
            "insufficient_fpr_resolution": not human or 1 / human > float(target),
        }
    summary["subgroups"] = {
        region: {
            "examples": regions.count(region),
            "validated": region in validated_regions,
            "coverage": sum(
                a and r == region for a, r in zip(accepted, regions, strict=True)
            )
            / regions.count(region),
            **binary_ranking(
                [s for s, r in zip(scores, regions, strict=True) if r == region],
                [y for y, r in zip(labels, regions, strict=True) if r == region],
            ),
        }
        for region in sorted(set(regions))
    }
    return summary
