from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from app.modules.detection.intelligence.evaluation import (
    evaluate_bundle,
    fit_calibrator,
    freeze_thresholds,
    metrics,
)
from app.modules.governance.validation import PredictionRow


def fixture_bundle():
    """Synthetic arithmetic fixture only; not a calibration dataset or benchmark."""
    dataset, predictions = [], []
    for split in ("train", "validation", "calibration", "test", "ood"):
        for index, (label, score) in enumerate(
            (
                ("HUMAN", 0.1),
                ("HUMAN", 0.2),
                ("AI_GENERATED", 0.8),
                ("AI_GENERATED", 0.9),
            )
        ):
            key = f"{split}-{index}"
            digest = hashlib.sha256(key.encode()).hexdigest()
            dataset.append(
                dict(
                    example_key=key,
                    split=split,
                    label=label,
                    text_sha256=digest,
                    author_key_hash=digest,
                    document_key_hash=digest,
                )
            )
            if split != "train":
                predictions.append(
                    dict(
                        example_key=key, split=split, expected_label=label, score=score
                    )
                )
    return dict(
        dataset=dataset,
        predictions=predictions,
        purpose="TEST_ONLY",
        provenance=dict(
            source="synthetic unit fixture",
            collection_method="arithmetic fixture",
            license="test-only",
            curator="unit test",
            created_at="2026-09-20",
        ),
        model_revision="a" * 40,
        pipeline_version="test-only",
        runtime="test-only",
        hardware="test-only",
        dataset_version="fixture-v1",
    )


def test_metric_arithmetic_and_tied_scores():
    rows = [
        PredictionRow(str(i), label, score)
        for i, (label, score) in enumerate(
            (
                ("HUMAN", 0.1),
                ("HUMAN", 0.2),
                ("AI_GENERATED", 0.8),
                ("AI_GENERATED", 0.9),
            )
        )
    ]
    thresholds = freeze_thresholds([replace(row, split="validation") for row in rows])
    result = metrics(rows, thresholds)
    assert result["metrics"]["auroc"] == 1
    assert result["metrics"]["auprc"] == 1
    assert result["metrics"]["brier_score"] == pytest.approx(0.025)
    assert result["metrics"]["ece"] == pytest.approx(0.15)
    assert result["metrics"]["f1"] == 1
    assert result["fixed_fpr_operating_points"]["0.001"]["tpr"] == 1
    assert not result["fixed_fpr_operating_points"]["0.001"][
        "empirical_resolution_supported"
    ]
    tied = [replace(row, score=0.5) for row in rows]
    assert metrics(tied, thresholds)["metrics"]["auroc"] == 0.5


def test_final_labels_cannot_fit_or_select_thresholds():
    rows = [PredictionRow("h", "HUMAN", 0.1), PredictionRow("m", "AI_GENERATED", 0.9)]
    with pytest.raises(ValueError, match="calibration split"):
        fit_calibrator(rows)
    with pytest.raises(ValueError, match="validation"):
        freeze_thresholds(rows)
    original = fixture_bundle()
    changed = deepcopy(original)
    for row in changed["predictions"]:
        if row["split"] in {"test", "ood"}:
            row["score"] = 1 - row["score"]
    first, second = evaluate_bundle(original), evaluate_bundle(changed)
    assert first["calibrator"] == second["calibrator"]
    assert first["operating_thresholds"] == second["operating_thresholds"]
    assert first["test"]["metrics"]["auroc"] != second["test"]["metrics"]["auroc"]
    assert first["production_approved"] is False
    assert first["status"] == "EXPERIMENTAL"


def test_leakage_missing_provenance_and_invalid_scores_rejected():
    bundle = fixture_bundle()
    bundle["dataset"][-1]["author_key_hash"] = bundle["dataset"][0]["author_key_hash"]
    with pytest.raises(ValueError, match="leakage"):
        evaluate_bundle(bundle)
    bundle = fixture_bundle()
    bundle["provenance"]["license"] = ""
    with pytest.raises(ValueError, match="provenance"):
        evaluate_bundle(bundle)
    bundle = fixture_bundle()
    bundle["predictions"][0]["score"] = float("nan")
    with pytest.raises(ValueError, match="score"):
        evaluate_bundle(bundle)
    bundle = fixture_bundle()
    bundle["predictions"][0]["split"] = "test"
    with pytest.raises(ValueError, match="frozen dataset"):
        evaluate_bundle(bundle)


def test_experimental_api_never_exposes_authoritative_probability():
    from datetime import datetime
    from app.modules.detection.schemas import DetectionResultResponse

    data = dict(
        id="fixture",
        document_id="fixture",
        model_version="fixture",
        pipeline_version="fixture",
        feature_version="fixture",
        inference_id="fixture",
        created_at=datetime.now(),
        release_status="EXPERIMENTAL",
        abstained=False,
        overall_verdict="ai_generated",
        confidence=0.99,
        human_probability=0.01,
        ai_probability=0.99,
        mixed_probability=0,
        uncertain_probability=0,
        confidence_reliability="VALIDATED_HELD_OUT",
    )
    result = DetectionResultResponse(**data)
    assert result.authorship_assessment == "INDETERMINATE"
    assert result.confidence is None and result.ai_probability is None
    result = DetectionResultResponse(**{**data, "release_status": "PRODUCTION"})
    assert result.authorship_assessment == "LIKELY_MACHINE"
    assert result.ai_probability == 0.99
