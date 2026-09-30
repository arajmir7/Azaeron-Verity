"""Offline full/LoRA/QLoRA supervised training of admitted writer candidates.

No download, approval, preference optimization or customer-data ingestion occurs.
The output is an experimental derivative; a training loss cannot approve it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import math
import os
from pathlib import Path
import random
import time
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from .admission import inventory_hash, load_candidate
from .datasets import read_dataset
from .hardware import enforce, plan, profile
from .policy import FileRef, PolicyError, StrictModel, canonical, digest


class DerivativeConfig(StrictModel):
    candidate: FileRef
    dataset: FileRef
    family: Literal["writer"] = "writer"
    method: Literal["full", "lora", "qlora"]
    device: Literal["cpu", "mps", "cuda"]
    precision: Literal["float32", "float16", "bfloat16"]
    seed: int = Field(ge=0, le=2**31 - 1)
    epochs: int = Field(ge=1, le=100)
    sequence_length: int = Field(ge=32, le=32768)
    microbatch: int = Field(ge=1, le=64)
    gradient_accumulation: int = Field(ge=1, le=1024)
    gradient_checkpointing: bool = True
    learning_rate: float = Field(gt=0, le=0.01, allow_inf_nan=False)
    weight_decay: float = Field(default=0.01, ge=0, le=1, allow_inf_nan=False)
    warmup_steps: int = Field(default=0, ge=0)
    lora_rank: int = Field(default=16, ge=1, le=256)
    lora_alpha: int = Field(default=32, ge=1, le=512)
    lora_dropout: float = Field(default=0, ge=0, lt=1, allow_inf_nan=False)
    target_modules: list[str] = Field(default_factory=lambda: ["q_proj", "v_proj"])
    merge_adapter: bool = False

    @model_validator(mode="after")
    def compatible(self):
        if self.method == "qlora" and (
            self.device != "cuda" or self.precision == "float32" or self.merge_adapter
        ):
            raise ValueError(
                "QLoRA requires CUDA, reduced precision and separate audited merging"
            )
        if self.device == "cpu" and self.precision != "float32":
            raise ValueError("Reference CPU training requires float32")
        if not self.target_modules or any(
            not name.replace("_", "").isalnum() for name in self.target_modules
        ):
            raise ValueError("Explicit literal adapter target modules required")
        return self


def offline():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"


def artifact_hash(root: Path):
    return inventory_hash(
        {
            str(p.relative_to(root)): digest(p)
            for p in sorted(root.rglob("*.safetensors"))
        }
    )


def trainable_hash(model):
    import torch

    value = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            value.update(name.encode())
            for chunk in parameter.detach().reshape(-1).split(1024 * 1024):
                value.update(
                    chunk.cpu().contiguous().view(torch.uint8).numpy().tobytes()
                )
    return value.hexdigest()


def train(config_file: Path, output: Path, *, smoke=False):
    offline()
    config = DerivativeConfig.model_validate_json(config_file.read_bytes())
    admitted = config.candidate.verify(config_file.parent).parent
    if digest(admitted / "candidate.json") != config.candidate.sha256:
        raise PolicyError("candidate_reference_mismatch")
    candidate, review = load_candidate(admitted, smoke=smoke)
    dataset_file = config.dataset.verify(config_file.parent)
    dataset, rows = read_dataset(dataset_file, config.family, smoke=smoke)
    if config.sequence_length > candidate.context:
        raise PolicyError("training_context_exceeds_admission")
    if output.exists():
        raise PolicyError("checkpoint_output_already_exists")

    import torch
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    root = admitted / "bundle"
    architecture = AutoConfig.from_pretrained(
        root,
        revision=candidate.revision,
        local_files_only=True,
        trust_remote_code=False,
    )
    with init_empty_weights(include_buffers=True):
        empty = AutoModelForCausalLM.from_config(architecture, trust_remote_code=False)
        empty.tie_weights()
        parameters = sum(p.numel() for p in empty.parameters())
        adapter_config = LoraConfig(
            r=config.lora_rank,
            lora_alpha=config.lora_alpha,
            target_modules=config.target_modules,
            lora_dropout=config.lora_dropout,
            bias="none",
            task_type="CAUSAL_LM",
        )
        if config.method != "full":
            empty = get_peft_model(empty, adapter_config)
        trainable = sum(p.numel() for p in empty.parameters() if p.requires_grad)
    del empty
    if parameters != candidate.parameters:
        raise PolicyError("candidate_parameter_count_mismatch")
    tokenizer = AutoTokenizer.from_pretrained(
        root,
        revision=candidate.revision,
        local_files_only=True,
        trust_remote_code=False,
        use_fast=True,
    )
    if tokenizer.eos_token_id is None:
        raise PolicyError("tokenizer_eos_required")
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    def encode(row):
        # Explicit plain SFT format; never execute a bundle-supplied chat template.
        prompt = tokenizer.encode(
            "Instruction:\n" + row["input"] + "\nResponse:\n", add_special_tokens=False
        )
        target = tokenizer.encode(row["target"], add_special_tokens=False) + [
            tokenizer.eos_token_id
        ]
        if not prompt or len(prompt) + len(target) > config.sequence_length:
            raise PolicyError("training_example_overflow_no_truncation")
        return prompt + target, [-100] * len(prompt) + target

    encoded = {
        split: [encode(row) for row in values]
        for split, values in rows.items()
        if split in {"train", "validation"}
    }
    tokens = sum(len(value[0]) for value in encoded["train"]) * config.epochs
    hardware = profile()
    memory_plan = plan(
        parameters,
        trainable,
        method=config.method,
        precision=(
            "float32"
            if config.precision == "float16" and config.method != "qlora"
            else config.precision
        ),
        layers=architecture.num_hidden_layers,
        width=architecture.hidden_size,
        heads=architecture.num_attention_heads,
        vocab=architecture.vocab_size,
        sequence=config.sequence_length,
        microbatch=config.microbatch,
        accumulation=config.gradient_accumulation,
        checkpointing=config.gradient_checkpointing,
        tokens=tokens,
    )
    enforce(memory_plan, hardware, config.device, output_bytes=parameters * 8)
    dtype = getattr(torch, config.precision)
    weight_dtype = (
        torch.float32
        if config.precision == "float16" and config.method != "qlora"
        else dtype
    )
    kwargs = {
        "local_files_only": True,
        "trust_remote_code": False,
        "use_safetensors": True,
        "dtype": weight_dtype,
        "attn_implementation": "eager",
    }
    if config.method == "qlora":
        from transformers import BitsAndBytesConfig
        from peft import prepare_model_for_kbit_training

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        )
        kwargs["device_map"] = {"": 0}
    started = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        root, revision=candidate.revision, **kwargs
    )
    if config.method == "qlora":
        model = prepare_model_for_kbit_training(
            model, use_gradient_checkpointing=config.gradient_checkpointing
        )
    else:
        model.to(config.device)
    if config.method != "full":
        model = get_peft_model(model, adapter_config)
    initialization = trainable_hash(model)
    model.config.use_cache = False
    if config.gradient_checkpointing:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False}
        )
    if config.device == "cuda":
        torch.cuda.reset_peak_memory_stats()
    output.mkdir(parents=True, exist_ok=False)
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    batches = math.ceil(len(encoded["train"]) / config.microbatch)
    total_steps = math.ceil(batches / config.gradient_accumulation) * config.epochs
    if config.warmup_steps >= total_steps:
        raise PolicyError("warmup_must_be_shorter_than_training")

    def schedule(step):
        if step < config.warmup_steps:
            return (step + 1) / max(1, config.warmup_steps)
        return max(0, (total_steps - step) / max(1, total_steps - config.warmup_steps))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, schedule)
    scaler = torch.amp.GradScaler(
        "cuda", enabled=config.device == "cuda" and config.precision == "float16"
    )

    def batch(values):
        length = max(len(ids) for ids, _ in values)
        return {
            "input_ids": torch.tensor(
                [
                    ids + [tokenizer.pad_token_id] * (length - len(ids))
                    for ids, _ in values
                ],
                device=config.device,
            ),
            "attention_mask": torch.tensor(
                [[1] * len(ids) + [0] * (length - len(ids)) for ids, _ in values],
                device=config.device,
            ),
            "labels": torch.tensor(
                [labels + [-100] * (length - len(labels)) for _, labels in values],
                device=config.device,
            ),
        }

    losses, steps = [], 0
    for _ in range(config.epochs):
        model.train()
        order = list(encoded["train"])
        random.shuffle(order)
        mini = [
            order[i : i + config.microbatch]
            for i in range(0, len(order), config.microbatch)
        ]
        for offset in range(0, len(mini), config.gradient_accumulation):
            accumulation = mini[offset : offset + config.gradient_accumulation]
            optimizer.zero_grad(set_to_none=True)
            for values in accumulation:
                with torch.autocast(
                    device_type=config.device,
                    dtype=dtype,
                    enabled=config.device == "cuda" and config.precision != "float32",
                ):
                    loss = model(**batch(values)).loss
                if not torch.isfinite(loss):
                    raise PolicyError("nonfinite_derivative_loss")
                losses.append(float(loss.detach().cpu()))
                scaler.scale(loss / len(accumulation)).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), 1.0, error_if_nonfinite=True
            )
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            steps += 1
    model.eval()
    trained = trainable_hash(model)
    if trained == initialization:
        raise PolicyError("training_did_not_change_parameters")
    with torch.inference_mode():
        validation = [
            float(model(**batch([row])).loss.cpu()) for row in encoded["validation"]
        ]
    if not all(math.isfinite(value) for value in validation):
        raise PolicyError("nonfinite_validation_loss")
    directory = output / ("model" if config.method == "full" else "adapter")
    model.save_pretrained(directory, safe_serialization=True)
    tokenizer.save_pretrained(output / "tokenizer")
    adapter_hash = artifact_hash(directory) if config.method != "full" else None
    merged_hash = None
    if config.merge_adapter and config.method == "lora":
        model = model.merge_and_unload(safe_merge=True)
        model.save_pretrained(output / "model", safe_serialization=True)
        merged_hash = artifact_hash(output / "model")
    checkpoint_hash = artifact_hash(directory)
    base_weights = inventory_hash(
        {name: candidate.artifacts[name] for name in candidate.weights}
    )
    if config.method == "full" and checkpoint_hash == base_weights:
        raise PolicyError("training_did_not_change_checkpoint")
    # Detect replacement of source artifacts during a long run before signing the output record.
    load_candidate(admitted, smoke=smoke)
    config.dataset.verify(config_file.parent)
    source = Path(__file__).parent
    code_hash = hashlib.sha256(
        canonical({p.name: digest(p) for p in sorted(source.glob("*.py"))})
    ).hexdigest()
    training = {
        "schema_version": 2,
        "run_id": str(uuid4()),
        "classification": "AZAERON_DERIVATIVE",
        "family": "writer",
        "purpose": candidate.purpose,
        "status": "EXPERIMENTAL",
        "production_approval": "NOT_APPROVED",
        "base_repository": candidate.repository,
        "base_revision": candidate.revision,
        "base_weights_sha256": base_weights,
        "base_artifacts": candidate.artifacts,
        "candidate_manifest_sha256": config.candidate.sha256,
        "base_review_sha256": digest(admitted / "review.json"),
        "checkpoint_sha256": checkpoint_hash,
        "adapter_sha256": adapter_hash,
        "trainable_initialization_sha256": initialization,
        "trained_parameters_sha256": trained,
        "merged_checkpoint_sha256": merged_hash,
        "dataset_manifest_sha256": config.dataset.sha256,
        "dataset_splits": {key: ref.sha256 for key, ref in dataset.splits.items()},
        "tokenizer_sha256": inventory_hash(
            {name: candidate.artifacts[name] for name in candidate.tokenizer}
        ),
        "code_sha256": code_hash,
        "configuration": config.model_dump(mode="json"),
        "optimizer": "AdamW",
        "scheduler": "linear_with_warmup",
        "steps": steps,
        "tokens_processed": tokens,
        "wall_seconds": time.perf_counter() - started,
        "hardware": hardware,
        "memory_plan": memory_plan,
        "cuda_peak_allocated_bytes": (
            torch.cuda.max_memory_allocated() if config.device == "cuda" else None
        ),
        "software": {
            name: importlib.metadata.version(name)
            for name in ["torch", "transformers", "peft", "accelerate", "safetensors"]
        },
        "metrics": {
            "training_loss_first": losses[0],
            "training_loss_last": losses[-1],
            "validation_loss": sum(validation) / len(validation),
        },
        "payload_artifacts": {
            str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
        "quality_evaluation": "NOT_RUN",
        "human_review": "NOT_FOUND",
        "reviewer": review.reviewer,
    }
    (output / "training-manifest.json").write_bytes(canonical(training) + b"\n")
    (output / "MODEL_CARD.md").write_text(
        f"# Azaeron-Verity-Writer experimental derivative\n\nPurpose: {candidate.purpose}. NOT APPROVED.\n\n"
        f"Base: {candidate.repository}@{candidate.revision}. Method: {config.method}.\n\n"
        "Training/validation loss does not establish product quality. No human review, baseline victory, production runtime or commercial release is claimed. "
        "See the training manifest for original tokenizer/base, dataset, reviewer, code, optimizer and artifact hashes. "
        "Adapter-only exports require their exact admitted base. Production export and release remain separately gated.\n"
    )
    inventory = {
        str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    (output / "artifacts.json").write_bytes(canonical(inventory) + b"\n")
    for path in output.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)
    return training


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = train(args.config, args.output, smoke=args.smoke)
    print(
        canonical(
            {
                key: result[key]
                for key in [
                    "status",
                    "purpose",
                    "steps",
                    "checkpoint_sha256",
                    "production_approval",
                ]
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
