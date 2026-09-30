"""Admission, leakage, compute and release attacks; no production model fixtures."""

import json

import pytest
from pydantic import ValidationError

from app.modules.model_platform.admission import (
    Candidate,
    CandidateReview,
    verify_bundle,
)
from app.modules.model_platform.datasets import (
    Dataset,
    DatasetReview,
    read_dataset,
    review_subject,
)
from app.modules.model_platform.derivative import DerivativeConfig
from app.modules.model_platform.detector_metrics import (
    detector_report,
    operating_thresholds,
)
from app.modules.model_platform.hardware import enforce, plan
from app.modules.model_platform.policy import FileRef, PolicyError, canonical, digest
from app.modules.model_platform.human_review import writer_review
from app.modules.inference.registry import AzaeronModelRegistry
from tests.test_private_inference import approved_model


def candidate_fixture(root):
    root.mkdir()
    header = canonical(
        {"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}
    )
    (root / "model.safetensors").write_bytes(
        len(header).to_bytes(8, "little") + header + b"\x00" * 4
    )
    (root / "config.json").write_bytes(
        canonical(
            {
                "model_type": "gpt2",
                "n_positions": 64,
                "n_layer": 1,
                "n_embd": 16,
                "n_head": 2,
                "vocab_size": 8,
            }
        )
    )
    (root / "tokenizer.json").write_text("{}")
    (root / "LICENSE").write_text("TEST_ONLY")
    (root / "README.md").write_text("TEST_ONLY")
    return Candidate(
        candidate_id="fixture",
        purpose="TEST_ONLY",
        repository="local/fixture",
        revision="a" * 40,
        artifacts={p.name: digest(p) for p in root.iterdir()},
        weights=["model.safetensors"],
        tokenizer=["tokenizer.json"],
        license_file="LICENSE",
        model_card="README.md",
        license="TEST_ONLY",
        architecture="gpt2",
        parameters=1,
        context=64,
        languages=["fixture"],
        runtime_compatibility=["fixture"],
    )


@pytest.mark.parametrize("mutation", ["tamper", "extra", "remote", "symlink", "header"])
def test_candidate_inventory_attacks(tmp_path, mutation):
    root = tmp_path / "source"
    model = candidate_fixture(root)
    verify_bundle(model, root)
    if mutation == "tamper":
        (root / "LICENSE").write_text("changed")
    elif mutation == "extra":
        (root / "evil.py").write_text("pass")
    elif mutation == "symlink":
        (root / "tokenizer.json").unlink()
        (root / "tokenizer.json").symlink_to(root / "config.json")
    else:
        if mutation == "remote":
            data = json.loads((root / "config.json").read_bytes())
            data["auto_map"] = {"AutoModel": "evil.Model"}
            (root / "config.json").write_bytes(canonical(data))
        else:
            (root / "model.safetensors").write_bytes((2**62).to_bytes(8, "little"))
        model = model.model_copy(
            update={"artifacts": {p.name: digest(p) for p in root.iterdir()}}
        )
    with pytest.raises(PolicyError):
        verify_bundle(model, root)


def test_floating_revision_and_fake_review_rejected(tmp_path):
    candidate = candidate_fixture(tmp_path / "source")
    with pytest.raises(ValidationError):
        Candidate.model_validate({**candidate.model_dump(), "revision": "main"})
    with pytest.raises(ValidationError):
        CandidateReview.model_validate({"commercial_use": "UNKNOWN"})


def dataset_fixture(root):
    rows = {}
    for split in ["train", "validation", "calibration", "test", "ood"]:
        path = root / (split + ".jsonl")
        row = {
            "id": split,
            "group": split,
            "input": split,
            "target": "AI",
            "language": "en",
            "domain": "fixture",
            "task": "classify",
            "slices": [],
            "generator_family": split,
        }
        path.write_bytes(canonical(row) + b"\n")
        rows[split] = {"path": path.name, "sha256": digest(path)}
    return Dataset(
        dataset_id="fixture",
        version="1",
        purpose="TEST_ONLY",
        source="fixture",
        license="TEST_ONLY",
        commercial_training_permission="GRANTED",
        redistribution_permission="PROHIBITED",
        provenance="fixture",
        acquisition_method="generated",
        copyright_review="PASS",
        pii_review="PASS",
        language=["en"],
        domain=["fixture"],
        quality_tier="TEST_FIXTURE",
        allowed_model_families=["detector"],
        contains_customer_content=False,
        splits=rows,
        review={"path": "review.json", "sha256": "0" * 64},
    )


def save_dataset(root, manifest):
    review = DatasetReview(
        subject_sha256=review_subject(manifest),
        reviewer="TEST_ONLY",
        reviewer_kind="TEST_FIXTURE",
        reviewed_at="2026-09-30",
        evidence_reference="TEST_ONLY",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        pii="PASS",
    )
    (root / "review.json").write_bytes(canonical(review.model_dump()) + b"\n")
    manifest = manifest.model_copy(
        update={
            "review": FileRef(path="review.json", sha256=digest(root / "review.json"))
        }
    )
    (root / "dataset.json").write_bytes(canonical(manifest.model_dump()) + b"\n")
    return root / "dataset.json"


@pytest.mark.parametrize("field", ["group", "input", "id", "generator_family"])
def test_five_split_leakage_rejected(tmp_path, field):
    manifest = dataset_fixture(tmp_path)
    path = save_dataset(tmp_path, manifest)
    assert len(read_dataset(path, "detector", smoke=True)[1]) == 5
    test = tmp_path / "test.jsonl"
    row = json.loads(test.read_bytes())
    row[field] = "train"
    test.write_bytes(canonical(row) + b"\n")
    values = manifest.model_dump()
    values["splits"]["test"]["sha256"] = digest(test)
    path = save_dataset(tmp_path, Dataset.model_validate(values))
    with pytest.raises(PolicyError, match="leakage"):
        read_dataset(path, "detector", smoke=True)


def test_dataset_reviews_bound_and_customer_data_rejected(tmp_path):
    manifest = dataset_fixture(tmp_path)
    path = save_dataset(tmp_path, manifest)
    with pytest.raises(PolicyError, match="purpose"):
        read_dataset(path, "detector")
    values = json.loads(path.read_bytes())
    values["license"] = "changed"
    path.write_bytes(canonical(values))
    with pytest.raises(PolicyError, match="binding"):
        read_dataset(path, "detector", smoke=True)
    with pytest.raises(ValidationError):
        Dataset.model_validate(
            {**manifest.model_dump(), "contains_customer_content": True}
        )


def test_gpu_plan_blocks_oversized_training():
    value = plan(
        7_000_000_000,
        7_000_000_000,
        method="full",
        precision="bfloat16",
        layers=32,
        width=4096,
        heads=32,
        vocab=128000,
        sequence=2048,
        microbatch=1,
        accumulation=16,
        checkpointing=True,
        tokens=10_000_000,
    )
    assert value["optimizer_bytes"] == 56_000_000_000
    with pytest.raises(PolicyError, match="memory"):
        enforce(
            value,
            {
                "cuda": [],
                "memory_total_bytes": 16 * 1024**3,
                "memory_available_bytes": 10 * 1024**3,
                "disk_free_bytes": 60 * 1024**3,
            },
            "cpu",
            output_bytes=28_000_000_000,
        )
    with pytest.raises(ValidationError):
        DerivativeConfig.model_validate({"method": "qlora", "device": "mps"})


def test_same_base_verifier_rejected_even_with_new_weights():
    writer = approved_model(model_id="writer")
    verifier = approved_model(model_id="verifier", tasks=["verify"])
    shared = {
        "classification": "AZAERON_DERIVATIVE",
        "base_model": "fixture/base",
        "base_revision": "a" * 40,
        "base_checkpoint_sha256": "a" * 64,
        "base_approval_sha256": "b" * 64,
    }
    writer = approved_model(
        model_id="writer", lineage={**writer.lineage.model_dump(), **shared}
    )
    verifier = approved_model(
        model_id="verifier",
        tasks=["verify"],
        lineage={**verifier.lineage.model_dump(), **shared},
    )
    with pytest.raises(ValidationError, match="independent base"):
        AzaeronModelRegistry(models=[writer, verifier])


def test_detector_ties_calibration_thresholds_and_region_abstention():
    threshold = operating_thresholds([0.1, 0.9, 0.8], [0, 1, 2])
    probs = [[0.9, 0.05, 0.05], [0.01, 0.98, 0.01], [0.01, 0.01, 0.98]]
    result = detector_report(probs, [0, 1, 2], ["en", "en", "ood"], {"en"}, threshold)
    assert result["auroc"] == result["auprc"] == 1
    assert result["coverage"] == pytest.approx(2 / 3)
    assert result["subgroups"]["ood"]["coverage"] == 0
    assert result["operating_points"]["0.001"]["insufficient_fpr_resolution"]
    tied = detector_report(
        [[0.5, 0.25, 0.25]] * 2, [0, 1], ["en"] * 2, {"en"}, threshold
    )
    assert tied["auroc"] == tied["auprc"] == 0.5
    with pytest.raises(PolicyError):
        detector_report([[float("nan"), 0, 1]], [0], ["en"], {"en"}, threshold)


def test_model_self_rating_is_not_human_review(tmp_path):
    path = tmp_path / "review.json"
    path.write_bytes(
        canonical(
            {
                "checkpoint_sha256": "a" * 64,
                "dataset_manifest_sha256": "b" * 64,
                "method": "blinded_independent_ratings_v1",
                "reviewer_kind": "MODEL",
                "ratings": [],
            }
        )
    )
    with pytest.raises(PolicyError):
        writer_review(path, "a" * 64, "b" * 64, {"sample": "c" * 64})
