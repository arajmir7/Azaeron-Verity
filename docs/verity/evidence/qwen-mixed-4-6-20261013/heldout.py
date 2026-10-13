#!/usr/bin/env python3
"""Offline sealed independent technical comparison; keeps responses private."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
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


def save_new(path: Path, data: dict, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def load_inputs() -> tuple[dict, dict, dict]:
    seal = json.loads((HERE / "heldout-seal.json").read_bytes())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError("heldout seal mismatch: " + name)
    protocol = json.loads((HERE / "heldout-protocol.json").read_bytes())
    for path, key in (
        (HERE / "conversion-result.json", "conversion_result_sha256"),
        (HERE / "heldout-fixtures.json", "fixture_sha256"),
        (OLD / "fixtures.json", "old_fixture_sha256"),
        (OLD / "benchmark.py", "original_scorer_sha256"),
    ):
        if sha(path) != protocol[key]:
            raise RuntimeError("bound input changed: " + key)
    fixture = json.loads((HERE / "heldout-fixtures.json").read_bytes())
    old = json.loads((OLD / "fixtures.json").read_bytes())
    for group, size in (("tasks", 32), ("stopping", 8), ("resources", 1)):
        if len(fixture[group]) != size:
            raise RuntimeError("heldout case count changed")
    norm = lambda text: re.sub(r"\s+", " ", text.strip()).casefold()
    old_prompts = {norm(c["prompt"]) for group in ("tasks", "stopping", "resources") for c in old[group]}
    cases = [c for group in ("tasks", "stopping", "resources") for c in fixture[group]]
    new_prompts = [norm(c["prompt"]) for c in cases]
    if len(set(new_prompts)) != len(cases) or old_prompts.intersection(new_prompts):
        raise RuntimeError("heldout prompt leakage")
    conversion = json.loads((HERE / "conversion-result.json").read_bytes())
    if conversion["files"]["model.safetensors"]["sha256"] != protocol["candidate_weight_sha256"]:
        raise RuntimeError("candidate weight identity changed")
    return protocol, fixture, conversion


def load_scorer():
    spec = importlib.util.spec_from_file_location("original_sealed_scorer", OLD / "benchmark.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("scorer unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_artifacts(stage: str, conversion: dict) -> Path:
    scorer = load_scorer()
    if stage == "source":
        directory = scorer.SOURCE
        expected = conversion["source_artifact_hashes"]
    else:
        directory = ROOT / conversion["output_relative_path"]
        expected = {name: value["sha256"] for name, value in conversion["files"].items()}
    if directory.is_symlink() or not directory.is_dir():
        raise RuntimeError("missing or linked controlled bundle")
    for name, digest in expected.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise RuntimeError("bundle artifact mismatch: " + name)
    return directory


def run(stage: str) -> None:
    protocol, fixture, conversion = load_inputs()
    if stage not in ("source", "candidate", "candidate-repeat"):
        raise ValueError(stage)
    raw_path = PRIVATE / f"heldout-{stage}.json"
    summary_path = HERE / f"heldout-{stage}.json"
    if raw_path.exists() or summary_path.exists():
        raise RuntimeError("refusing to overwrite heldout run")
    if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib_before"] * 1024**3:
        raise RuntimeError("insufficient free disk before heldout run")
    directory = verify_artifacts("source" if stage == "source" else "candidate", conversion)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1")
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.sample_utils import make_sampler

    scorer = load_scorer()
    model, tokenizer = load(str(directory), trust_remote_code=False)
    sampler = make_sampler(temp=0.0)
    records: dict[str, list[dict]] = {"tasks": [], "stopping": [], "resources": []}
    for group, cap in (("tasks", "task_max_tokens"), ("stopping", "stopping_max_tokens"), ("resources", "resource_max_tokens")):
        for case in fixture[group]:
            if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib_during"] * 1024**3:
                raise RuntimeError("disk headroom fell below heldout guard")
            item = scorer.generate_case(model, tokenizer, case["prompt"], protocol[cap], sampler)
            item["id"] = case["id"]
            if group == "tasks":
                item["score"] = scorer.score(case, item["response"])
            elif group == "stopping":
                item["exact"] = scorer.normalize(item["response"]) == scorer.normalize(case["expected"])
            else:
                item["success"] = item["input_tokens"] >= protocol["minimum_resource_input_tokens"] and item["finish_reason"] == "stop"
            records[group].append(item)
    raw = {
        "stage": stage,
        "protocol_sha256": sha(HERE / "heldout-protocol.json"),
        "fixtures_sha256": protocol["fixture_sha256"],
        "model_weight_sha256": protocol["candidate_weight_sha256"] if stage != "source" else None,
        "eos_token_ids": sorted(tokenizer.eos_token_ids),
        "peak_mlx_memory_gib": round(mx.get_peak_memory() / 1024**3, 4),
        "records": records,
    }
    save_new(raw_path, raw, private=True)
    save_new(summary_path, {
        "classification": "HELDOUT_TECHNICAL_PROBE_NOT_WRITING_QUALITY",
        "stage": stage,
        "private_raw_sha256": sha(raw_path),
        "protocol_sha256": raw["protocol_sha256"],
        "task_score": sum(item["score"] for item in records["tasks"]),
        "stopping_exact": sum(item["exact"] for item in records["stopping"]),
        "stopping_terminal_stop": sum(item["finish_reason"] == "stop" for item in records["stopping"]),
        "invariant_scores": sum(item["score"] for item in records["tasks"] if item["id"].startswith("H-P")),
        "visible_reasoning_markers": sum(item["reasoning_visible"] for group in records.values() for item in group),
        "resource_success": records["resources"][0]["success"],
        "resource_input_tokens": records["resources"][0]["input_tokens"],
        "peak_mlx_memory_gib": raw["peak_mlx_memory_gib"],
        "eos_token_ids": raw["eos_token_ids"],
        "owner_approval": "NOT_REQUESTED_FOR_THIS_ARTIFACT",
    })


def compare() -> None:
    protocol, fixture, _ = load_inputs()
    if (HERE / "heldout-verdict.json").exists():
        raise RuntimeError("refusing to overwrite heldout verdict")
    runs = {}
    summaries = {}
    for stage in ("source", "candidate", "candidate-repeat"):
        summary = json.loads((HERE / f"heldout-{stage}.json").read_bytes())
        path = PRIVATE / f"heldout-{stage}.json"
        if sha(path) != summary["private_raw_sha256"]:
            raise RuntimeError("private raw hash changed")
        runs[stage] = json.loads(path.read_bytes())
        summaries[stage] = summary
    eos = [runs[stage]["eos_token_ids"] for stage in runs]
    if not all(value == eos[0] for value in eos):
        raise RuntimeError("effective EOS differed")
    rows = []
    for group in ("tasks", "stopping", "resources"):
        for index, case in enumerate(fixture[group]):
            items = [runs[stage]["records"][group][index] for stage in runs]
            if any(item["id"] != case["id"] for item in items):
                raise RuntimeError("case order differed")
            if len({item["prompt_sha256"] for item in items}) != 1 or len({item["token_ids_sha256"] for item in items}) != 1:
                raise RuntimeError("prompt or tokenizer mismatch: " + case["id"])
            rows.append({
                "id": case["id"], "group": group,
                "source_score": items[0].get("score"), "candidate_score": items[1].get("score"),
                "candidate_repeat_equal": items[1]["response_sha256"] == items[2]["response_sha256"],
                "candidate_response_sha256": items[1]["response_sha256"],
                "candidate_finish_reason": items[1]["finish_reason"],
                "candidate_stopping_exact": items[1].get("exact"),
            })
    source_score = summaries["source"]["task_score"]
    candidate_score = summaries["candidate"]["task_score"]
    repeat_score = summaries["candidate-repeat"]["task_score"]
    conditions = {
        "score_drop": (source_score - candidate_score) / 32 <= protocol["maximum_score_drop_fraction_of_32"],
        "candidate_score_floor": candidate_score / 32 >= protocol["minimum_candidate_score_fraction"],
        "all_stopping_exact": summaries["candidate"]["stopping_exact"] == protocol["required_stopping_exact"],
        "all_stopping_terminal": summaries["candidate"]["stopping_terminal_stop"] == protocol["required_stopping_terminal_stop"],
        "all_invariants": summaries["candidate"]["invariant_scores"] == protocol["required_invariant_scores"],
        "memory": summaries["candidate"]["peak_mlx_memory_gib"] <= protocol["maximum_candidate_peak_mlx_gib"],
        "reasoning_hidden": summaries["candidate"]["visible_reasoning_markers"] <= protocol["maximum_visible_reasoning_markers"],
        "resource": summaries["candidate"]["resource_success"] is protocol["required_resource_success"],
        "repeat": all(row["candidate_repeat_equal"] for row in rows) and repeat_score == candidate_score,
    }
    save_new(HERE / "heldout-verdict.json", {
        "classification": "INDEPENDENT_TECHNICAL_HELDOUT_NOT_HUMAN_QUALITY_OR_RELEASE",
        "protocol_sha256": sha(HERE / "heldout-protocol.json"),
        "fixture_sha256": protocol["fixture_sha256"],
        "candidate_weight_sha256": protocol["candidate_weight_sha256"],
        "score_source": f"{source_score}/32", "score_candidate": f"{candidate_score}/32",
        "score_candidate_repeat": f"{repeat_score}/32",
        "score_drop_fraction": (source_score - candidate_score) / 32,
        "stopping_exact": summaries["candidate"]["stopping_exact"],
        "stopping_terminal_stop": summaries["candidate"]["stopping_terminal_stop"],
        "invariant_scores": summaries["candidate"]["invariant_scores"],
        "candidate_peak_mlx_memory_gib": summaries["candidate"]["peak_mlx_memory_gib"],
        "resource_input_tokens": summaries["candidate"]["resource_input_tokens"],
        "response_repeat_equal": sum(row["candidate_repeat_equal"] for row in rows),
        "conditions": conditions,
        "technical_result": "PASS" if all(conditions.values()) else "FAIL",
        "owner_approval_for_this_artifact": "NOT_REQUESTED",
        "training_data_admitted_rows": 0,
        "rows": rows,
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["source", "candidate", "candidate-repeat", "compare"])
    stage = parser.parse_args().stage
    if stage == "compare":
        compare()
    else:
        run(stage)


if __name__ == "__main__":
    main()
