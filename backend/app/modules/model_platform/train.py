"""Offline, deterministic reference training. No automatic data or model download."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import random
from uuid import uuid4

from pydantic import Field

from .policy import (
    DatasetManifest,
    Family,
    FileRef,
    PolicyError,
    StrictModel,
    canonical,
    digest,
)
from .datasets import read_native_dataset


class TrainConfig(StrictModel):
    family: Family
    dataset: FileRef
    seed: int = Field(ge=0, le=2**31 - 1)
    epochs: int = Field(ge=1, le=1000)
    batch_size: int = Field(ge=2, le=128)
    learning_rate: float = Field(gt=0, le=0.01, allow_inf_nan=False)
    width: int = Field(default=256, ge=16, le=4096)
    heads: int = Field(default=8, ge=1, le=32)
    layers: int = Field(default=4, ge=1, le=48)
    context: int = Field(default=1024, ge=32, le=32768)
    embedding_size: int = Field(default=128, ge=8, le=4096)
    device: str = Field(default="cpu", pattern=r"^(cpu|cuda|mps)$")


def train(config_file: Path, output: Path, *, smoke=False):
    config = TrainConfig.model_validate_json(config_file.read_bytes())
    manifest_path = config.dataset.verify(config_file.parent)
    # Rights and split validation happens BEFORE importing ML libraries or allocating compute.
    manifest, rows = read_native_dataset(manifest_path, config.family, smoke=smoke)
    if smoke and manifest.purpose != "TEST_ONLY":
        raise PolicyError("smoke_requires_explicit_test_only_dataset")
    import torch
    from safetensors.torch import save_file
    from .network import Architecture, FamilyNetwork, TOKENIZER, training_loss

    if len(rows["train"]) < config.batch_size:
        raise PolicyError("insufficient_training_rows")
    random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    architecture = Architecture(
        **{
            k: getattr(config, k)
            for k in ["family", "width", "heads", "layers", "context", "embedding_size"]
        }
    )
    model = FamilyNetwork(architecture).to(config.device)
    # Validate every row's shape and label before beginning training.
    for split_rows in rows.values():
        with torch.no_grad():
            for offset in range(0, len(split_rows), config.batch_size):
                batch = split_rows[offset : offset + config.batch_size]
                if config.family == "embed" and len(batch) == 1:
                    batch = split_rows[-2:]
                training_loss(model, batch, config.device)
    output.mkdir(parents=True, exist_ok=False)
    checkpoint = output / "checkpoint.safetensors"
    save_file(
        {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
        str(checkpoint),
    )
    initialization = digest(checkpoint)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=config.learning_rate, weight_decay=0.01
    )
    steps, losses = 0, []
    order = list(rows["train"])
    model.train()
    for _ in range(config.epochs):
        random.shuffle(order)
        for offset in range(0, len(order), config.batch_size):
            batch = order[offset : offset + config.batch_size]
            if config.family == "embed" and len(batch) == 1:
                batch = order[-2:]
            optimizer.zero_grad(set_to_none=True)
            loss = training_loss(model, batch, config.device)
            if not torch.isfinite(loss):
                raise PolicyError("nonfinite_training_loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), 1.0, error_if_nonfinite=True
            )
            optimizer.step()
            steps += 1
            losses.append(float(loss.detach().cpu()))
    save_file(
        {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
        str(checkpoint),
    )
    checkpoint_hash = digest(checkpoint)
    if initialization == checkpoint_hash:
        raise PolicyError("training_did_not_change_checkpoint")
    run_id = str(uuid4())
    code_hash = hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
    ).hexdigest()
    training = {
        "schema_version": 1,
        "run_id": run_id,
        "classification": "AZAERON_NATIVE",
        "family": config.family,
        "tokenizer_sha256": hashlib.sha256(canonical(TOKENIZER) + b"\n").hexdigest(),
        "purpose": manifest.purpose,
        "status": "TRAINED_NOT_APPROVED",
        "checkpoint_sha256": checkpoint_hash,
        "initialization_sha256": initialization,
        "dataset_manifest_sha256": config.dataset.sha256,
        "dataset_splits": {k: v.sha256 for k, v in manifest.splits.items()},
        "dataset_reviews": (
            {k: v.sha256 for k, v in manifest.reviews.items()}
            if isinstance(manifest, DatasetManifest)
            else {"manifest": manifest.review.sha256}
        ),
        "steps": steps,
        "examples": len(order),
        "code_sha256": code_hash,
        "configuration": config.model_dump(mode="json"),
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "safetensors": importlib.metadata.version("safetensors"),
            "device": config.device,
        },
        "training_loss_first": losses[0],
        "training_loss_last": losses[-1],
        "quality_evaluation": "NOT_RUN",
        "production_approval": "NOT_APPROVED",
    }
    for name, value in {
        "architecture.json": asdict(architecture),
        "tokenizer.json": TOKENIZER,
        "training-manifest.json": training,
    }.items():
        (output / name).write_bytes(canonical(value) + b"\n")
    (output / "MODEL_CARD.md").write_text(
        f"# Azaeron-Verity-{config.family.title()}\n\n"
        f"Classification: AZAERON_NATIVE. Purpose: {manifest.purpose}.\n\n"
        f"Run: {run_id}. Checkpoint SHA-256: {checkpoint_hash}.\n\n"
        "Status: NOT APPROVED. Original byte-token Transformer trained from random initialization. "
        "Training loss is not a quality benchmark. No production capabilities, multilingual coverage, "
        "calibration, factual accuracy or comparative quality are established by this run. "
        "See training-manifest.json for configuration, dataset/review hashes, environment and code lineage. "
        "Independent evaluation, security/runtime evidence and release approval are required.\n"
    )
    (output / "lineage.json").write_bytes(
        canonical(
            {
                "classification": "AZAERON_NATIVE",
                "family": config.family,
                "run_id": run_id,
                "training_steps": steps,
                "checkpoint_sha256": checkpoint_hash,
                "initialization_sha256": initialization,
                "dataset_manifest_sha256": config.dataset.sha256,
                "training_manifest_sha256": digest(output / "training-manifest.json"),
                "model_card_sha256": digest(output / "MODEL_CARD.md"),
                "code_sha256": code_hash,
                "purpose": manifest.purpose,
            }
        )
        + b"\n"
    )
    return training


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--smoke", action="store_true", help="TEST_ONLY training; never promotable"
    )
    args = parser.parse_args()
    result = train(args.config, args.output, smoke=args.smoke)
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "run_id",
                    "family",
                    "purpose",
                    "checkpoint_sha256",
                    "steps",
                    "production_approval",
                ]
            }
        )
    )


if __name__ == "__main__":
    main()
