#!/usr/bin/env python3
"""Disk-guarded offline conversion of the pinned Qwen source; no admission."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / ".verity-local/qwen3-4b-source-1cfa9a"
PRIVATE = ROOT / ".verity-local/qwen-mixed-4-6-20261013"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def free_gib() -> float:
    return shutil.disk_usage(ROOT).free / 1024**3


def save_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def main() -> None:
    seal = json.loads((HERE / "conversion-seal.json").read_bytes())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError("conversion seal mismatch: " + name)
    protocol = json.loads((HERE / "conversion-protocol.json").read_bytes())
    if sha(HERE / protocol["environment_lock"]) != protocol["environment_lock_sha256"]:
        raise RuntimeError("pinned conversion environment changed")
    old_summary = HERE.parent / "qwen-technical-32case-20261013/run-source.json"
    if sha(old_summary) != protocol["source_inventory_sha256"]:
        raise RuntimeError("pinned source inventory changed")
    old_hashes = json.loads(old_summary.read_bytes())["artifact_hashes"]
    for name, expected in old_hashes.items():
        path = SOURCE / name
        if path.is_symlink() or sha(path) != expected:
            raise RuntimeError("pinned source artifact mismatch: " + name)
    output = ROOT / protocol["output"]
    result_path = HERE / "conversion-result.json"
    if output.exists() or result_path.exists():
        raise RuntimeError("refusing to overwrite a candidate or result")
    if free_gib() < protocol["minimum_free_disk_gib_before"]:
        raise RuntimeError("disk headroom below sealed preflight")
    PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    log = PRIVATE / "conversion.log"
    command = [
        sys.executable,
        "-m",
        "mlx_lm",
        "convert",
        "--hf-path",
        str(SOURCE),
        "--mlx-path",
        str(output),
        "-q",
        "--q-group-size",
        "128",
        "--quant-predicate",
        "mixed_4_6",
    ]
    env = os.environ.copy()
    env.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
    )
    start_free = free_gib()
    minimum_free = start_free
    started = time.monotonic()
    reason = None
    with log.open("x") as stream:
        log.chmod(0o600)
        process = subprocess.Popen(
            command, stdout=stream, stderr=subprocess.STDOUT, env=env
        )
        while process.poll() is None:
            minimum_free = min(minimum_free, free_gib())
            if minimum_free < protocol["minimum_free_disk_gib_during_and_after"]:
                reason = "disk_guard_triggered"
            elif time.monotonic() - started > protocol["maximum_conversion_seconds"]:
                reason = "conversion_time_guard_triggered"
            if reason:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.25)
    minimum_free = min(minimum_free, free_gib())
    if process.returncode != 0 or reason:
        if output.exists() and output.parent == ROOT / ".verity-local":
            shutil.rmtree(output)
        save_new(
            result_path,
            {
                "classification": "FAILED_NON_TRAINING_CONVERSION",
                "reason": reason or "converter_failed",
                "return_code": process.returncode,
                "start_free_gib": round(start_free, 3),
                "minimum_free_gib": round(minimum_free, 3),
                "private_log_sha256": sha(log),
                "base_admitted": False,
            },
        )
        raise RuntimeError(reason or "converter_failed")
    shutil.copyfile(SOURCE / "LICENSE", output / "LICENSE")
    shutil.copyfile(SOURCE / "tokenizer.json", output / "tokenizer.json")
    if free_gib() < protocol["minimum_free_disk_gib_during_and_after"]:
        if output.parent == ROOT / ".verity-local":
            shutil.rmtree(output)
        save_new(
            result_path,
            {
                "classification": "FAILED_NON_TRAINING_CONVERSION",
                "reason": "post_conversion_disk_guard_triggered",
                "start_free_gib": round(start_free, 3),
                "minimum_free_gib": round(minimum_free, 3),
                "private_log_sha256": sha(log),
                "base_admitted": False,
            },
        )
        raise RuntimeError("post-conversion disk headroom below sealed minimum")
    files = {
        path.relative_to(output).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha(path),
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    save_new(
        result_path,
        {
            "classification": "UNADMITTED_THIRD_PARTY_CONVERSION_CANDIDATE",
            "source_repository": protocol["source_repository"],
            "source_revision": protocol["source_revision"],
            "source_artifact_hashes": old_hashes,
            "protocol_sha256": sha(HERE / "conversion-protocol.json"),
            "seal_sha256": sha(HERE / "conversion-seal.json"),
            "output_relative_path": protocol["output"],
            "files": files,
            "start_free_gib": round(start_free, 3),
            "minimum_free_gib": round(minimum_free, 3),
            "end_free_gib": round(free_gib(), 3),
            "private_log_sha256": sha(log),
            "owner_approval": "NOT_REQUESTED_FOR_THIS_ARTIFACT",
            "technical_acceptance": "NOT_EVALUATED",
            "training_authorized": False,
            "production_approved": False,
        },
    )


if __name__ == "__main__":
    main()
