"""Versioned, rights-reviewed five-split datasets for the candidate program."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Literal

from pydantic import Field

from .policy import Digest, Family, FileRef, PolicyError, StrictModel, canonical, digest

SPLITS = {"train", "validation", "calibration", "test", "ood"}
WRITER_TASKS = {
    "natural_prose",
    "academic",
    "professional",
    "explanation",
    "summary",
    "rewrite",
    "style_transfer",
    "document_qa",
    "instruction",
    "fact_preservation",
    "citation",
    "uncertainty",
    "tool_selection",
}
MEANING_SLICES = {
    "name",
    "date",
    "number",
    "money",
    "percentage",
    "citation",
    "doi",
    "url",
    "quote",
    "legal",
    "technical",
    "math",
    "code",
    "negation",
    "comparative",
    "causal",
    "uncertainty",
    "qualifier",
}


class Dataset(StrictModel):
    schema_version: Literal[2] = 2
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    version: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$")
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    source: str = Field(min_length=1)
    license: str = Field(min_length=1)
    commercial_training_permission: Literal["GRANTED"]
    redistribution_permission: Literal["GRANTED", "PROHIBITED"]
    provenance: str = Field(min_length=1)
    acquisition_method: str = Field(min_length=1)
    copyright_review: Literal["PASS"]
    pii_review: Literal["PASS"]
    language: list[str] = Field(min_length=1)
    domain: list[str] = Field(min_length=1)
    quality_tier: Literal["CURATED", "GOLD", "TEST_FIXTURE"]
    allowed_model_families: list[Family] = Field(min_length=1)
    contains_customer_content: Literal[False]
    splits: dict[str, FileRef]
    review: FileRef


class DatasetReview(StrictModel):
    subject_sha256: Digest
    reviewer: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "TEST_FIXTURE"]
    reviewed_at: str = Field(min_length=10)
    evidence_reference: str = Field(min_length=1)
    rights: Literal["PASS"]
    provenance: Literal["PASS"]
    copyright: Literal["PASS"]
    pii: Literal["PASS"]


class Example(StrictModel):
    id: str = Field(min_length=1, max_length=256)
    group: str = Field(min_length=1, max_length=256)
    input: str = Field(min_length=1, max_length=200_000)
    target: str = Field(min_length=1, max_length=200_000)
    language: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    task: str = Field(min_length=1)
    slices: list[str]
    generator_family: str | None = None


def review_subject(manifest: Dataset) -> str:
    # The attestation covers every metadata field and split hash, without a circular hash.
    return hashlib.sha256(
        canonical(manifest.model_dump(mode="json", exclude={"review"}))
    ).hexdigest()


def read_dataset(manifest_file: Path, family: Family, *, smoke=False):
    manifest = Dataset.model_validate_json(manifest_file.read_bytes())
    if (
        manifest.purpose == "TEST_ONLY"
    ) != smoke or family not in manifest.allowed_model_families:
        raise PolicyError("dataset_purpose_or_family_mismatch")
    if set(manifest.splits) != SPLITS:
        raise PolicyError("five_independent_splits_required")
    review = DatasetReview.model_validate_json(
        manifest.review.verify(manifest_file.parent).read_bytes()
    )
    if review.subject_sha256 != review_subject(manifest):
        raise PolicyError("dataset_review_binding_failed")
    if not smoke and (
        review.reviewer_kind != "HUMAN" or manifest.quality_tier == "TEST_FIXTURE"
    ):
        raise PolicyError("human_dataset_review_required")
    rows, ids, inputs, groups, generators = {}, set(), set(), set(), set()
    for split, ref in manifest.splits.items():
        path = ref.verify(manifest_file.parent)
        if path.stat().st_size > 256 * 1024**2:
            raise PolicyError("dataset_shard_too_large")
        values, split_groups, split_generators = [], set(), set()
        with path.open() as stream:
            for line in stream:
                row = Example.model_validate_json(line)
                key = hashlib.sha256(
                    " ".join(row.input.casefold().split()).encode()
                ).hexdigest()
                if row.id in ids or key in inputs or row.group in groups:
                    raise PolicyError("duplicate_or_source_group_leakage")
                if (
                    row.language not in manifest.language
                    or row.domain not in manifest.domain
                ):
                    raise PolicyError("dataset_region_not_reviewed")
                if family == "writer" and row.task not in WRITER_TASKS:
                    raise PolicyError("unreviewed_writer_task")
                if family == "detector":
                    if row.target not in {"HUMAN", "AI", "MIXED"}:
                        raise PolicyError("invalid_detector_class")
                    if row.target != "HUMAN" and not row.generator_family:
                        raise PolicyError("generator_lineage_missing")
                    if row.generator_family in generators:
                        raise PolicyError("generator_family_split_leakage")
                    if row.generator_family:
                        split_generators.add(row.generator_family)
                ids.add(row.id)
                inputs.add(key)
                split_groups.add(row.group)
                values.append(row.model_dump())
        if not values:
            raise PolicyError("empty_dataset_split")
        groups.update(split_groups)
        generators.update(split_generators)
        rows[split] = values
    return manifest, rows


def register(manifest_file: Path, registry: Path, *, smoke=False):
    manifest = Dataset.model_validate_json(manifest_file.read_bytes())
    for family in manifest.allowed_model_families:
        read_dataset(manifest_file, family, smoke=smoke)
    output = registry / manifest.dataset_id / manifest.version
    output.mkdir(parents=True, exist_ok=False)
    for ref in [*manifest.splits.values(), manifest.review]:
        source = ref.verify(manifest_file.parent)
        destination = output / ref.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    shutil.copyfile(manifest_file, output / "dataset.json")
    for family in manifest.allowed_model_families:
        read_dataset(output / "dataset.json", family, smoke=smoke)
    (output / "registration.json").write_bytes(
        canonical(
            {
                "dataset_sha256": digest(output / "dataset.json"),
                "purpose": manifest.purpose,
            }
        )
        + b"\n"
    )
    for path in output.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(register(args.manifest, args.registry, smoke=args.smoke))


if __name__ == "__main__":
    main()
