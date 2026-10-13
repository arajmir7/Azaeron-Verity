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
    ReleaseApproval,
    _verify_derivative_admission,
    canonical,
    digest,
    release_subject_sha256,
    verify_release_files,
)
from app.modules.model_platform.release import promote
from app.modules.inference.registry import AzaeronModelRegistry, ModelRecord
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


def _release_model(bundle, metadata, approval):
    lineage = Lineage.model_validate_json((bundle / "lineage.json").read_bytes())
    release = ReleaseApproval.model_validate(approval)
    artifacts = {
        path.relative_to(bundle).as_posix(): digest(path)
        for path in bundle.rglob("*")
        if path.is_file()
    }
    return ModelRecord.model_validate(
        {
            **metadata,
            "artifacts": artifacts,
            "lineage": lineage,
            "release": release,
            "status": "APPROVED",
            "commercial_use_approved": True,
            "approval_reference": release.reference,
            "evaluation_sha256": release.gates["evaluation"].evidence.sha256,
        }
    )


def test_release_subject_binds_scope_without_owner_decision_cycle(tmp_path):
    metadata, approval = _unreviewed_derivative(tmp_path)
    original = _release_model(tmp_path, metadata, approval)
    subject = release_subject_sha256(original)
    values = original.model_dump(mode="json")

    for field, replacement in (
        ("model_id", "different-model"),
        ("runtime_image", "example.invalid/other@sha256:" + "e" * 64),
        ("tasks", ["chat"]),
    ):
        changed = {**values, field: replacement}
        assert release_subject_sha256(ModelRecord.model_validate(changed)) != subject

    changed = original.model_dump(mode="json")
    changed["lineage"]["classification"] = "AZAERON_NATIVE"
    for key in (
        "base_model",
        "base_revision",
        "base_checkpoint_sha256",
        "base_approval_sha256",
    ):
        changed["lineage"][key] = None
    assert release_subject_sha256(ModelRecord.model_validate(changed)) != subject

    changed = original.model_dump(mode="json")
    changed["release"]["gates"]["security"]["evidence"]["sha256"] = "f" * 64
    changed["artifacts"]["evidence/security.json"] = "f" * 64
    assert release_subject_sha256(ModelRecord.model_validate(changed)) != subject

    decision_derived = original.model_dump(mode="json")
    decision_derived["artifacts"]["owner-decision.json"] = "f" * 64
    decision_derived["release"]["owner_decision"]["sha256"] = "f" * 64
    decision_derived["release"]["reference"] = "eventual-comment-id"
    decision_derived["approval_reference"] = "eventual-comment-id"
    assert (
        release_subject_sha256(ModelRecord.model_validate(decision_derived)) == subject
    )


def test_native_reclassification_cannot_reuse_derivative_release_decision(
    tmp_path, monkeypatch
):
    metadata, approval = _unreviewed_derivative(tmp_path)
    reviewed_subject = release_subject_sha256(
        _release_model(tmp_path, metadata, approval)
    )
    lineage = Lineage.model_validate_json((tmp_path / "lineage.json").read_bytes())
    native = lineage.model_dump(mode="json")
    native["classification"] = "AZAERON_NATIVE"
    for key in (
        "base_model",
        "base_revision",
        "base_checkpoint_sha256",
        "base_approval_sha256",
    ):
        native[key] = None
    (tmp_path / "lineage.json").write_bytes(canonical(native))

    def owner_for_original_scope(_path, kind, subject, use):
        assert kind == "MODEL_RELEASE" and use == "production_release"
        if subject != reviewed_subject:
            raise PolicyError("owner_release_subject_mismatch")
        raise AssertionError("Reclassified model unexpectedly retained owner scope")

    monkeypatch.setattr(
        owner_decision, "require_owner_approval", owner_for_original_scope
    )
    with pytest.raises(PolicyError, match="owner_release_subject_mismatch"):
        promote(tmp_path, metadata, approval, AzaeronModelRegistry())


def test_release_reference_must_match_authenticated_comment(tmp_path, monkeypatch):
    metadata, approval = _unreviewed_derivative(tmp_path)
    lineage = Lineage.model_validate_json((tmp_path / "lineage.json").read_bytes())
    native = lineage.model_dump(mode="json")
    native["classification"] = "AZAERON_NATIVE"
    for key in (
        "base_model",
        "base_revision",
        "base_checkpoint_sha256",
        "base_approval_sha256",
    ):
        native[key] = None
    (tmp_path / "lineage.json").write_bytes(canonical(native))
    model = _release_model(tmp_path, metadata, approval)

    class ApprovedOwner:
        approver_name = "Ajmir Aribam"
        confirmation_reference = "github-issue-comment:123:sha256:" + "a" * 64

    monkeypatch.setattr(
        owner_decision, "require_owner_approval", lambda *_: ApprovedOwner()
    )
    with pytest.raises(PolicyError, match="release_confirmation_reference_mismatch"):
        promote(tmp_path, metadata, approval, AzaeronModelRegistry())
    with pytest.raises(PolicyError, match="release_confirmation_reference_mismatch"):
        verify_release_files(model, tmp_path)


def test_derivative_release_rechecks_base_and_dataset_admission(tmp_path, monkeypatch):
    metadata, approval = _unreviewed_derivative(tmp_path)

    class ApprovedOwner:
        approver_name = "Ajmir Aribam"
        confirmation_reference = approval["reference"]

    # Emulate a genuine release signature. This does not supply a base/data
    # approval; those must be independently verifiable at promotion and startup.
    monkeypatch.setattr(
        owner_decision, "require_owner_approval", lambda *_: ApprovedOwner()
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
