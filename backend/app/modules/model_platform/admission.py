"""Offline candidate admission. Legal attestations must come from the operator.

Admission is permission to experiment, never approval to serve customers. No
download path exists here. The complete copied bundle is checked before use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
from typing import Literal

from pydantic import Field, model_validator

from .policy import (
    Digest,
    FileRef,
    PolicyError,
    StrictModel,
    canonical,
    digest,
    local_file,
)


class Candidate(StrictModel):
    schema_version: Literal[1] = 1
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    repository: str = Field(min_length=3)
    revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    artifacts: dict[str, Digest] = Field(min_length=4)
    weights: list[str] = Field(min_length=1)
    tokenizer: list[str] = Field(min_length=1)
    license_file: str
    model_card: str
    license: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    parameters: int = Field(gt=0)
    context: int = Field(ge=32, le=2_000_000)
    languages: list[str] = Field(min_length=1)
    runtime_compatibility: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def inventory(self):
        required = {
            *self.weights,
            *self.tokenizer,
            self.license_file,
            self.model_card,
            "config.json",
        }
        if not required <= self.artifacts.keys() or any(
            not name.endswith(".safetensors") for name in self.weights
        ):
            raise ValueError(
                "Complete safe-tensor weights and tokenizer lineage required"
            )
        if {n for n in self.artifacts if n.endswith(".safetensors")} != set(
            self.weights
        ):
            raise ValueError("Every weight file must be declared")
        for name in self.artifacts:
            local_file(Path("."), name)
            if (
                Path(name).suffix.lower()
                not in {".json", ".safetensors", ".model", ".txt", ".md", ".tiktoken"}
                and name != "LICENSE"
            ):
                raise ValueError("Unsupported artifact type")
        return self


class CandidateReview(StrictModel):
    subject_sha256: Digest
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    reviewer: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "TEST_FIXTURE"]
    reviewed_at: str = Field(min_length=10)
    reference: str = Field(min_length=1)
    license: str = Field(min_length=1)
    commercial_use: Literal["PASS"]
    commercial_training: Literal["PASS"]
    redistribution_requirements: str = Field(min_length=1)
    attribution_requirements: str = Field(min_length=1)
    acceptable_use_restrictions: str = Field(min_length=1)
    technical_review: Literal["PASS"]
    strong_baseline: bool = False
    strong_baseline_evidence: str | None = None

    @model_validator(mode="after")
    def human_attestation(self):
        if self.purpose == "PRODUCTION" and self.reviewer_kind != "HUMAN":
            raise ValueError("Production review requires an accountable human reviewer")
        if self.strong_baseline and not self.strong_baseline_evidence:
            raise ValueError("A strong-baseline claim needs evidence")
        return self


def inventory_hash(artifacts: dict[str, str]) -> str:
    return hashlib.sha256(canonical(artifacts)).hexdigest()


def verify_bundle(candidate: Candidate, root: Path):
    files = set()
    for path in root.rglob("*"):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise PolicyError("candidate_special_file")
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    if files != candidate.artifacts.keys():
        raise PolicyError("candidate_inventory_mismatch")
    for name, expected in candidate.artifacts.items():
        path = FileRef(path=name, sha256=expected).verify(root)
        if name in candidate.weights:
            # Validate the bounded safe-tensor container before ML code is imported.
            with path.open("rb") as stream:
                header_length = int.from_bytes(stream.read(8), "little")
                if not 2 <= header_length <= min(16 * 1024**2, path.stat().st_size - 8):
                    raise PolicyError("invalid_safetensors_header")
                header = json.loads(stream.read(header_length))
            sizes = {
                "F64": 8,
                "F32": 4,
                "F16": 2,
                "BF16": 2,
                "I64": 8,
                "I32": 4,
                "I16": 2,
                "I8": 1,
                "U8": 1,
                "BOOL": 1,
            }
            intervals = []
            for key, value in header.items():
                if key == "__metadata__":
                    continue
                shape, offsets = value.get("shape", []), value.get("data_offsets", [])
                if (
                    value.get("dtype") not in sizes
                    or len(offsets) != 2
                    or any(type(v) is not int or v < 0 for v in [*shape, *offsets])
                ):
                    raise PolicyError("invalid_safetensors_layout")
                count = math.prod(shape)
                if (
                    count > candidate.parameters * 2
                    or offsets[1] - offsets[0] != count * sizes[value["dtype"]]
                ):
                    raise PolicyError("invalid_safetensors_shape")
                intervals.append(offsets)
            end = 0
            for start, stop in sorted(intervals):
                if start != end:
                    raise PolicyError("invalid_safetensors_offsets")
                end = stop
            if not intervals or end != path.stat().st_size - 8 - header_length:
                raise PolicyError("invalid_safetensors_payload")
        if name not in candidate.weights and path.stat().st_size > 64 * 1024**2:
            raise PolicyError("candidate_metadata_too_large")
        if path.suffix == ".json":
            value = json.loads(path.read_bytes())

            def inspect(item):
                if isinstance(item, dict):
                    if "auto_map" in item or item.get("trust_remote_code"):
                        raise PolicyError("candidate_remote_code_prohibited")
                    for child in item.values():
                        inspect(child)
                elif isinstance(item, list):
                    for child in item:
                        inspect(child)

            inspect(value)
    config = json.loads((root / "config.json").read_bytes())
    for names, bound in [
        (("num_hidden_layers", "n_layer"), 128),
        (("hidden_size", "n_embd"), 32768),
        (("num_attention_heads", "n_head"), 256),
        (("vocab_size",), 1_000_000),
    ]:
        value = next((config[key] for key in names if key in config), None)
        if type(value) is not int or not 0 < value <= bound:
            raise PolicyError("candidate_architecture_dimensions_invalid")
    if config.get("model_type") != candidate.architecture:
        raise PolicyError("candidate_architecture_mismatch")
    context = config.get("max_position_embeddings", config.get("n_positions"))
    if not isinstance(context, int) or candidate.context > context:
        raise PolicyError("candidate_context_mismatch")


def load_candidate(admitted: Path, *, smoke=False):
    candidate = Candidate.model_validate_json(
        (admitted / "candidate.json").read_bytes()
    )
    review = CandidateReview.model_validate_json(
        (admitted / "review.json").read_bytes()
    )
    record = json.loads((admitted / "admission.json").read_bytes())
    if record != {
        "status": "EXPERIMENTAL",
        "candidate_sha256": digest(admitted / "candidate.json"),
        "review_sha256": digest(admitted / "review.json"),
        "production_approved": False,
    }:
        raise PolicyError("admission_record_mismatch")
    if (
        review.subject_sha256 != digest(admitted / "candidate.json")
        or review.license != candidate.license
        or review.purpose != candidate.purpose
    ):
        raise PolicyError("candidate_review_binding_failed")
    if (candidate.purpose == "TEST_ONLY") != smoke:
        raise PolicyError("candidate_purpose_mismatch")
    verify_bundle(candidate, admitted / "bundle")
    return candidate, review


def admit(
    manifest: Path, review_file: Path, source: Path, registry: Path, *, smoke=False
):
    candidate = Candidate.model_validate_json(manifest.read_bytes())
    review = CandidateReview.model_validate_json(review_file.read_bytes())
    if (
        review.subject_sha256 != digest(manifest)
        or review.license != candidate.license
        or review.purpose != candidate.purpose
    ):
        raise PolicyError("candidate_review_binding_failed")
    if (candidate.purpose == "TEST_ONLY") != smoke:
        raise PolicyError("candidate_purpose_mismatch")
    verify_bundle(candidate, source)
    output = registry / candidate.candidate_id / digest(manifest)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, output / "bundle", symlinks=True)
    shutil.copyfile(manifest, output / "candidate.json")
    shutil.copyfile(review_file, output / "review.json")
    (output / "admission.json").write_bytes(
        canonical(
            {
                "status": "EXPERIMENTAL",
                "candidate_sha256": digest(manifest),
                "review_sha256": digest(review_file),
                "production_approved": False,
            }
        )
        + b"\n"
    )
    load_candidate(output, smoke=smoke)
    # Hash checks remain mandatory: filesystem permissions alone are not a trust boundary.
    for path in output.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["manifest", "review", "source", "registry"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(
        admit(args.manifest, args.review, args.source, args.registry, smoke=args.smoke)
    )


if __name__ == "__main__":
    main()
