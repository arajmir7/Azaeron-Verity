from app.modules.governance.validation import (
    DatasetRow,
    PredictionRow,
    ReproducibilityMetadata,
    build_dataset_manifest,
    build_model_evaluation_record,
    evaluate_predictions,
    validate_dataset_rows,
    validation_gate,
)
import pytest
from app.modules.governance.service import GovernanceService


def _row(
    key: str,
    split: str,
    label: str,
    author: str,
    document: str,
    text: str | None = None,
) -> DatasetRow:
    return DatasetRow(
        example_key=key,
        split=split,
        label=label,
        text_sha256=text or f"text-{key}",
        author_key_hash=author,
        document_key_hash=document,
        source_document_hash=f"source-{document}",
        language="en",
        domain="science",
        genre="report",
        document_length=240,
        writing_proficiency="advanced",
        generation_source="none" if label == "HUMAN" else "validated-source",
        editing_intensity="none",
    )


def test_dataset_validation_rejects_text_author_and_document_leakage():
    report = validate_dataset_rows(
        [
            _row("train-1", "train", "HUMAN", "author-1", "doc-1"),
            _row("test-1", "test", "AI_GENERATED", "author-1", "doc-1"),
        ],
        required_labels={"HUMAN", "AI_GENERATED"},
    )
    assert report["valid"] is False
    assert any("author leakage" in error for error in report["errors"])
    assert any("document leakage" in error for error in report["errors"])

    duplicate = validate_dataset_rows(
        [
            _row("a", "train", "HUMAN", "author-a", "doc-a", text="same-text"),
            _row("b", "train", "HUMAN", "author-b", "doc-b", text="same-text"),
        ],
        required_labels={"HUMAN"},
    )
    assert duplicate["valid"] is False
    assert any("duplicate text hash" in error for error in duplicate["errors"])


def test_dataset_manifest_is_order_independent_and_requires_provenance():
    rows = [
        _row("b", "test", "AI_GENERATED", "author-b", "doc-b"),
        _row("a", "train", "HUMAN", "author-a", "doc-a"),
    ]
    provenance = {
        "source": "validated-corpus://example",
        "collection_method": "documented-manual-curation",
        "license": "internal-evaluation-license",
        "curator": "evaluation-team",
        "created_at": "2026-09-12T00:00:00Z",
    }
    first, _ = build_dataset_manifest(rows, provenance)
    second, _ = build_dataset_manifest(list(reversed(rows)), provenance)
    assert first == second


def test_evaluation_reports_metrics_breakdowns_errors_and_reliability():
    rows = [
        PredictionRow(
            "h1",
            "HUMAN",
            0.1,
            "HUMAN",
            0.9,
            split="test",
            language="en",
            domain="science",
            genre="report",
            document_length=100,
        ),
        PredictionRow(
            "a1",
            "AI_GENERATED",
            0.9,
            "AI_GENERATED",
            0.9,
            split="test",
            language="en",
            domain="science",
            genre="report",
            document_length=600,
        ),
        PredictionRow(
            "h2",
            "HUMAN",
            0.7,
            "AI_GENERATED",
            0.9,
            split="test",
            language="fr",
            domain="law",
            genre="essay",
            document_length=1200,
        ),
        PredictionRow(
            "a2",
            "AI_GENERATED",
            0.2,
            "HUMAN",
            0.9,
            split="test",
            language="fr",
            domain="law",
            genre="essay",
            document_length=300,
        ),
        PredictionRow(
            "ood-1",
            "OOD",
            0.8,
            "AI_GENERATED",
            0.8,
            abstained=False,
            split="test",
            language="de",
        ),
    ]
    report = evaluate_predictions(
        rows,
        held_out=True,
        reference_rows=[
            PredictionRow(
                "train-ref", "HUMAN", 0.2, "HUMAN", 0.8, split="train", language="en"
            )
        ],
        reproducibility=ReproducibilityMetadata(
            0, "git-sha", "features-v1", "pipeline-v1", "manifest-sha", "config-sha"
        ).as_dict(),
    )
    assert report["held_out_test"] is True
    assert report["metrics"]["precision"] == 0.5
    assert report["metrics"]["recall"] == 0.5
    assert report["metrics"]["f1"] == 0.5
    assert report["metrics"]["fpr"] == 0.5
    assert report["metrics"]["fnr"] == 0.5
    assert report["metrics"]["auroc"] is not None
    assert report["metrics"]["auprc"] is not None
    assert report["metrics"]["calibration_error"] is not None
    assert report["confidence_reliability"]["status"] == "AVAILABLE"
    assert report["error_analysis"]["false_positives"][0]["example_key"] == "h2"
    assert report["error_analysis"]["false_negatives"][0]["example_key"] == "a2"
    assert report["error_analysis"]["ood_failures"][0]["example_key"] == "ood-1"
    assert set(report["breakdowns"]) == {
        "language",
        "domain",
        "genre",
        "document_length",
        "writing_proficiency",
        "generation_source",
        "editing_intensity",
    }


