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
    gates: dict[str, GateEvidence]

    @model_validator(mode="after")
    def all_gates(self):
        if set(self.gates) != GATES or any(
            item.checkpoint_sha256 != self.checkpoint_sha256
            for item in self.gates.values()
        ):
            raise ValueError("Every promotion gate must pass for this exact checkpoint")
        return self


def verify_release_files(model, root: Path):
    """Called at serving startup, after complete bundle integrity validation."""
    lineage, release = model.lineage, model.release
    if not lineage or not release or lineage.purpose != "PRODUCTION":
        raise PolicyError("owned_production_lineage_required")
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
