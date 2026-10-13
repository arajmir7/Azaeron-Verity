"""Fail-closed local training inputs and hash-bound release records.

Review records are attestations by the operator's reviewers, not automated legal
opinions. The trainer cannot create reviews or grant production approval.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Family = Literal["writer", "verifier", "detector", "embed"]
GATES = frozenset(
    {
        "license",
        "rights",
        "provenance",
        "training",
        "checkpoint",
        "evaluation",
        "security",
        "private_runtime",
    }
)
FAMILY_TASKS = {
    "writer": {"chat", "summarize", "refine", "extract"},
    "verifier": {"verify"},
    "detector": {"classify"},
    "embed": {"embed", "rerank"},
}


class PolicyError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise PolicyError("regular_file_required")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def local_file(root: Path, name: str) -> Path:
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise PolicyError("unsafe_artifact_path")
    path = root / relative
    if any(part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise PolicyError("symlink_not_allowed")
    if not path.resolve().is_relative_to(root.resolve()):
        raise PolicyError("unsafe_artifact_path")
    return path


class FileRef(StrictModel):
    path: str = Field(min_length=1)
    sha256: Digest

    def verify(self, root: Path) -> Path:
        path = local_file(root, self.path)
        if digest(path) != self.sha256:
            raise PolicyError("artifact_hash_mismatch")
        return path


class Review(StrictModel):
    subject_sha256: Digest
    reviewer: str = Field(min_length=1)
    reviewed_at: str = Field(min_length=10)
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    commercial_training_rights: Literal[True]
    provenance: Literal["PASS"]
    pii_review: Literal["PASS"]
    copyright_review: Literal["PASS"]
    allowed_tasks: list[Family] = Field(min_length=1)
    evidence_reference: str = Field(min_length=1)


class DatasetManifest(StrictModel):
    schema_version: Literal[1] = 1
    dataset_id: str = Field(min_length=1)
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    allowed_tasks: list[Family] = Field(min_length=1)
    splits: dict[str, FileRef]
    reviews: dict[str, FileRef]

    def load_rows(self, root: Path, family: Family, *, smoke: bool = False):
        if self.purpose != "PRODUCTION" and not smoke:
            raise PolicyError("test_data_cannot_train_production_model")
        if self.purpose == "PRODUCTION":
            raise PolicyError("production_requires_five_split_dataset_v2")
        if family not in self.allowed_tasks or set(self.splits) != {
            "train",
            "calibration",
            "evaluation",
        }:
            raise PolicyError("dataset_tasks_or_splits_missing")
        if set(self.reviews) != set(self.splits):
            raise PolicyError("rights_review_missing")
        rows, seen, groups, identifiers = {}, set(), set(), set()
        for split, ref in self.splits.items():
            source = ref.verify(root)
            review = Review.model_validate_json(
                self.reviews[split].verify(root).read_bytes()
            )
            if (
                review.subject_sha256 != ref.sha256
                or family not in review.allowed_tasks
                or review.source != self.source
                or review.license != self.license
            ):
                raise PolicyError("rights_review_does_not_cover_dataset")
            if source.stat().st_size > 256 * 1024 * 1024:
                raise PolicyError("dataset_shard_too_large")
            values = [
                json.loads(line)
                for line in source.read_text().splitlines()
                if line.strip()
            ]
            if not values:
                raise PolicyError("empty_dataset_split")
            split_seen, split_groups = set(), set()
            for row in values:
                required = {"id", "group", "input", "target"}
                if set(row) != required or not all(
                    isinstance(row[k], str) and row[k].strip() for k in required
                ):
                    raise PolicyError("invalid_training_row")
                if row["id"] in identifiers or max(map(len, row.values())) > 200_000:
                    raise PolicyError("duplicate_id_or_oversized_row")
                identifiers.add(row["id"])
                key = hashlib.sha256(
                    " ".join(row["input"].casefold().split()).encode()
                ).hexdigest()
                if key in seen or key in split_seen or row["group"] in groups:
                    raise PolicyError("duplicate_or_split_leakage")
                split_seen.add(key)
                split_groups.add(row["group"])
            seen.update(split_seen)
            groups.update(split_groups)
            rows[split] = values
        return rows


class Lineage(StrictModel):
    classification: Literal["AZAERON_NATIVE", "AZAERON_DERIVATIVE"]
    family: Family
    run_id: UUID
    training_steps: int = Field(gt=0)
    checkpoint_sha256: Digest
    initialization_sha256: Digest
    dataset_manifest_sha256: Digest
    training_manifest_sha256: Digest
    model_card_sha256: Digest
    code_sha256: Digest
    base_model: str | None = None
    base_revision: Annotated[str, Field(pattern=r"^[a-f0-9]{40,64}$")] | None = None
    base_checkpoint_sha256: Digest | None = None
    base_approval_sha256: Digest | None = None
    purpose: Literal["PRODUCTION", "TEST_ONLY"]

    @model_validator(mode="after")
    def new_checkpoint(self):
        if self.checkpoint_sha256 == self.initialization_sha256:
            raise ValueError("Unchanged initialization is not an Azaeron model")
        if self.classification == "AZAERON_DERIVATIVE" and not all(
            [
                self.base_model,
                self.base_revision,
                self.base_checkpoint_sha256,
                self.base_approval_sha256,
            ]
        ):
            raise ValueError("Derivative base lineage and approval are required")
        if self.classification == "AZAERON_NATIVE" and any(
            [
                self.base_model,
                self.base_revision,
                self.base_checkpoint_sha256,
                self.base_approval_sha256,
            ]
        ):
            raise ValueError("A base checkpoint must be classified as a derivative")
        return self


class GateEvidence(StrictModel):
    status: Literal["PASS"]
    checkpoint_sha256: Digest
    evidence: FileRef


class ReleaseApproval(StrictModel):
    reviewer: str = Field(min_length=1)
    approved_at: str = Field(min_length=10)
    reference: str = Field(min_length=1)
    checkpoint_sha256: Digest
    owner_decision: FileRef | None = None
    gates: dict[str, GateEvidence]

    @model_validator(mode="after")
    def all_gates(self):
        if self.owner_decision and self.owner_decision.path != "owner-decision.json":
            raise ValueError("Owner decision must be the adjacent owner-decision.json")
        if set(self.gates) != GATES or any(
            item.checkpoint_sha256 != self.checkpoint_sha256
            for item in self.gates.values()
        ):
            raise ValueError("Every promotion gate must pass for this exact checkpoint")
        return self


class DerivativeAdmission(StrictModel):
    """Compact, hash-bound copies of the admissions used for a derivative."""

    candidate_manifest_sha256: Digest
    candidate_review_sha256: Digest
    base_owner_decision_sha256: Digest
    technical_acceptance_sha256: Digest
    base_weights_sha256: Digest
    base_license_sha256: Digest
    dataset_manifest_sha256: Digest
    dataset_review_sha256: Digest
    dataset_owner_decision_sha256: Digest
    training_manifest_sha256: Digest


def _required_attestation(root: Path, name: str) -> Path:
    path = local_file(root, name)
    if not path.is_file() or path.stat().st_size > 4 * 1024**2:
        raise PolicyError("derivative_admission_evidence_missing")
    return path


def _verify_derivative_admission(lineage: Lineage, training: dict, root: Path) -> None:
    """Recheck external decisions at promotion and at every serving load.

    The release bundle carries only admission records and their reviewed hashes,
    not private training rows or a second copy of base weights. This attests
    admissions and lineage; it is not a proof of the physical training execution.
    """
    from .admission import (
        Candidate,
        CandidateReview,
        inventory_hash,
        require_technical_acceptance,
    )
    from .datasets import Dataset, DatasetReview, SPLITS, review_subject
    from .owner_decision import require_owner_approval

    base_root = root / "base-admission"
    data_root = root / "dataset-admission"
    candidate_file = _required_attestation(base_root, "candidate.json")
    candidate_review_file = _required_attestation(base_root, "review.json")
    provenance_file = _required_attestation(root, "derivative-admission.json")
    dataset_file = _required_attestation(data_root, "dataset.json")
    candidate = Candidate.model_validate_json(candidate_file.read_bytes())
    candidate_review = CandidateReview.model_validate_json(
        candidate_review_file.read_bytes()
    )
    candidate_hash = digest(candidate_file)
    if (
        candidate.purpose != "PRODUCTION"
        or candidate_review.purpose != "PRODUCTION"
        or candidate_review.subject_sha256 != candidate_hash
        or candidate_review.license != candidate.license
        or candidate_review.owner_decision is None
        or candidate_review.technical_acceptance is None
    ):
        raise PolicyError("derivative_base_admission_mismatch")
    base_license_file = _required_attestation(base_root, candidate.license_file)
    if digest(base_license_file) != candidate.artifacts[candidate.license_file]:
        raise PolicyError("derivative_base_license_mismatch")
    model_card = _required_attestation(root, "MODEL_CARD.md").read_text(
        encoding="utf-8"
    )
    if f"{candidate.repository}@{candidate.revision}" not in model_card:
        raise PolicyError("derivative_model_card_base_attribution_missing")
    base_owner_file = candidate_review.owner_decision.verify(base_root)
    base_owner = require_owner_approval(
        base_owner_file, "BASE_MODEL", candidate_hash, "commercial_derivative_training"
    )
    if candidate_review.reviewer != base_owner.approver_name:
        raise PolicyError("derivative_base_reviewer_mismatch")
    require_technical_acceptance(base_root, candidate_review, candidate, candidate_hash)
    base_weights_hash = inventory_hash(
        {name: candidate.artifacts[name] for name in candidate.weights}
    )
    # A single-file base has an established checkpoint SHA. A sharded base has
    # no single file SHA, so its canonical weight inventory is the checkpoint.
    base_checkpoint_hash = (
        candidate.artifacts[candidate.weights[0]]
        if len(candidate.weights) == 1
        else base_weights_hash
    )

    dataset = Dataset.model_validate_json(dataset_file.read_bytes())
    dataset_hash = digest(dataset_file)
    if (
        dataset.purpose != "PRODUCTION"
        or dataset.derivative_permission != "GRANTED"
        or lineage.family not in dataset.allowed_model_families
        or not dataset.allowed_tasks
        or set(dataset.splits) != SPLITS
        or dataset.quality_tier == "TEST_FIXTURE"
    ):
        raise PolicyError("derivative_dataset_admission_mismatch")
    dataset_review_file = dataset.review.verify(data_root)
    dataset_review = DatasetReview.model_validate_json(dataset_review_file.read_bytes())
    if (
        dataset_review.subject_sha256 != review_subject(dataset)
        or dataset_review.reviewer_kind != "HUMAN"
        or dataset_review.owner_decision is None
    ):
        raise PolicyError("derivative_dataset_review_mismatch")
    dataset_owner_file = dataset_review.owner_decision.verify(data_root)
    dataset_owner = require_owner_approval(
        dataset_owner_file,
        "DATASET",
        review_subject(dataset),
        "commercial_training",
    )
    if dataset_review.reviewer != dataset_owner.approver_name:
        raise PolicyError("derivative_dataset_reviewer_mismatch")

    provenance = DerivativeAdmission.model_validate_json(provenance_file.read_bytes())
    if provenance.model_dump() != {
        "candidate_manifest_sha256": candidate_hash,
        "candidate_review_sha256": digest(candidate_review_file),
        "base_owner_decision_sha256": digest(base_owner_file),
        "technical_acceptance_sha256": candidate_review.technical_acceptance.sha256,
        "base_weights_sha256": base_weights_hash,
        "base_license_sha256": digest(base_license_file),
        "dataset_manifest_sha256": dataset_hash,
        "dataset_review_sha256": digest(dataset_review_file),
        "dataset_owner_decision_sha256": digest(dataset_owner_file),
        "training_manifest_sha256": lineage.training_manifest_sha256,
    }:
        raise PolicyError("derivative_admission_hash_mismatch")
    if (
        lineage.base_model != candidate.repository
        or lineage.base_revision != candidate.revision
        or lineage.base_checkpoint_sha256 != base_checkpoint_hash
        or lineage.base_approval_sha256 != digest(base_owner_file)
        or lineage.dataset_manifest_sha256 != dataset_hash
        or training.get("candidate_manifest_sha256") != candidate_hash
        or training.get("base_review_sha256") != digest(candidate_review_file)
        or training.get("base_owner_decision_sha256") != digest(base_owner_file)
        or training.get("technical_acceptance_sha256")
        != candidate_review.technical_acceptance.sha256
        or training.get("base_repository") != candidate.repository
        or training.get("base_revision") != candidate.revision
        or training.get("base_artifacts") != candidate.artifacts
        or training.get("dataset_review_sha256") != digest(dataset_review_file)
        or training.get("dataset_owner_decision_sha256") != digest(dataset_owner_file)
        or training.get("dataset_splits")
        != {name: ref.sha256 for name, ref in dataset.splits.items()}
    ):
        raise PolicyError("derivative_training_lineage_mismatch")


def verify_release_files(model, root: Path):
    """Called at serving startup, after complete bundle integrity validation."""
    lineage, release = model.lineage, model.release
    if not lineage or not release or lineage.purpose != "PRODUCTION":
        raise PolicyError("owned_production_lineage_required")
    if release.owner_decision is None:
        raise PolicyError("owner_release_decision_required")
    from .owner_decision import require_owner_approval

    owner = require_owner_approval(
        release.owner_decision.verify(root),
        "MODEL_RELEASE",
        lineage.checkpoint_sha256,
        "production_release",
    )
    if release.reviewer != owner.approver_name:
        raise PolicyError("release_reviewer_is_not_project_owner")
    for gate, item in release.gates.items():
        evidence = json.loads(item.evidence.verify(root).read_bytes())
        if (
            evidence.get("status") != "PASS"
            or evidence.get("checkpoint_sha256") != lineage.checkpoint_sha256
        ):
            raise PolicyError("release_evidence_binding_failed")
        if evidence.get("gate") != gate:
            raise PolicyError("release_evidence_gate_mismatch")
    manifest = json.loads((root / "training-manifest.json").read_bytes())
    if (
        digest(root / "tokenizer.json") != model.tokenizer_revision
        or manifest.get("tokenizer_sha256") != model.tokenizer_revision
    ):
        raise PolicyError("tokenizer_lineage_mismatch")
    if (
        manifest.get("checkpoint_sha256") != lineage.checkpoint_sha256
        or manifest.get("purpose") != "PRODUCTION"
        or manifest.get("steps") != lineage.training_steps
        or manifest.get("run_id") != str(lineage.run_id)
        or manifest.get("code_sha256") != lineage.code_sha256
        or manifest.get("dataset_manifest_sha256") != lineage.dataset_manifest_sha256
        or manifest.get("initialization_sha256") != lineage.initialization_sha256
    ):
        raise PolicyError("training_lineage_mismatch")
    if lineage.classification == "AZAERON_DERIVATIVE":
        _verify_derivative_admission(lineage, manifest, root)
    evaluation = json.loads(
        release.gates["evaluation"].evidence.verify(root).read_bytes()
    )
    if (
        evaluation.get("purpose") != "PRODUCTION"
        or evaluation.get("examples", 0) < 1000
        or not evaluation.get("checks")
        or not all(value is True for value in evaluation["checks"].values())
        or evaluation.get("baseline_comparison") != "PASS"
        or evaluation.get("production_load_benchmark") != "PASS"
        or evaluation.get("dataset_manifest_sha256") != lineage.dataset_manifest_sha256
    ):
        raise PolicyError("evaluation_or_comparative_benchmarks_incomplete")
    if lineage.family in {"detector", "verifier"}:
        if json.loads((root / "calibration.json").read_bytes()) != evaluation.get(
            "calibration"
        ):
            raise PolicyError("calibration_not_bound_to_evaluation")