def test_production_gate_requires_the_full_validation_contract():
    rows = [
        PredictionRow("h", "HUMAN", 0.1, "HUMAN", 0.95, split="test"),
        PredictionRow("a", "AI_GENERATED", 0.9, "AI_GENERATED", 0.95, split="test"),
        PredictionRow("ood", "OOD", 0.1, None, 0.2, abstained=True, split="test"),
    ]
    report = evaluate_predictions(
        rows,
        held_out=True,
        reference_rows=[
            PredictionRow("train-ref", "HUMAN", 0.2, "HUMAN", 0.8, split="train")
        ],
        reproducibility=ReproducibilityMetadata(
            0, "git-sha", "features-v1", "pipeline-v1", "manifest-sha", "config-sha"
        ).as_dict(),
    )
    report["leakage_free"] = True
    allowed, missing = validation_gate(report, max_fpr=0.05)
    assert allowed is True
    assert missing == []
    record = build_model_evaluation_record(
        model_id="validated-model",
        model_version="v1",
        dataset_version="corpus-v1",
        pipeline_version="pipeline-v1",
        report=report,
        requested_status="PRODUCTION",
    )
    assert record["status"] == "PRODUCTION"


def test_production_promotion_rejects_missing_calibration_and_reproducibility():
    report = evaluate_predictions(
        [
            PredictionRow("h", "HUMAN", 0.1, "HUMAN", None, split="test"),
            PredictionRow("a", "AI_GENERATED", 0.9, "AI_GENERATED", None, split="test"),
        ],
        held_out=True,
    )
    report["leakage_free"] = True
    with pytest.raises(ValueError, match="Production promotion blocked"):
        build_model_evaluation_record(
            model_id="blocked-model",
            model_version="v1",
            dataset_version="corpus-v1",
            pipeline_version="pipeline-v1",
            report=report,
            requested_status="PRODUCTION",
        )


async def test_governance_service_persists_and_freezes_dataset_version(db_session):
    dataset = await GovernanceService().create_dataset_version(
        db_session,
        dataset_id="service-corpus",
        version="v1",
        description="Validated service test corpus",
        rows=[
            _row("service-h", "train", "HUMAN", "service-author-h", "service-doc-h"),
            _row(
                "service-a", "test", "AI_GENERATED", "service-author-a", "service-doc-a"
            ),
        ],
        provenance={
            "source": "validated-corpus://service-test",
            "collection_method": "documented-manual-curation",
            "license": "internal-evaluation-license",
            "curator": "evaluation-team",
            "created_at": "2026-09-12T00:00:00Z",
        },
        required_labels={"HUMAN", "AI_GENERATED"},
    )
    assert str(dataset.status) == "VALIDATED"
    frozen = await GovernanceService().freeze_dataset_version(db_session, dataset)
    assert str(frozen.status) == "FROZEN"
    assert frozen.immutable is True
    assert frozen.manifest_sha256
