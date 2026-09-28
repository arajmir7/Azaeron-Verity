from app.modules.governance.evaluation import (
    EvaluationRow,
    binary_metrics,
    production_gate,
    validate_no_leakage,
)


def test_dataset_leakage_check_rejects_text_and_author_overlap():
    report = validate_no_leakage(
        [
            EvaluationRow("a", "train", "human", "hash-a", "author-1"),
            EvaluationRow("b", "test", "ai", "hash-a", "author-1"),
        ]
    )
    assert report["valid"] is False
    assert len(report["errors"]) == 2


def test_binary_metrics_are_reproducible_and_explicit():
    metrics = binary_metrics([0, 0, 1, 1], [0.1, 0.8, 0.7, 0.2])
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["false_positive_rate"] == 0.5
    assert metrics["false_negative_rate"] == 0.5


def test_production_gate_requires_evidence_beyond_a_single_score():
    allowed, missing = production_gate({"held_out_test": True, "limitations": True})
    assert allowed is False
    assert missing == [
        "calibration analysis",
        "error analysis",
        "reproducibility metadata",
    ]
