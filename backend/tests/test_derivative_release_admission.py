"""A release signature alone cannot admit an unreviewed derivative base or data."""

from uuid import uuid4

import pytest

from app.modules.model_platform import owner_decision
from app.modules.model_platform import admission as base_admission
from app.modules.model_platform.admission import Candidate, CandidateReview
from app.modules.model_platform.datasets import Dataset, DatasetReview, review_subject
from app.modules.model_platform.policy import (
    GATES,
    FileRef,
    Lineage,
    PolicyError,
    _verify_derivative_admission,
    canonical,
    digest,
)
from app.modules.model_platform.release import promote
from app.modules.model_platform import release as release_module
from app.modules.inference.registry import AzaeronModelRegistry
from tests.test_private_inference import approved_model


def _unreviewed_derivative(tmp_path):
    (tmp_path / "checkpoint.safetensors").write_bytes(b"unreviewed-derivative")
    (tmp_path / "tokenizer.json").write_bytes(b"{}")
    (tmp_path / "MODEL_CARD.md").write_text("Unreviewed derivative fixture")
    (tmp_path / "owner-decision.json").write_bytes(b"{}")
    checkpoint = digest(tmp_path / "checkpoint.safetensors")
    lineage = {
        "classification": "AZAERON_DERIVATIVE",
        "family": "writer",
        "run_id": str(uuid4()),
        "training_steps": 1,
        "checkpoint_sha256": checkpoint,
        "initialization_sha256": "0" * 64,
        "dataset_manifest_sha256": "1" * 64,
        "training_manifest_sha256": "0" * 64,
        "model_card_sha256": digest(tmp_path / "MODEL_CARD.md"),
        "code_sha256": "2" * 64,
        "base_model": "unreviewed/base",
        "base_revision": "a" * 40,
        "base_checkpoint_sha256": "b" * 64,
        "base_approval_sha256": "c" * 64,
        "purpose": "PRODUCTION",
    }
    training = {
        "checkpoint_sha256": checkpoint,
        "tokenizer_sha256": digest(tmp_path / "tokenizer.json"),
        "purpose": "PRODUCTION",
        "steps": 1,
        "run_id": lineage["run_id"],
        "code_sha256": lineage["code_sha256"],
        "dataset_manifest_sha256": lineage["dataset_manifest_sha256"],
        "initialization_sha256": lineage["initialization_sha256"],
    }
    (tmp_path / "training-manifest.json").write_bytes(canonical(training))
    lineage["training_manifest_sha256"] = digest(tmp_path / "training-manifest.json")
    (tmp_path / "lineage.json").write_bytes(canonical(lineage))
    (tmp_path / "evidence").mkdir()
    gates = {}
    for gate in GATES:
        value = {"status": "PASS", "gate": gate, "checkpoint_sha256": checkpoint}
        if gate == "evaluation":
            value.update(
                purpose="PRODUCTION",
                examples=1000,
                checks={"fixture": True},
                baseline_comparison="PASS",
                production_load_benchmark="PASS",
                dataset_manifest_sha256=lineage["dataset_manifest_sha256"],
            )
        path = tmp_path / "evidence" / f"{gate}.json"
        path.write_bytes(canonical(value))
        gates[gate] = {
            "status": "PASS",
            "checkpoint_sha256": checkpoint,
            "evidence": {"path": f"evidence/{gate}.json", "sha256": digest(path)},
        }
    approval = {
        "reviewer": "Ajmir Aribam",
        "approved_at": "2026-10-13",
        "reference": "authenticated-owner-fixture",
        "checkpoint_sha256": checkpoint,
        "owner_decision": {
            "path": "owner-decision.json",
            "sha256": digest(tmp_path / "owner-decision.json"),
        },
        "gates": gates,
    }
    metadata = approved_model().model_dump(mode="json")
    metadata.update(
        model_id="forged-derivative-fixture",
        tokenizer_revision=digest(tmp_path / "tokenizer.json"),
    )
    return metadata, approval


