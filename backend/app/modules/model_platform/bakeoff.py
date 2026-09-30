"""Same-policy offline Writer bake-off; no automatic winner or release approval."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import statistics
import threading
import time
from typing import Literal

from pydantic import Field

from .admission import load_candidate
from .datasets import read_dataset
from .derivative import offline
from .hardware import profile
from .policy import FileRef, PolicyError, StrictModel, canonical, digest


class Entrant(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    role: Literal["BASELINE", "CANDIDATE"]
    admission: FileRef
    training_manifest: FileRef | None = None


class Benchmark(StrictModel):
    dataset: FileRef
    entrants: list[Entrant] = Field(min_length=3)
    device: Literal["cpu", "cuda", "mps"]
    max_input_tokens: int = Field(ge=16, le=32768)
    max_output_tokens: int = Field(ge=1, le=4096)
    seed: int = Field(ge=0, le=2**31 - 1)
    decoding: Literal["GREEDY"] = "GREEDY"
    prompt_format: Literal["instruction_response_v1"] = "instruction_response_v1"


def run(config_file: Path, output: Path, *, smoke=False):
    offline()
    config = Benchmark.model_validate_json(config_file.read_bytes())
    if output.exists():
        raise PolicyError("benchmark_output_already_exists")
    dataset_file = config.dataset.verify(config_file.parent)
    dataset, splits = read_dataset(dataset_file, "writer", smoke=smoke)
    rows = splits["test"]
    if len({item.id for item in config.entrants}) != len(config.entrants):
        raise PolicyError("duplicate_benchmark_entrant")
    admitted, baseline_hashes = {}, set()
    for entrant in config.entrants:
        path = entrant.admission.verify(config_file.parent).parent
        if digest(path / "candidate.json") != entrant.admission.sha256:
            raise PolicyError("candidate_reference_mismatch")
        candidate, review = load_candidate(path, smoke=smoke)
        if entrant.role == "BASELINE":
            if entrant.training_manifest is not None or not review.strong_baseline:
                raise PolicyError("approved_strong_baseline_required")
            baseline_hashes.add(
                tuple(sorted(candidate.artifacts[name] for name in candidate.weights))
            )
        if config.max_input_tokens + config.max_output_tokens > candidate.context:
            raise PolicyError("benchmark_context_exceeds_candidate")
        admitted[entrant.id] = (path, candidate)
    if len(baseline_hashes) < 2 or not any(
        item.role == "CANDIDATE" for item in config.entrants
    ):
        raise PolicyError("two_distinct_approved_baselines_and_candidate_required")
    import psutil
    import torch
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    hardware = profile()
    if config.device == "cuda" and not hardware["cuda"]:
        raise PolicyError("cuda_gpu_not_available")
    if config.device == "mps" and not hardware["mps_available"]:
        raise PolicyError("mps_not_available")
    # Bound model loading before allocation. CUDA/MPS production sizing requires
    # a separate reviewed runtime plan; this reference uses full precision.
    largest = max(value[1].parameters for value in admitted.values())
    if largest * 8 + 2 * 1024**3 > min(
        hardware["memory_available_bytes"], hardware["memory_total_bytes"] * 0.6
    ):
        raise PolicyError("insufficient_safe_benchmark_memory")
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_bytes(
        canonical(config.model_dump(mode="json")) + b"\n"
    )
    (output / "hardware.json").write_bytes(canonical(hardware) + b"\n")
    results = []
    order = sorted(
        config.entrants,
        key=lambda item: hashlib.sha256(f"{config.seed}:{item.id}".encode()).digest(),
    )
    torch.set_num_threads(1)
    torch.manual_seed(config.seed)
    for entrant in order:
        path, candidate = admitted[entrant.id]
        bundle = path / "bundle"
        architecture = AutoConfig.from_pretrained(
            bundle,
            revision=candidate.revision,
            local_files_only=True,
            trust_remote_code=False,
        )
        with init_empty_weights(include_buffers=True):
            empty = AutoModelForCausalLM.from_config(
                architecture, trust_remote_code=False
            )
            empty.tie_weights()
            parameters = sum(p.numel() for p in empty.parameters())
        del empty
        if parameters != candidate.parameters:
            raise PolicyError("benchmark_parameter_mismatch")
        tokenizer = AutoTokenizer.from_pretrained(
            bundle,
            revision=candidate.revision,
            local_files_only=True,
            trust_remote_code=False,
        )
        if tokenizer.eos_token_id is None:
            raise PolicyError("tokenizer_eos_required")
        tokens = []
        for row in rows:
            ids = tokenizer.encode(
                "Instruction:\n" + row["input"] + "\nResponse:\n",
                add_special_tokens=False,
            )
            if not ids or len(ids) > config.max_input_tokens:
                raise PolicyError("benchmark_input_overflow_no_truncation")
            tokens.append(ids)
        model = AutoModelForCausalLM.from_pretrained(
            bundle,
            revision=candidate.revision,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            dtype=torch.float32,
        ).to(config.device)
        checkpoint = entrant.admission.sha256
        if entrant.training_manifest:
            manifest_file = entrant.training_manifest.verify(config_file.parent)
            training = json.loads(manifest_file.read_bytes())
            inventory = json.loads(
                (manifest_file.parent / "artifacts.json").read_bytes()
            )
            if (
                inventory.get("training-manifest.json")
                != entrant.training_manifest.sha256
                or training.get("candidate_manifest_sha256") != entrant.admission.sha256
                or training.get("purpose") != dataset.purpose
            ):
                raise PolicyError("benchmark_derivative_lineage_mismatch")
            actual = {
                str(p.relative_to(manifest_file.parent))
                for p in manifest_file.parent.rglob("*")
                if p.is_file()
            }
            if actual != {*inventory, "artifacts.json"}:
                raise PolicyError("derivative_inventory_mismatch")
            payload = {
                name: value
                for name, value in inventory.items()
                if name not in {"training-manifest.json", "MODEL_CARD.md"}
            }
            if not payload or payload != training.get("payload_artifacts"):
                raise PolicyError("derivative_payload_not_bound_to_training")
            for name, expected in inventory.items():
                FileRef(path=name, sha256=expected).verify(manifest_file.parent)
            checkpoint = training["checkpoint_sha256"]
            if training["configuration"]["method"] == "full":
                del model
                gc.collect()
                model = AutoModelForCausalLM.from_pretrained(
                    manifest_file.parent / "model",
                    revision=checkpoint,
                    local_files_only=True,
                    trust_remote_code=False,
                    use_safetensors=True,
                    dtype=torch.float32,
                ).to(config.device)
            else:
                from peft import PeftModel

                model = PeftModel.from_pretrained(
                    model,
                    manifest_file.parent / "adapter",
                    local_files_only=True,
                    is_trainable=False,
                )
        if sum(p.numel() for p in model.parameters()) > candidate.parameters * 1.2:
            raise PolicyError("benchmark_parameter_mismatch")
        model.eval()
        process = psutil.Process()
        peak = [process.memory_info().rss]
        stop = threading.Event()

        def sample():
            while not stop.wait(0.02):
                peak[0] = max(peak[0], process.memory_info().rss)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        if config.device == "cuda":
            torch.cuda.reset_peak_memory_stats()

        def synchronize():
            if config.device == "cuda":
                torch.cuda.synchronize()
            elif config.device == "mps":
                torch.mps.synchronize()

        measured = []
        try:
            for row, ids in zip(rows, tokens, strict=True):
                tensor = torch.tensor([ids], device=config.device)
                past, generated, first = None, [], None
                synchronize()
                started = time.perf_counter()
                try:
                    with torch.inference_mode():
                        for _ in range(config.max_output_tokens):
                            values = model(
                                input_ids=tensor, past_key_values=past, use_cache=True
                            )
                            logits = values.logits[:, -1]
                            if not torch.isfinite(logits).all():
                                raise PolicyError("nonfinite_benchmark_logits")
                            next_id = int(logits.argmax(-1).item())
                            synchronize()
                            if first is None:
                                first = time.perf_counter() - started
                            generated.append(next_id)
                            if next_id == tokenizer.eos_token_id:
                                break
                            tensor = torch.tensor([[next_id]], device=config.device)
                            past = values.past_key_values
                    text = tokenizer.decode(generated, skip_special_tokens=True)
                    if len(text.encode()) > 128 * 1024:
                        raise PolicyError("benchmark_output_too_large")
                    measured.append(
                        {
                            "id": row["id"],
                            "domain": row["domain"],
                            "task": row["task"],
                            "slices": row["slices"],
                            "input_tokens": len(ids),
                            "output_tokens": len(generated),
                            "ttft_seconds": first,
                            "seconds": time.perf_counter() - started,
                            "status": "EXECUTED",
                            "candidate_sha256": hashlib.sha256(
                                text.encode()
                            ).hexdigest(),
                            "output": text,
                            "exact_reference_match_debug_only": text == row["target"],
                        }
                    )
                except (PolicyError, RuntimeError):
                    measured.append(
                        {
                            "id": row["id"],
                            "status": "FAILED",
                            "seconds": time.perf_counter() - started,
                        }
                    )
        finally:
            stop.set()
            sampler.join(timeout=1)
        succeeded = [row for row in measured if row["status"] == "EXECUTED"]
        duration = sum(row["seconds"] for row in measured)
        result = {
            "entrant": entrant.model_dump(mode="json"),
            "checkpoint_sha256": checkpoint,
            "dataset_manifest_sha256": config.dataset.sha256,
            "test_split_sha256": dataset.splits["test"].sha256,
            "purpose": dataset.purpose,
            "status": "EXPERIMENTAL",
            "production_approved": False,
            "quality": "BLOCKED_HUMAN_AND_INDEPENDENT_REVIEW",
            "human_review": "NOT_FOUND",
            "examples": measured,
            "failure_rate": 1 - len(succeeded) / len(measured),
            "latency_seconds_p50": (
                statistics.median(row["seconds"] for row in succeeded)
                if succeeded
                else None
            ),
            "ttft_seconds_p50": (
                statistics.median(row["ttft_seconds"] for row in succeeded)
                if succeeded
                else None
            ),
            "requests_per_second": len(succeeded) / duration,
            "tokens_per_second": sum(row["output_tokens"] for row in succeeded)
            / duration,
            "peak_process_rss_bytes": peak[0],
            "rss_sampling_interval_ms": 20,
            "cuda_peak_allocated_bytes": (
                torch.cuda.max_memory_allocated() if config.device == "cuda" else None
            ),
            "context_scaling": [
                {
                    "input_tokens": row["input_tokens"],
                    "ttft_seconds": row["ttft_seconds"],
                }
                for row in succeeded
            ],
            "runtime_scope": "Reference serial offline runtime; not production batching or load certification",
        }
        (output / (entrant.id + ".json")).write_bytes(canonical(result) + b"\n")
        results.append(
            {"id": entrant.id, "sha256": digest(output / (entrant.id + ".json"))}
        )
        del model
        gc.collect()
        if config.device == "cuda":
            torch.cuda.empty_cache()
        load_candidate(path, smoke=smoke)
    report = {
        "status": "BLOCKED",
        "purpose": dataset.purpose,
        "protocol_sha256": digest(config_file),
        "results": results,
        "winner": None,
        "blockers": [
            "Independent blinded human reviews, task quality adjudication, release security and production runtime evidence required"
        ],
    }
    (output / "decision.json").write_bytes(canonical(report) + b"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(canonical(run(args.config, args.output, smoke=args.smoke)).decode())


if __name__ == "__main__":
    main()
