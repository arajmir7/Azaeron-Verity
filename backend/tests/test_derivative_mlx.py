"""MLX Writer safety checks. These tests never invoke training."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.model_platform import derivative_mlx as mlx
from app.modules.model_platform.admission import CandidateReview
from app.modules.model_platform.datasets import Dataset, DatasetReview
from app.modules.model_platform.policy import FileRef, PolicyError, canonical, digest


def config(tmp_path: Path, **changes) -> mlx.MLXWriterConfig:
    values = {
        "candidate": {"path": "admitted/candidate.json", "sha256": "a" * 64},
        "dataset": {"path": "dataset.json", "sha256": "b" * 64},
        "mlx_python": "/nonexistent/python",
        "seed": 42,
        "sequence_length": 1024,
        "iterations": 8,
        "gradient_accumulation": 2,
        "num_layers": 8,
        "lora_rank": 8,
        "lora_scale": 20,
        "learning_rate": 0.0001,
        "max_wall_seconds": 3600,
    }
    values.update(changes)
    return mlx.MLXWriterConfig.model_validate(values)


def test_mlx_rejects_dropped_gradients_and_partial_resume(tmp_path):
    with pytest.raises(ValidationError, match="optimizer step"):
        config(tmp_path, iterations=7)
    with pytest.raises(ValidationError, match="adapter and bound intent"):
        config(
            tmp_path,
            resume_adapter={"path": "adapters.safetensors", "sha256": "c" * 64},
        )


def test_mlx_owner_gate_precedes_training_and_output(tmp_path, monkeypatch):
    admitted = tmp_path / "admitted"
    admitted.mkdir()
    (admitted / "candidate.json").write_bytes(b"{}")
    value = config(
        tmp_path,
        candidate={
            "path": "admitted/candidate.json",
            "sha256": digest(admitted / "candidate.json"),
        },
    )
    config_file = tmp_path / "config.json"
    config_file.write_bytes(canonical(value.model_dump(mode="json")))

    def reject(*_args, **_kwargs):
        raise PolicyError("owner_candidate_decision_required")

    monkeypatch.setattr(mlx, "load_candidate", reject)
    monkeypatch.setattr(
        mlx,
        "read_dataset",
        lambda *_args, **_kwargs: pytest.fail("data read before base approval"),
    )
    output = tmp_path / "new-run"
    with pytest.raises(PolicyError, match="owner_candidate_decision_required"):
        mlx.train(config_file, output)
    assert not output.exists()


def test_mlx_only_prepares_train_and_validation(tmp_path):
    rows = {
        split: [{"input": f"{split} question", "target": "reviewed answer"}]
        for split in ("train", "validation", "calibration", "test", "ood")
    }
    mlx._write_training_rows(tmp_path, rows)
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "train.jsonl",
        "valid.jsonl",
    ]
    assert json.loads((tmp_path / "valid.jsonl").read_text()) == {
        "prompt": "validation question",
        "completion": "reviewed answer",
    }


def test_mlx_weights_only_continuation_requires_matching_intent(tmp_path):
    prior = tmp_path / "prior"
    prior.mkdir()
    adapter = prior / "adapters.safetensors"
    adapter.write_bytes(b"fixture weights")
    intent = prior / "run-intent.json"
    intent.write_bytes(canonical({"candidate_manifest_sha256": "other"}))
    value = config(
        tmp_path,
        resume_adapter={
            "path": "prior/adapters.safetensors",
            "sha256": digest(adapter),
        },
        resume_intent={"path": "prior/run-intent.json", "sha256": digest(intent)},
    )
    with pytest.raises(PolicyError, match="resume_lineage"):
        mlx._resume_source(value, tmp_path, mlx._bindings(value, "a" * 64, "b" * 64))


def test_mlx_run_binds_and_rechecks_base_and_dataset_decisions(tmp_path):
    admitted = tmp_path / "admitted"
    admitted.mkdir()
    (admitted / "review.json").write_bytes(b"reviewed base")
    (admitted / "owner-decision.json").write_bytes(b"base owner")
    (admitted / "technical-acceptance.json").write_bytes(b"technical reviewer")
    base_review = CandidateReview.model_construct(
        owner_decision=FileRef(
            path="owner-decision.json",
            sha256=digest(admitted / "owner-decision.json"),
        ),
        technical_acceptance=FileRef(
            path="technical-acceptance.json",
            sha256=digest(admitted / "technical-acceptance.json"),
        ),
    )
    data = tmp_path / "data"
    data.mkdir()
    (data / "owner-decision.json").write_bytes(b"dataset owner")
    data_review = DatasetReview(
        subject_sha256="a" * 64,
        reviewer="fixture owner",
        reviewer_kind="HUMAN",
        reviewed_at="2026-10-13",
        evidence_reference="TEST FIXTURE",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        pii="PASS",
        owner_decision=FileRef(
            path="owner-decision.json",
            sha256=digest(data / "owner-decision.json"),
        ),
    )
    (data / "review.json").write_bytes(canonical(data_review.model_dump(mode="json")))
    dataset = Dataset.model_construct(
        review=FileRef(path="review.json", sha256=digest(data / "review.json"))
    )
    bound = mlx._admission_hashes(admitted, base_review, data / "dataset.json", dataset)
    assert bound["base_review_sha256"] == digest(admitted / "review.json")
    assert bound["dataset_owner_decision_sha256"] == digest(
        data / "owner-decision.json"
    )
    (data / "owner-decision.json").write_bytes(b"changed dataset owner")
    with pytest.raises(PolicyError, match="artifact_hash_mismatch"):
        mlx._admission_hashes(admitted, base_review, data / "dataset.json", dataset)


def test_mlx_memory_disk_preflight_parses_vm_stat(tmp_path, monkeypatch):
    monkeypatch.setattr(mlx.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(mlx.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        mlx,
        "_local_output",
        lambda command, **_kwargs: (
            str(16 * 1024**3)
            if command[0] == "/usr/sbin/sysctl"
            else "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
            "Pages free: 300000.\nPages inactive: 300000.\n"
            "Pages speculative: 1000.\nPages purgeable: 1000.\n"
        ),
    )
    monkeypatch.setattr(
        mlx.shutil, "disk_usage", lambda _path: SimpleNamespace(free=9 * 1024**3)
    )
    result = mlx._mac_preflight(tmp_path / "new-run")
    assert result["physical_memory_bytes"] == 16 * 1024**3
    assert result["reclaimable_memory_bytes"] > 4 * 1024**3
    monkeypatch.setattr(
        mlx.shutil, "disk_usage", lambda _path: SimpleNamespace(free=7 * 1024**3)
    )
    with pytest.raises(PolicyError, match="checkpoint_disk"):
        mlx._mac_preflight(tmp_path / "new-run")


def test_mlx_local_runner_requires_absolute_executable_and_bounds_capture():
    with pytest.raises(PolicyError, match="absolute_and_executable"):
        mlx._run_local(["python", "-c", "pass"], environment={}, timeout=1)
    with pytest.raises(PolicyError, match="absolute_and_executable"):
        mlx._run_local(["/no/such/python"], environment={}, timeout=1)
    value = mlx._run_local(
        [sys.executable, "-c", "print('local-only')"],
        environment={"PATH": "/usr/bin"},
        timeout=3,
    )
    assert value == b"local-only\n"
    with pytest.raises(PolicyError, match="output_overflow"):
        mlx._run_local(
            [sys.executable, "-c", "print('x' * 70000)"],
            environment={"PATH": "/usr/bin"},
            timeout=3,
        )


def test_mlx_local_runner_reaps_timeout_and_rejects_nonzero(tmp_path):
    with pytest.raises(PolicyError, match="process_failed"):
        mlx._run_local(
            [sys.executable, "-c", "raise SystemExit(3)"],
            environment={"PATH": "/usr/bin"},
            timeout=3,
        )
    with pytest.raises(PolicyError, match="process_timeout"):
        mlx._run_local(
            [sys.executable, "-c", "import time; time.sleep(4)"],
            environment={"PATH": "/usr/bin"},
            timeout=1,
        )
    log = tmp_path / "process.log"
    with log.open("wb") as stream:
        assert (
            mlx._run_local(
                [sys.executable, "-c", "print('logged')"],
                environment={"PATH": "/usr/bin"},
                timeout=3,
                output_fd=stream.fileno(),
            )
            == b""
        )
    assert log.read_bytes() == b"logged\n"
    with log.open("wb") as stream:
        with pytest.raises(PolicyError, match="output_overflow"):
            mlx._run_local(
                [sys.executable, "-c", "print('x' * 1000)"],
                environment={"PATH": "/usr/bin"},
                timeout=3,
                output_fd=stream.fileno(),
                output_limit=100,
            )


def test_mlx_subprocess_environment_excludes_credentials(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-token")
    monkeypatch.setenv("HTTPS_PROXY", "https://example.invalid")
    environment = mlx._offline_environment()
    assert "HF_TOKEN" not in environment
    assert "HTTPS_PROXY" not in environment
    assert environment["HF_HUB_OFFLINE"] == "1"


def test_mlx_adapter_requires_complete_lora_safetensors(tmp_path):
    adapter = tmp_path / "adapters.safetensors"
    header = canonical(
        {
            "model.layers.0.self_attn.q_proj.lora_a": {
                "dtype": "F32",
                "shape": [1],
                "data_offsets": [0, 4],
            }
        }
    )
    adapter.write_bytes(len(header).to_bytes(8, "little") + header + bytes(4))
    assert mlx._verify_adapter(adapter) == digest(adapter)
    adapter.write_bytes(len(header).to_bytes(8, "little") + header + bytes(3))
    with pytest.raises(PolicyError, match="invalid_payload"):
        mlx._verify_adapter(adapter)


def test_mlx_command_is_local_masked_and_does_not_report_externally(tmp_path):
    value = mlx._mlx_command_config(
        config(tmp_path),
        tmp_path / "admitted" / "bundle",
        tmp_path / "prepared",
        tmp_path / "new-run",
        None,
    )
    assert value["model"] == str(tmp_path / "admitted" / "bundle")
    assert value["data"] == str(tmp_path / "prepared")
    assert value["mask_prompt"] is True
    assert value["trust_remote_code"] is False
    assert value["report_to"] is None
    assert value["grad_accumulation_steps"] == 2
    assert value["resume_adapter_file"] is None