def test_derivative_release_rechecks_base_and_dataset_admission(tmp_path, monkeypatch):
    metadata, approval = _unreviewed_derivative(tmp_path)

    class ApprovedOwner:
        approver_name = "Ajmir Aribam"

    # Emulate a genuine release signature. This does not supply a base/data
    # approval; those must be independently verifiable at promotion and startup.
    monkeypatch.setattr(
        owner_decision, "require_owner_approval", lambda *_: ApprovedOwner()
    )
    monkeypatch.setattr(
        release_module, "require_owner_approval", lambda *_: ApprovedOwner()
    )
    with pytest.raises(PolicyError, match="derivative_admission_evidence_missing"):
        promote(tmp_path, metadata, approval, AzaeronModelRegistry())


def test_derivative_admission_attestations_bind_all_reviewed_hashes(
    tmp_path, monkeypatch
):
    base = tmp_path / "base-admission"
    data = tmp_path / "dataset-admission"
    base.mkdir()
    data.mkdir()
    (base / "owner-decision.json").write_bytes(b"TEST OWNER FIXTURE")
    (base / "technical-acceptance.json").write_bytes(b"TEST TECHNICAL FIXTURE")
    (base / "LICENSE").write_bytes(b"TEST LICENSE FIXTURE")
    (data / "owner-decision.json").write_bytes(b"TEST DATA OWNER FIXTURE")
    candidate = Candidate(
        candidate_id="fixture-base",
        purpose="PRODUCTION",
        repository="fixture/base",
        revision="a" * 40,
        artifacts={
            name: str(index) * 64
            for index, name in enumerate(
                [
                    "model.safetensors",
                    "tokenizer.json",
                    "LICENSE",
                    "README.md",
                    "config.json",
                ],
                1,
            )
        },
        weights=["model.safetensors"],
        tokenizer=["tokenizer.json"],
        license_file="LICENSE",
        model_card="README.md",
        license="TEST FIXTURE",
        architecture="gpt2",
        parameters=1,
        context=64,
        languages=["fixture"],
        runtime_compatibility=["fixture"],
    )
    candidate_file = base / "candidate.json"
    candidate = candidate.model_copy(
        update={
            "artifacts": {
                **candidate.artifacts,
                "LICENSE": digest(base / "LICENSE"),
            }
        }
    )
    candidate_file.write_bytes(canonical(candidate.model_dump(mode="json")))
    (tmp_path / "MODEL_CARD.md").write_text(
        f"Fixture derivative from {candidate.repository}@{candidate.revision}"
    )
    candidate_review = CandidateReview(
        subject_sha256=digest(candidate_file),
        purpose="PRODUCTION",
        reviewer="Ajmir Aribam",
        reviewer_kind="HUMAN",
        reviewed_at="2026-10-13",
        reference="TEST FIXTURE",
        license=candidate.license,
        commercial_use="PASS",
        commercial_training="PASS",
        redistribution_requirements="TEST FIXTURE",
        attribution_requirements="TEST FIXTURE",
        acceptable_use_restrictions="TEST FIXTURE",
        technical_review="PASS",
        technical_acceptance=FileRef(
            path="technical-acceptance.json",
            sha256=digest(base / "technical-acceptance.json"),
        ),
        owner_decision=FileRef(
            path="owner-decision.json", sha256=digest(base / "owner-decision.json")
        ),
    )
    candidate_review_file = base / "review.json"
    candidate_review_file.write_bytes(
        canonical(candidate_review.model_dump(mode="json"))
    )
    splits = {
        name: FileRef(path=f"{name}.jsonl", sha256=str(index) * 64)
        for index, name in enumerate(
            ["train", "validation", "calibration", "test", "ood"], 1
        )
    }
    dataset = Dataset(
        dataset_id="fixture-data",
        version="v1",
        purpose="PRODUCTION",
        source="TEST FIXTURE",
        license="TEST FIXTURE",
        commercial_training_permission="GRANTED",
        derivative_permission="GRANTED",
        redistribution_permission="PROHIBITED",
        provenance="TEST FIXTURE",
        acquisition_method="TEST FIXTURE",
        copyright_review="PASS",
        pii_review="PASS",
        language=["en"],
        domain=["fixture"],
        quality_tier="CURATED",
        allowed_model_families=["writer"],
        allowed_tasks=["rewrite"],
        contains_customer_content=False,
        splits=splits,
        review=FileRef(path="review.json", sha256="f" * 64),
    )
    dataset_review = DatasetReview(
        subject_sha256=review_subject(dataset),
        reviewer="Ajmir Aribam",
        reviewer_kind="HUMAN",
        reviewed_at="2026-10-13",
        evidence_reference="TEST FIXTURE",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        pii="PASS",
        owner_decision=FileRef(
            path="owner-decision.json", sha256=digest(data / "owner-decision.json")
        ),
    )
    dataset_review_file = data / "review.json"
    dataset_review_file.write_bytes(canonical(dataset_review.model_dump(mode="json")))
    dataset = dataset.model_copy(
        update={
            "review": FileRef(path="review.json", sha256=digest(dataset_review_file))
        }
    )
    dataset_file = data / "dataset.json"
    dataset_file.write_bytes(canonical(dataset.model_dump(mode="json")))
    from app.modules.model_platform.admission import inventory_hash

    base_weights = inventory_hash(
        {name: candidate.artifacts[name] for name in candidate.weights}
    )
    lineage = Lineage(
        classification="AZAERON_DERIVATIVE",
        family="writer",
        run_id=uuid4(),
        training_steps=1,
        checkpoint_sha256="d" * 64,
        initialization_sha256="e" * 64,
        dataset_manifest_sha256=digest(dataset_file),
        training_manifest_sha256="b" * 64,
        model_card_sha256="a" * 64,
        code_sha256="c" * 64,
        base_model=candidate.repository,
        base_revision=candidate.revision,
        base_checkpoint_sha256=candidate.artifacts[candidate.weights[0]],
        base_approval_sha256=digest(base / "owner-decision.json"),
        purpose="PRODUCTION",
    )
    training = {
        "candidate_manifest_sha256": digest(candidate_file),
        "base_review_sha256": digest(candidate_review_file),
        "base_owner_decision_sha256": digest(base / "owner-decision.json"),
        "technical_acceptance_sha256": digest(base / "technical-acceptance.json"),
        "base_repository": candidate.repository,
        "base_revision": candidate.revision,
        "base_artifacts": candidate.artifacts,
        "dataset_review_sha256": digest(dataset_review_file),
        "dataset_owner_decision_sha256": digest(data / "owner-decision.json"),
        "dataset_splits": {name: ref.sha256 for name, ref in splits.items()},
    }
    provenance = {
        "candidate_manifest_sha256": digest(candidate_file),
        "candidate_review_sha256": digest(candidate_review_file),
        "base_owner_decision_sha256": digest(base / "owner-decision.json"),
        "technical_acceptance_sha256": digest(base / "technical-acceptance.json"),
        "base_weights_sha256": base_weights,
        "base_license_sha256": digest(base / "LICENSE"),
        "dataset_manifest_sha256": digest(dataset_file),
        "dataset_review_sha256": digest(dataset_review_file),
        "dataset_owner_decision_sha256": digest(data / "owner-decision.json"),
        "training_manifest_sha256": lineage.training_manifest_sha256,
    }
    (tmp_path / "derivative-admission.json").write_bytes(canonical(provenance))

    class ApprovedOwner:
        approver_name = "Ajmir Aribam"

    monkeypatch.setattr(
        owner_decision, "require_owner_approval", lambda *_: ApprovedOwner()
    )
    monkeypatch.setattr(base_admission, "require_technical_acceptance", lambda *_: ())
    _verify_derivative_admission(lineage, training, tmp_path)
    provenance["dataset_owner_decision_sha256"] = "f" * 64
    (tmp_path / "derivative-admission.json").write_bytes(canonical(provenance))
    with pytest.raises(PolicyError, match="derivative_admission_hash_mismatch"):
        _verify_derivative_admission(lineage, training, tmp_path)
