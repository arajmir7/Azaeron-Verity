"""Offline, owner-gated MLX LoRA training for an admitted local Writer base.

This produces an experimental adapter. MLX-LM 0.32.0 can restart from adapter
weights, but does not restore optimizer, RNG or iteration state; this module
never describes such a restart as an exact resume.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import select
import shutil
import signal
import tempfile
import time
from typing import Literal

from pydantic import Field, model_validator

from .admission import CandidateReview, load_candidate
from .datasets import Dataset, DatasetReview, read_dataset
from .policy import FileRef, PolicyError, StrictModel, canonical, digest

MLX_LM_VERSION = "0.32.0"
CONTROLLED_QWEN_MANIFEST = (
    "19fe23dd9302d4cb73e8cf9866f42b6a73399c9ec9398c28a340cda1acf1b8ce"
)
CONTROLLED_QWEN_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
CONTROLLED_QWEN_WEIGHT = (
    "55467c6157306f2a4463e9d149b0ed2552943f187778cc67d02e5bef4735773d"
)
CONTROLLED_QWEN_TEMPLATE = (
    "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8"
)
MIN_DISK_FREE = 8 * 1024**3
MIN_PHYSICAL_MEMORY = 16 * 1024**3
MIN_RECLAIMABLE_MEMORY = 4 * 1024**3


def _run_local(
    argv: list[str],
    *,
    environment: dict[str, str],
    timeout: int,
    output_fd: int | None = None,
    output_limit: int | None = None,
) -> bytes:
    """Run an absolute local executable with bounded capture and group cleanup."""
    if not argv or not Path(argv[0]).is_absolute() or not os.access(argv[0], os.X_OK):
        raise PolicyError("mlx_executable_must_be_absolute_and_executable")
    read_fd: int | None = None
    write_fd = output_fd
    if write_fd is None:
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
    try:
        pid = os.posix_spawn(
            argv[0],
            argv,
            environment,
            file_actions=[
                (os.POSIX_SPAWN_DUP2, write_fd, 1),
                (os.POSIX_SPAWN_DUP2, write_fd, 2),
            ],
            setpgroup=0,
        )
    except (OSError, TypeError) as exc:
        if read_fd is not None:
            os.close(read_fd)
            os.close(write_fd)
        raise PolicyError("mlx_local_process_unavailable") from exc
    if read_fd is not None:
        os.close(write_fd)
    reaped = False
    captured = bytearray()
    try:
        deadline = time.monotonic() + timeout
        while True:
            if read_fd is not None:
                ready, _, _ = select.select([read_fd], [], [], 0.05)
                if ready:
                    chunk = os.read(read_fd, 64 * 1024 + 1 - len(captured))
                    captured.extend(chunk)
                    if len(captured) > 64 * 1024:
                        raise PolicyError("mlx_local_process_output_overflow")
            else:
                time.sleep(0.05)
                if (
                    output_limit is not None
                    and output_fd is not None
                    and os.fstat(output_fd).st_size > output_limit
                ):
                    raise PolicyError("mlx_local_process_output_overflow")
            completed, status = os.waitpid(pid, os.WNOHANG)
            if completed == pid:
                reaped = True
                if os.waitstatus_to_exitcode(status):
                    raise PolicyError("mlx_local_process_failed")
                if read_fd is not None:
                    while True:
                        try:
                            chunk = os.read(read_fd, 64 * 1024 + 1 - len(captured))
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        captured.extend(chunk)
                        if len(captured) > 64 * 1024:
                            raise PolicyError("mlx_local_process_output_overflow")
                return bytes(captured)
            if time.monotonic() >= deadline:
                raise PolicyError("mlx_local_process_timeout")
    except BaseException:
        if not reaped:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                # A child may exit between the poll and group signal on macOS.
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            os.waitpid(pid, 0)
        raise
    finally:
        if read_fd is not None:
            os.close(read_fd)


def _local_output(argv: list[str], *, environment: dict[str, str], timeout: int) -> str:
    return _run_local(argv, environment=environment, timeout=timeout).decode("utf-8")


class MLXWriterConfig(StrictModel):
    candidate: FileRef
    dataset: FileRef
    mlx_python: Path
    family: Literal["writer"] = "writer"
    method: Literal["lora"] = "lora"
    seed: int = Field(ge=0, le=2**31 - 1)
    sequence_length: int = Field(ge=128, le=2048)
    iterations: int = Field(ge=1, le=10000)
    gradient_accumulation: int = Field(ge=1, le=128)
    num_layers: int = Field(ge=1, le=64)
    lora_rank: int = Field(ge=1, le=32)
    lora_scale: float = Field(gt=0, le=128, allow_inf_nan=False)
    learning_rate: float = Field(gt=0, le=0.001, allow_inf_nan=False)
    max_wall_seconds: int = Field(ge=60, le=43200)
    resume_adapter: FileRef | None = None
    resume_intent: FileRef | None = None

    @model_validator(mode="after")
    def bounded(self):
        if self.iterations % self.gradient_accumulation:
            raise ValueError(
                "Every accumulated gradient must receive an optimizer step"
            )
        if (self.resume_adapter is None) != (self.resume_intent is None):
            raise ValueError("Weights-only continuation needs adapter and bound intent")
        return self


def _mac_preflight(output: Path) -> dict[str, int | str]:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise PolicyError("mlx_training_requires_apple_silicon")
    if output.exists() or not output.parent.is_dir() or output.parent.is_symlink():
        raise PolicyError("mlx_output_must_be_new_under_existing_directory")
    environment = _offline_environment()
    total = int(
        _local_output(
            ["/usr/sbin/sysctl", "-n", "hw.memsize"],
            environment=environment,
            timeout=15,
        )
    )
    if total < MIN_PHYSICAL_MEMORY:
        raise PolicyError("mlx_physical_memory_below_training_floor")
    vm = _local_output(["/usr/bin/vm_stat"], environment=environment, timeout=15)
    page_size = int(vm.split("page size of ", 1)[1].split(" bytes", 1)[0])
    pages = {}
    for line in vm.splitlines():
        if line.startswith("Pages ") and ":" in line:
            key, value = line.split(":", 1)
            pages[key] = int(value.strip().rstrip("."))
    reclaimable = page_size * sum(
        pages.get(name, 0)
        for name in (
            "Pages free",
            "Pages inactive",
            "Pages speculative",
            "Pages purgeable",
        )
    )
    if reclaimable < MIN_RECLAIMABLE_MEMORY:
        raise PolicyError("mlx_reclaimable_memory_below_training_floor")
    free = shutil.disk_usage(output.parent).free
    if free < MIN_DISK_FREE:
        raise PolicyError("mlx_checkpoint_disk_below_training_floor")
    return {
        "machine": "Darwin/arm64",
        "physical_memory_bytes": total,
        "reclaimable_memory_bytes": reclaimable,
        "disk_free_bytes": free,
        "classification": "PREFLIGHT_ESTIMATE_NOT_TRAINING_MEASUREMENT",
    }


def _mlx_version(python: Path) -> str:
    if not python.is_absolute() or not python.is_file():
        raise PolicyError("mlx_python_not_found")
    try:
        version = _local_output(
            [
                str(python),
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('mlx-lm'))",
            ],
            timeout=15,
            environment=_offline_environment(),
        ).strip()
    except (OSError, UnicodeError, PolicyError) as exc:
        raise PolicyError("mlx_runtime_unavailable") from exc
    if version != MLX_LM_VERSION:
        raise PolicyError("mlx_runtime_version_mismatch")
    return version


def _bindings(config: MLXWriterConfig, candidate_hash: str, dataset_hash: str) -> dict:
    return {
        "candidate_manifest_sha256": candidate_hash,
        "dataset_manifest_sha256": dataset_hash,
        "hyperparameters": {
            "seed": config.seed,
            "sequence_length": config.sequence_length,
            "gradient_accumulation": config.gradient_accumulation,
            "num_layers": config.num_layers,
            "lora_rank": config.lora_rank,
            "lora_scale": config.lora_scale,
            "learning_rate": config.learning_rate,
        },
    }


def _admission_hashes(
    admitted: Path,
    candidate_review: CandidateReview,
    dataset_file: Path,
    dataset: Dataset,
) -> dict[str, str]:
    """Bind the already-validated human decisions to the actual training run."""
    if (
        candidate_review.owner_decision is None
        or candidate_review.technical_acceptance is None
    ):
        raise PolicyError("mlx_base_admission_incomplete")
    dataset_review_file = dataset.review.verify(dataset_file.parent)
    dataset_review = DatasetReview.model_validate_json(dataset_review_file.read_bytes())
    if dataset_review.owner_decision is None:
        raise PolicyError("mlx_dataset_admission_incomplete")
    return {
        "base_review_sha256": digest(admitted / "review.json"),
        "base_owner_decision_sha256": digest(
            candidate_review.owner_decision.verify(admitted)
        ),
        "technical_acceptance_sha256": digest(
            candidate_review.technical_acceptance.verify(admitted)
        ),
        "dataset_review_sha256": digest(dataset_review_file),
        "dataset_owner_decision_sha256": digest(
            dataset_review.owner_decision.verify(dataset_file.parent)
        ),
    }


def _resume_source(config: MLXWriterConfig, root: Path, bindings: dict) -> Path | None:
    if config.resume_adapter is None or config.resume_intent is None:
        return None
    adapter = config.resume_adapter.verify(root)
    intent = config.resume_intent.verify(root)
    if (
        adapter.parent != intent.parent
        or adapter.suffix != ".safetensors"
        or intent.name != "run-intent.json"
    ):
        raise PolicyError("mlx_resume_files_must_share_run_directory")
    prior = json.loads(intent.read_bytes())
    if any(prior.get(key) != value for key, value in bindings.items()):
        raise PolicyError("mlx_resume_lineage_or_hyperparameters_mismatch")
    _verify_adapter(adapter)
    return adapter


def _write_training_rows(directory: Path, rows: dict):
    # MLX-LM understands prompt/completion JSONL; its loss is prompt-masked below.
    # Test/calibration/OOD data are deliberately never copied into trainer input.
    for name, split in (("train", "train"), ("valid", "validation")):
        with (directory / f"{name}.jsonl").open("xb") as stream:
            for row in rows[split]:
                stream.write(
                    canonical({"prompt": row["input"], "completion": row["target"]})
                    + b"\n"
                )


def _offline_environment() -> dict[str, str]:
    # Do not pass credentials, proxy settings or telemetry integrations to MLX.
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
    }
    environment.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TOKENIZERS_PARALLELISM="false",
        WANDB_DISABLED="true",
    )
    return environment


def _verify_adapter(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size <= 8:
        raise PolicyError("mlx_training_checkpoint_missing")
    with path.open("rb") as stream:
        header_length = int.from_bytes(stream.read(8), "little")
        if not 2 <= header_length <= min(16 * 1024**2, path.stat().st_size - 8):
            raise PolicyError("mlx_adapter_invalid_header")
        header = json.loads(stream.read(header_length))
    sizes = {"F32": 4, "F16": 2, "BF16": 2}
    intervals = []
    tensors = 0
    for name, value in header.items():
        if name == "__metadata__":
            continue
        shape, offsets = value.get("shape", []), value.get("data_offsets", [])
        if (
            "lora" not in name.lower()
            or value.get("dtype") not in sizes
            or not shape
            or len(offsets) != 2
            or any(type(item) is not int or item < 0 for item in [*shape, *offsets])
            or offsets[1] - offsets[0] != math.prod(shape) * sizes[value["dtype"]]
        ):
            raise PolicyError("mlx_adapter_invalid_tensor")
        intervals.append(offsets)
        tensors += 1
    end = 0
    for start, stop in sorted(intervals):
        if start != end:
            raise PolicyError("mlx_adapter_invalid_offsets")
        end = stop
    if not tensors or end != path.stat().st_size - 8 - header_length:
        raise PolicyError("mlx_adapter_invalid_payload")
    return digest(path)


def _mlx_command_config(
    config: MLXWriterConfig,
    model: Path,
    training_data: Path,
    output: Path,
    resume: Path | None,
) -> dict:
    return {
        "model": str(model),
        "train": True,
        "fine_tune_type": "lora",
        "optimizer": "adamw",
        "data": str(training_data),
        "seed": config.seed,
        "num_layers": config.num_layers,
        "batch_size": 1,
        "iters": config.iterations,
        "val_batches": -1,
        "learning_rate": config.learning_rate,
        "steps_per_report": max(1, min(10, config.iterations)),
        "steps_per_eval": max(1, min(50, config.iterations)),
        "resume_adapter_file": str(resume) if resume else None,
        "adapter_path": str(output),
        "save_every": max(1, min(50, config.iterations)),
        "test": False,
        "max_seq_length": config.sequence_length,
        "grad_checkpoint": True,
        "grad_accumulation_steps": config.gradient_accumulation,
        "lora_parameters": {
            "rank": config.lora_rank,
            "dropout": 0.0,
            "scale": config.lora_scale,
        },
        "mask_prompt": True,
        "report_to": None,
        "trust_remote_code": False,
    }


def train(config_file: Path, output: Path) -> dict:
    config = MLXWriterConfig.model_validate_json(config_file.read_bytes())
    admitted = config.candidate.verify(config_file.parent).parent
    if digest(admitted / "candidate.json") != config.candidate.sha256:
        raise PolicyError("candidate_reference_mismatch")
    candidate, review = load_candidate(admitted, smoke=False)
    dataset_file = config.dataset.verify(config_file.parent)
    dataset, rows = read_dataset(dataset_file, "writer", smoke=False)
    if (
        config.candidate.sha256 != CONTROLLED_QWEN_MANIFEST
        or candidate.architecture != "qwen3"
        or candidate.revision != CONTROLLED_QWEN_REVISION
        or candidate.artifacts.get("model.safetensors") != CONTROLLED_QWEN_WEIGHT
        or candidate.artifacts.get("chat_template.jinja") != CONTROLLED_QWEN_TEMPLATE
        or candidate.weights != ["model.safetensors"]
    ):
        raise PolicyError("mlx_candidate_not_exact_controlled_qwen_bundle")
    if not any(MLX_LM_VERSION in value for value in candidate.runtime_compatibility):
        raise PolicyError("candidate_not_validated_for_pinned_mlx_runtime")
    if config.sequence_length > candidate.context:
        raise PolicyError("training_context_exceeds_admission")
    hardware = _mac_preflight(output)
    mlx_version = _mlx_version(config.mlx_python)
    admission_hashes = _admission_hashes(admitted, review, dataset_file, dataset)
    bindings = {
        **_bindings(config, config.candidate.sha256, config.dataset.sha256),
        **admission_hashes,
    }
    resume = _resume_source(config, config_file.parent, bindings)
    environment = _offline_environment()
    model = (admitted / "bundle").resolve()
    with tempfile.TemporaryDirectory(
        prefix="azaeron-mlx-data-", dir=output.parent
    ) as temporary:
        training_data = Path(temporary)
        training_data.chmod(0o700)
        _write_training_rows(training_data, rows)
        prepared_data_hashes = {
            name: digest(training_data / f"{name}.jsonl") for name in ("train", "valid")
        }
        # MLX-LM silently truncates overlength rows. This separate, pinned
        # interpreter checks the exact chat template and masked target offset.
        with os.fdopen(os.open(os.devnull, os.O_WRONLY), "wb") as sink:
            _run_local(
                [
                    str(config.mlx_python),
                    str(Path(__file__).with_name("mlx_token_preflight.py")),
                    str(model),
                    str(training_data),
                    str(config.sequence_length),
                ],
                timeout=180,
                environment=environment,
                output_fd=sink.fileno(),
            )
        # Recheck input integrity immediately before creating any output.
        _, rechecked_review = load_candidate(admitted, smoke=False)
        rechecked_dataset, _ = read_dataset(dataset_file, "writer", smoke=False)
        if (
            _admission_hashes(
                admitted, rechecked_review, dataset_file, rechecked_dataset
            )
            != admission_hashes
        ):
            raise PolicyError("mlx_admission_changed_during_training")
        if config.resume_adapter is not None and config.resume_intent is not None:
            config.resume_adapter.verify(config_file.parent)
            config.resume_intent.verify(config_file.parent)
        output.mkdir(mode=0o700, exist_ok=False)
        intent = {
            "schema_version": 1,
            **bindings,
            "purpose": "EXPERIMENTAL",
            "production_approval": "NOT_APPROVED",
            "base_repository": candidate.repository,
            "base_revision": candidate.revision,
            "base_artifacts": candidate.artifacts,
            "dataset_splits": {key: ref.sha256 for key, ref in dataset.splits.items()},
            "prepared_training_data_sha256": prepared_data_hashes,
            "config_sha256": digest(config_file),
            "resume_semantics": (
                "WEIGHTS_ONLY_OPTIMIZER_RNG_AND_ITERATION_RESET"
                if resume
                else "NEW_RUN"
            ),
            "resume_adapter_sha256": digest(resume) if resume else None,
        }
        (output / "run-intent.json").write_bytes(canonical(intent) + b"\n")
        mlx_config = _mlx_command_config(config, model, training_data, output, resume)
        command_file = training_data / "mlx-config.json"
        command_file.write_bytes(canonical(mlx_config) + b"\n")
        mlx_config_hash = digest(command_file)
        log_fd = os.open(
            output / "training.log", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(log_fd, "wb") as log:
            _run_local(
                [
                    str(config.mlx_python),
                    "-m",
                    "mlx_lm",
                    "lora",
                    "-c",
                    str(command_file),
                ],
                timeout=config.max_wall_seconds,
                environment=environment,
                output_fd=log.fileno(),
                output_limit=64 * 1024**2,
            )
    adapter = output / "adapters.safetensors"
    checkpoint_hash = _verify_adapter(adapter)
    # A completed process and changed adapter produce a candidate, not quality evidence.
    if resume is not None and checkpoint_hash == digest(resume):
        raise PolicyError("mlx_training_did_not_change_resumed_adapter")
    _, rechecked_review = load_candidate(admitted, smoke=False)
    rechecked_dataset, _ = read_dataset(dataset_file, "writer", smoke=False)
    if (
        _admission_hashes(admitted, rechecked_review, dataset_file, rechecked_dataset)
        != admission_hashes
    ):
        raise PolicyError("mlx_admission_changed_during_training")
    if config.resume_adapter is not None and config.resume_intent is not None:
        config.resume_adapter.verify(config_file.parent)
        config.resume_intent.verify(config_file.parent)
    if digest(config_file) != intent["config_sha256"]:
        raise PolicyError("mlx_config_changed_during_training")
    training = {
        **intent,
        "status": "EXPERIMENTAL",
        "classification": "AZAERON_DERIVATIVE",
        "checkpoint_sha256": checkpoint_hash,
        "adapter_config_sha256": digest(output / "adapter_config.json"),
        "log_sha256": digest(output / "training.log"),
        "mlx_lm_version": mlx_version,
        "mlx_invocation_config_sha256": mlx_config_hash,
        "mlx_invocation": {
            **mlx_config,
            "model": "EXACT_ADMITTED_BUNDLE",
            "data": "PREPARED_TRAIN_AND_VALIDATION_SPLITS",
            "adapter_path": "OUTPUT_DIRECTORY",
            "resume_adapter_file": "HASHED_PRIOR_WEIGHTS" if resume else None,
        },
        "trainer_code_sha256": digest(Path(__file__)),
        "token_preflight_code_sha256": digest(
            Path(__file__).with_name("mlx_token_preflight.py")
        ),
        "hardware_preflight": hardware,
        "iterations_configured": config.iterations,
        "optimizer_steps_configured": config.iterations // config.gradient_accumulation,
        "trainer_process_exit": 0,
        "quality_evaluation": "NOT_RUN",
        "human_review": "NOT_FOUND",
        "owner_base_reviewer": review.reviewer,
    }
    (output / "training-manifest.json").write_bytes(canonical(training) + b"\n")
    (output / "MODEL_CARD.md").write_text(
        "# Azaeron-Verity-Writer experimental MLX LoRA derivative\n\n"
        f"Base: {candidate.repository}@{candidate.revision}. License: {candidate.license}.\n\n"
        "No independent quality, production security or release approval is claimed. "
        "Adapter loading requires the exact admitted third-party base. "
        "See training-manifest.json for hashes and continuation semantics.\n"
    )
    return training


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = train(args.config, args.output)
    print(
        canonical(
            {
                key: result[key]
                for key in ("status", "checkpoint_sha256", "production_approval")
            }
        ).decode()
    )


if __name__ == "__main__":
    main()
