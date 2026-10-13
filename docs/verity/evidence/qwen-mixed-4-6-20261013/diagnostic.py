#!/usr/bin/env python3
"""Repeat a new conversion on the known failure set without admitting it."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / "qwen-technical-32case-20261013"
PRIVATE = ROOT / ".verity-local/qwen-mixed-4-6-20261013"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def save_new(path: Path, value: dict, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def inputs() -> tuple[dict, dict, dict]:
    seal = json.loads((HERE / "diagnostic-seal.json").read_bytes())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError("diagnostic seal mismatch: " + name)
    protocol = json.loads((HERE / "diagnostic-protocol.json").read_bytes())
    checks = (
        (HERE / "conversion-result.json", "candidate_conversion_result_sha256"),
        (OLD / "seal.json", "original_seal_sha256"),
        (OLD / "fixtures.json", "original_fixtures_sha256"),
        (OLD / "benchmark.py", "original_runner_sha256"),
        (
            ROOT / ".verity-local/qwen-technical-32case-20261013/raw-source.json",
            "original_source_raw_sha256",
        ),
        (
            ROOT / ".verity-local/qwen-technical-32case-20261013/raw-candidate.json",
            "original_4bit_raw_sha256",
        ),
    )
    for path, key in checks:
        if sha(path) != protocol[key]:
            raise RuntimeError("input hash changed: " + key)
    conversion = json.loads((HERE / "conversion-result.json").read_bytes())
    bundle = ROOT / conversion["output_relative_path"]
    if conversion["files"]["model.safetensors"]["sha256"] != protocol["candidate_weight_sha256"]:
        raise RuntimeError("new candidate identity mismatch")
    for name, item in conversion["files"].items():
        path = bundle / name
        if path.is_symlink() or sha(path) != item["sha256"]:
            raise RuntimeError("new candidate artifact changed: " + name)
    old_seal = json.loads((OLD / "seal.json").read_bytes())
    for name, expected in old_seal["input_sha256"].items():
        if sha(OLD / name) != expected:
            raise RuntimeError("old sealed benchmark changed: " + name)
    fixtures = json.loads((OLD / "fixtures.json").read_bytes())
    if (
        len(fixtures["tasks"]) != protocol["task_cases"]
        or len(fixtures["stopping"]) != protocol["stopping_cases"]
        or len(fixtures["resources"]) != protocol["resource_cases"]
    ):
        raise RuntimeError("diagnostic case count mismatch")
    return protocol, conversion, fixtures


def old_runner():
    spec = importlib.util.spec_from_file_location("sealed_qwen_benchmark", OLD / "benchmark.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("sealed runner import failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(repetition: int) -> None:
    protocol, conversion, fixtures = inputs()
    if repetition not in (1, 2):
        raise ValueError("only two declared repetitions allowed")
    if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib_before"] * 1024**3:
        raise RuntimeError("disk headroom below diagnostic preflight")
    raw_path = PRIVATE / f"diagnostic-{repetition}.json"
    summary_path = HERE / f"diagnostic-{repetition}.json"
    if raw_path.exists() or summary_path.exists():
        raise RuntimeError("refusing to overwrite diagnostic run")
    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
    )
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.sample_utils import make_sampler

    runner = old_runner()
    model, tokenizer = load(str(ROOT / conversion["output_relative_path"]), trust_remote_code=False)
    sampler = make_sampler(temp=0.0)
    records: dict[str, list[dict]] = {"tasks": [], "stopping": [], "resources": []}
    for group, max_tokens in (
        ("tasks", protocol["task_max_tokens"]),
        ("stopping", protocol["stopping_max_tokens"]),
        ("resources", protocol["resource_max_tokens"]),
    ):
        for case in fixtures[group]:
            if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib_during"] * 1024**3:
                raise RuntimeError("disk headroom fell below diagnostic minimum")
            item = runner.generate_case(model, tokenizer, case["prompt"], max_tokens, sampler)
            item["id"] = case["id"]
            if group == "tasks":
                item["score"] = runner.score(case, item["response"])
            elif group == "stopping":
                item["expected_exact_match"] = runner.normalize(item["response"]) == runner.normalize(case["expected"])
            else:
                item["success"] = (
                    item["input_tokens"] >= protocol["resource_minimum_input_tokens"]
                    and item["finish_reason"] == "stop"
                    and runner.normalize(item["response"])
                    == runner.normalize(case["expected"])
                )
            records[group].append(item)
    raw = {
        "repetition": repetition,
        "protocol_sha256": sha(HERE / "diagnostic-protocol.json"),
        "candidate_weight_sha256": protocol["candidate_weight_sha256"],
        "eos_token_ids": sorted(tokenizer.eos_token_ids),
        "peak_mlx_memory_gib": round(mx.get_peak_memory() / 1024**3, 4),
        "records": records,
    }
    save_new(raw_path, raw, private=True)
    save_new(
        summary_path,
        {
            "classification": "KNOWN_SET_DIAGNOSTIC_NOT_ACCEPTANCE",
            "repetition": repetition,
            "protocol_sha256": raw["protocol_sha256"],
            "candidate_weight_sha256": raw["candidate_weight_sha256"],
            "private_raw_sha256": sha(raw_path),
            "task_score": sum(item["score"] for item in records["tasks"]),
            "task_cases": len(records["tasks"]),
            "stopping_exact": sum(item["expected_exact_match"] for item in records["stopping"]),
            "stopping_cases": len(records["stopping"]),
            "stopping_terminal_stop": sum(item["finish_reason"] == "stop" for item in records["stopping"]),
            "literal_reasoning_markers": sum(
                item["reasoning_visible"] for group in records.values() for item in group
            ),
            "resource_input_tokens": records["resources"][0]["input_tokens"],
            "resource_success": records["resources"][0]["success"],
            "eos_token_ids": raw["eos_token_ids"],
            "peak_mlx_memory_gib": raw["peak_mlx_memory_gib"],
            "base_admitted": False,
        },
    )


def compare() -> None:
    protocol, _, fixtures = inputs()
    old_source = json.loads(
        (ROOT / ".verity-local/qwen-technical-32case-20261013/raw-source.json").read_bytes()
    )
    old_4bit = json.loads(
        (ROOT / ".verity-local/qwen-technical-32case-20261013/raw-candidate.json").read_bytes()
    )
    runs = []
    for repetition in (1, 2):
        summary = json.loads((HERE / f"diagnostic-{repetition}.json").read_bytes())
        path = PRIVATE / f"diagnostic-{repetition}.json"
        if sha(path) != summary["private_raw_sha256"]:
            raise RuntimeError("diagnostic raw hash changed")
        runs.append(json.loads(path.read_bytes()))
    if runs[0]["eos_token_ids"] != runs[1]["eos_token_ids"] or runs[0]["eos_token_ids"] != sorted(old_source["eos_token_ids"]):
        raise RuntimeError("effective EOS mismatch")
    rows = []
    for group in ("tasks", "stopping", "resources"):
        for index, case in enumerate(fixtures[group]):
            old_a = old_source["records"][group][index]
            old_b = old_4bit["records"][group][index]
            new_a = runs[0]["records"][group][index]
            new_b = runs[1]["records"][group][index]
            if len({x["prompt_sha256"] for x in (old_a, old_b, new_a, new_b)}) != 1 or len({x["token_ids_sha256"] for x in (old_a, old_b, new_a, new_b)}) != 1:
                raise RuntimeError("prompt or tokenizer mismatch: " + case["id"])
            rows.append(
                {
                    "id": case["id"],
                    "group": group,
                    "source_score": old_a.get("score"),
                    "old_4bit_score": old_b.get("score"),
                    "mixed_4_6_score": new_a.get("score"),
                    "new_repeat_response_hash_equal": new_a["response_sha256"] == new_b["response_sha256"],
                    "new_response_sha256": new_a["response_sha256"],
                    "new_finish_reason": new_a["finish_reason"],
                    "new_stopping_exact": new_a.get("expected_exact_match"),
                }
            )
    task_rows = [row for row in rows if row["group"] == "tasks"]
    stop_rows = [row for row in rows if row["group"] == "stopping"]
    score_source = sum(row["source_score"] for row in task_rows)
    score_old = sum(row["old_4bit_score"] for row in task_rows)
    score_new = sum(row["mixed_4_6_score"] for row in task_rows)
    save_new(
        HERE / "diagnostic-verdict.json",
        {
            "classification": "KNOWN_SET_DIAGNOSTIC_NOT_TECHNICAL_ACCEPTANCE",
            "protocol_sha256": sha(HERE / "diagnostic-protocol.json"),
            "candidate_weight_sha256": protocol["candidate_weight_sha256"],
            "scores": {
                "bf16_source": f"{score_source}/32",
                "original_4bit": f"{score_old}/32",
                "mixed_4_6": f"{score_new}/32",
                "mixed_drop_vs_source": (score_source - score_new) / 32,
                "old_limit_for_comparison_only": protocol["old_predeclared_mean_drop_max_for_comparison_only"],
            },
            "stopping_exact": sum(row["new_stopping_exact"] for row in stop_rows),
            "stopping_terminal_stop": sum(row["new_finish_reason"] == "stop" for row in stop_rows),
            "response_repeat_equal": sum(row["new_repeat_response_hash_equal"] for row in rows),
            "response_count": len(rows),
            "literal_reasoning_markers": sum(
                item["reasoning_visible"]
                for group in runs[0]["records"].values()
                for item in group
            ),
            "resource_success": runs[0]["records"]["resources"][0]["success"],
            "resource_input_tokens": runs[0]["records"]["resources"][0]["input_tokens"],
            "peak_mlx_memory_gib": max(run["peak_mlx_memory_gib"] for run in runs),
            "rows": rows,
            "technical_admission": "BLOCKED_KNOWN_SET_AND_NO_INDEPENDENT_ACCEPTANCE",
            "base_admitted": False,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["first", "repeat", "compare"])
    mode = parser.parse_args().mode
    if mode == "compare":
        compare()
    else:
        execute(1 if mode == "first" else 2)


if __name__ == "__main__":
    main()
