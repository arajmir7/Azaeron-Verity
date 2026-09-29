"""Versioned model approval and artifact-integrity policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Task = Literal[
    "chat", "summarize", "refine", "extract", "classify", "embed", "rerank", "verify"
]
Status = Literal["CANDIDATE", "EVALUATING", "APPROVED", "RETIRED", "BLOCKED"]


class InferenceUnavailable(RuntimeError):
    """Only this stable, non-content-bearing reason may cross the API boundary."""

    def __init__(self, code: str = "inference_unavailable"):
        self.code = code
        super().__init__(code)


class ModelRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    model_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    tokenizer_revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    artifacts: dict[str, str] = Field(min_length=1)
    license: str = Field(min_length=1)
    commercial_use_approved: bool = False
    approval_reference: str | None = None
    evaluation_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    context_limit: int = Field(ge=256, le=2_000_000)
    runtime: Literal["vllm"] = "vllm"
    runtime_image: str = Field(pattern=r"^[^\s]+@sha256:[a-f0-9]{64}$")
    quantization: str = Field(min_length=1)
    tasks: list[Task] = Field(min_length=1)
    languages: list[str] = Field(min_length=1)
    hardware: dict[str, str] = Field(min_length=1)
    status: Status

    @model_validator(mode="after")
    def review(self):
        for name, digest in self.artifacts.items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError("Artifact paths must stay inside the approved bundle")
            if path.suffix.lower() in {".py", ".pickle", ".pkl", ".pt", ".bin"}:
                raise ValueError("Executable or pickle model artifacts are prohibited")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Artifact digests must be SHA-256")
        if self.status == "APPROVED" and not (
            self.commercial_use_approved
            and self.approval_reference
            and self.evaluation_sha256
        ):
            raise ValueError("Approval requires commercial-use and evaluation evidence")
        return self


class AzaeronModelRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    models: list[ModelRecord] = Field(default_factory=list)
    routes: dict[Task, str] = Field(default_factory=dict)
    promotion_requirements: list[str] = Field(default_factory=list)
    status: str = "BLOCKED_NO_APPROVED_MODELS"

    @model_validator(mode="after")
    def distinct_models(self):
        identifiers = [m.model_id for m in self.models]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Model IDs must be unique")
        if any(value not in identifiers for value in self.routes.values()):
            raise ValueError("Route references an unknown model")
        return self

    @classmethod
    def load(cls, path: str | Path) -> AzaeronModelRegistry:
        try:
            return cls.model_validate_json(Path(path).read_bytes())
        except (OSError, ValueError):
            raise InferenceUnavailable("model_registry_invalid") from None

    def select(self, task: Task) -> ModelRecord:
        selected = next(
            (m for m in self.models if m.model_id == self.routes.get(task)), None
        )
        if (
            selected is None
            or selected.status != "APPROVED"
            or task not in selected.tasks
        ):
            raise InferenceUnavailable("no_approved_model")
        return selected


def verify_artifacts(model: ModelRecord, root: Path) -> None:
    """Verify the complete read-only bundle; unlisted files and symlinks fail closed."""
    root = root.resolve(strict=True)
    files = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise InferenceUnavailable("model_artifact_symlink")
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    if files != set(model.artifacts):
        raise InferenceUnavailable("model_artifact_inventory_mismatch")
    for name, digest in model.artifacts.items():
        with (root / name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != digest:
            raise InferenceUnavailable("model_artifact_integrity_failed")
