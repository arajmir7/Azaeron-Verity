#!/usr/bin/env python3
"""Sealed, offline BF16-versus-4-bit technical probes; never a release verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / ".verity-local/qwen3-4b-source-1cfa9a"
CANDIDATE = ROOT / ".verity-local/qwen3-4b-mlx-controlled-1cfa9a-4bit"
PRIVATE = ROOT / ".verity-local/qwen-technical-32case-20261013"
SOURCE_HASHES = {
    "README.md": "71add1cd091c309b1cb1a6b943f2476eb2b004124b3bd1d32dcd0b24cc1abc47",
    "config.json": "8ba006f74fecfaaeb392872a60f4a480e7ec9860153d2e1b769ec81f9a147f8a",
    "generation_config.json": "2325da0f15bb848e018c5ae071b7943332e9f871d6b60e2ed22ca97d4cb993d2",
    "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
    "model-00001-of-00003.safetensors": "328a91d3122359d5547f9d79521205bc0a46e1f79a792dfe650e99fc2d651223",
    "model-00002-of-00003.safetensors": "6cd087b316306a68c562436b5492edbcf6e16c6dba3a1308279caa5a58e21ca5",
    "model-00003-of-00003.safetensors": "e4bf436957184f4eeb86a80e9db394503f1f56446b2e6b7edeac5b81470f4ca1",
    "model.safetensors.index.json": "6dc0981b8829fead746441f68f38f24c5ca4a3a66351f652c26c6df0efc43ab2",
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "tokenizer_config.json": "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
    "LICENSE": "832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e",
}
CANDIDATE_HASHES = {
    "README.md": "748c964f9b7e5f2c3770ce013bbc0153be7c54311d9692c343b6188eefe77ac6",
    "chat_template.jinja": "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8",
    "model.safetensors": "55467c6157306f2a4463e9d149b0ed2552943f187778cc67d02e5bef4735773d",
    "tokenizer.json": SOURCE_HASHES["tokenizer.json"],
    "LICENSE": SOURCE_HASHES["LICENSE"],
    "config.json": "c2ec0173d67f0d18cd9e538b4cf19e77b218459a7c108cfa863496bab46661e9",
    "generation_config.json": SOURCE_HASHES["generation_config.json"],
    "model.safetensors.index.json": "8cef64e1365a46469a966601e39615374b753f5deaff953fc3c4d706a8744481",
    "tokenizer_config.json": "5aa5069e1b0c0d623ce38e0df387e506b843e5c4d612a36d2e79e46a400e6450",
}
REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
MANIFEST_SHA256 = "19fe23dd9302d4cb73e8cf9866f42b6a73399c9ec9398c28a340cda1acf1b8ce"
MIN_FREE_GIB = 15


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_new(path: Path, value: dict) -> None:
    if path.exists():
        raise RuntimeError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write("\n")
    if path.is_relative_to(PRIVATE):
        path.chmod(0o600)


def check_free() -> float:
    free_gib = shutil.disk_usage(ROOT).free / (1024**3)
    if free_gib < MIN_FREE_GIB:
        raise RuntimeError(f"disk guard: {free_gib:.2f} GiB free, need {MIN_FREE_GIB}")
    return round(free_gib, 3)


def verify_bundle(directory: Path, expected: dict[str, str]) -> dict[str, str]:
    if directory.is_symlink() or not directory.is_dir() or not directory.is_relative_to(ROOT):
        raise RuntimeError("bundle path is not the controlled local directory")
    actual = {}
    for name, expected_digest in expected.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"missing or linked bundle artifact: {name}")
        actual[name] = sha(path)
        if actual[name] != expected_digest:
            raise RuntimeError(f"artifact digest mismatch: {name}")
    return actual


def verify_seal() -> tuple[dict, dict]:
    seal = json.loads((HERE / "seal.json").read_text())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError(f"sealed input changed: {name}")
    fixture = json.loads((HERE / "fixtures.json").read_text())
    protocol = json.loads((HERE / "protocol.json").read_text())
    if len(fixture["tasks"]) != 32 or len(fixture["stopping"]) != 8:
        raise RuntimeError("unexpected fixture size")
    if protocol["candidate_sha256"] != MANIFEST_SHA256:
        raise RuntimeError("protocol candidate mismatch")
    return fixture, protocol


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().strip('"\'`').rstrip(". ")).casefold()


def score(case: dict, response: str) -> float:
    if case["kind"] == "exact":
        return float(normalize(response) == normalize(case["expected"]))
    return float(
        all(marker in response for marker in case["required"])
        and all(marker not in response for marker in case["forbidden"])
    )


def reasoning_visible(text: str) -> bool:
    return bool(re.search(r"<\s*/?think\s*>|<\|im_start\|>assistant<\|meta_sep\|>analysis", text, flags=re.I))


def generate_case(model, tokenizer, prompt: str, max_tokens: int, sampler) -> dict:
    from mlx_lm import stream_generate

    messages = [{"role": "user", "content": prompt}]
    token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False)
    t0 = time.perf_counter()
    chunks = []
    final = None
    for item in stream_generate(model, tokenizer, token_ids, max_tokens=max_tokens, sampler=sampler):
        chunks.append(item.text)
        final = item
    if final is None or final.finish_reason is None:
        raise RuntimeError("generation ended without terminal response")
    response = "".join(chunks)
    return {
        "prompt_sha256": sha_text(prompt),
        "token_ids_sha256": sha_text(json.dumps(token_ids, separators=(",", ":"))),
        "input_tokens": len(token_ids),
        "response": response,
        "response_sha256": sha_text(response),
        "output_tokens": final.generation_tokens,
        "finish_reason": final.finish_reason,
        "reasoning_visible": reasoning_visible(response),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
        "peak_memory_gib": round(final.peak_memory / (1024**3 / 1e9), 4),
    }


def execute(stage: str) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    if stage not in {"source", "candidate"}:
        raise RuntimeError("invalid stage")
    private_target = PRIVATE / f"raw-{stage}.json"
    summary_target = HERE / f"run-{stage}.json"
    if private_target.exists() or summary_target.exists():
        raise RuntimeError("stage already executed; refusing overwrite")
    fixture, protocol = verify_seal()
    free_before = check_free()
    directory = SOURCE if stage == "source" else CANDIDATE
    actual_hashes = verify_bundle(directory, SOURCE_HASHES if stage == "source" else CANDIDATE_HASHES)
    check_free()

    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(str(directory), trust_remote_code=False)
    sampler = make_sampler(temp=0.0)
    records = {"tasks": [], "stopping": [], "resources": []}
    for case in fixture["tasks"]:
        check_free()
        item = generate_case(model, tokenizer, case["prompt"], 48, sampler)
        item.update(id=case["id"], score=score(case, item["response"]))
        records["tasks"].append(item)
    for case in fixture["stopping"]:
        check_free()
        item = generate_case(model, tokenizer, case["prompt"], 96, sampler)
        item.update(id=case["id"], expected_exact_match=normalize(item["response"]) == normalize(case["expected"]))
        records["stopping"].append(item)
    for case in fixture["resources"]:
        check_free()
        item = generate_case(model, tokenizer, case["prompt"], 32, sampler)
        item.update(id=case["id"], success=item["input_tokens"] >= protocol["context_tokens_min"] and item["finish_reason"] == "stop")
        records["resources"].append(item)
    raw = {
        "stage": stage,
        "source_revision": REVISION,
        "candidate_sha256": MANIFEST_SHA256,
        "protocol_sha256": sha(HERE / "protocol.json"),
        "fixtures_sha256": sha(HERE / "fixtures.json"),
        "artifact_hashes": actual_hashes,
        "free_disk_gib_before": free_before,
        "free_disk_gib_after": check_free(),
        "peak_mlx_memory_gib": round(mx.get_peak_memory() / (1024**3), 4),
        "eos_token_ids": list(tokenizer.eos_token_ids),
        "records": records,
    }
    write_new(private_target, raw)
    summary = {
        key: value for key, value in raw.items() if key != "records"
    }
    summary["private_raw_path"] = str(private_target.relative_to(ROOT))
    summary["private_raw_sha256"] = sha(private_target)
    summary["task_count"] = len(records["tasks"])
    summary["mean_objective_score"] = round(sum(x["score"] for x in records["tasks"]) / len(records["tasks"]), 6)
    summary["stopping_count"] = len(records["stopping"])
    summary["stopping_violations"] = sum(x["finish_reason"] != "stop" for x in records["stopping"])
    summary["reasoning_visible_count"] = sum(x["reasoning_visible"] for group in records.values() for x in group)
    summary["resource_cases"] = [{"id": x["id"], "input_tokens": x["input_tokens"], "success": x["success"], "peak_memory_gib": x["peak_memory_gib"]} for x in records["resources"]]
    write_new(summary_target, summary)


def compare() -> None:
    fixture, protocol = verify_seal()
    source_path = PRIVATE / "raw-source.json"
    candidate_path = PRIVATE / "raw-candidate.json"
    source = json.loads(source_path.read_text())
    candidate = json.loads(candidate_path.read_text())
    for stage, raw, path in (("source", source, source_path), ("candidate", candidate, candidate_path)):
        summary = json.loads((HERE / f"run-{stage}.json").read_text())
        if sha(path) != summary["private_raw_sha256"]:
            raise RuntimeError("private raw output changed")
        if raw["protocol_sha256"] != sha(HERE / "protocol.json"):
            raise RuntimeError("protocol mismatch")
    task_items = []
    for fixture_case, baseline, target in zip(fixture["tasks"], source["records"]["tasks"], candidate["records"]["tasks"], strict=True):
        if fixture_case["id"] != baseline["id"] or fixture_case["id"] != target["id"]:
            raise RuntimeError("task case order mismatch")
        if baseline["prompt_sha256"] != target["prompt_sha256"] or baseline["token_ids_sha256"] != target["token_ids_sha256"]:
            raise RuntimeError("task input/tokenizer mismatch")
        task_items.append({"id": fixture_case["id"], "prompt_sha256": baseline["prompt_sha256"], "baseline_response_sha256": baseline["response_sha256"], "candidate_response_sha256": target["response_sha256"], "baseline_score": baseline["score"], "candidate_score": target["score"]})
    stopping_items = []
    for fixture_case, baseline, target in zip(fixture["stopping"], source["records"]["stopping"], candidate["records"]["stopping"], strict=True):
        if fixture_case["id"] != baseline["id"] or fixture_case["id"] != target["id"]:
            raise RuntimeError("stopping case order mismatch")
        if baseline["prompt_sha256"] != target["prompt_sha256"] or baseline["token_ids_sha256"] != target["token_ids_sha256"]:
            raise RuntimeError("stopping input/tokenizer mismatch")
        stopping_items.append({"id": fixture_case["id"], "prompt_sha256": target["prompt_sha256"], "response_sha256": target["response_sha256"], "finish_reason": target["finish_reason"], "reasoning_visible": target["reasoning_visible"]})
    resources = []
    for fixture_case, baseline, target in zip(fixture["resources"], source["records"]["resources"], candidate["records"]["resources"], strict=True):
        if fixture_case["id"] != baseline["id"] or fixture_case["id"] != target["id"]:
            raise RuntimeError("resource case order mismatch")
        if baseline["prompt_sha256"] != target["prompt_sha256"] or baseline["token_ids_sha256"] != target["token_ids_sha256"]:
            raise RuntimeError("resource input/tokenizer mismatch")
        resources.append({"id": fixture_case["id"], "input_tokens": target["input_tokens"], "peak_memory_gib": target["peak_memory_gib"], "success": target["success"]})
    raw_results = {
        "candidate_sha256": MANIFEST_SHA256,
        "protocol_sha256": sha(HERE / "protocol.json"),
        "baseline_id": protocol["baseline_id"],
        "upstream_revision": REVISION,
        "artifact_hashes": candidate["artifact_hashes"],
        "source_checkpoint_verified": True,
        "tokenizer_verified": True,
        "runtime_conversion_verified": True,
        "tasks": task_items,
        "stopping": stopping_items,
        "resources": resources,
    }
    write_new(HERE / "raw-results.json", raw_results)
    score_source = sum(x["baseline_score"] for x in task_items) / len(task_items)
    score_candidate = sum(x["candidate_score"] for x in task_items) / len(task_items)
    summary = {
        "classification": "NON_TRAINING_TECHNICAL_COMPARISON_ONLY",
        "protocol_sha256": raw_results["protocol_sha256"],
        "raw_results_sha256": sha(HERE / "raw-results.json"),
        "source_private_raw_sha256": sha(source_path),
        "candidate_private_raw_sha256": sha(candidate_path),
        "task_count": len(task_items),
        "source_mean_objective_score": round(score_source, 6),
        "candidate_mean_objective_score": round(score_candidate, 6),
        "candidate_minus_source": round(score_candidate - score_source, 6),
        "candidate_stopping_violations": sum(x["finish_reason"] != "stop" for x in stopping_items),
        "candidate_reasoning_visible_count": sum(x["reasoning_visible"] for x in stopping_items),
        "candidate_peak_mlx_memory_gib": candidate["peak_mlx_memory_gib"],
        "resource_input_tokens": [x["input_tokens"] for x in resources],
        "technical_acceptance": "PENDING_INDEPENDENT_HUMAN_REVIEW",
        "base_admitted": False,
        "production_approved": False,
        "limitations": ["Self-authored objective probes are not blinded quality evaluation.", "Short deterministic outputs do not establish naturalness or commercial model quality.", "Only one Mac/runtime was measured; quantization discrepancies in earlier logits remain.", "Protocol timestamp shows file creation before this run but does not prove external pre-registration."],
    }
    write_new(HERE / "summary.json", summary)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["source", "candidate", "compare"])
    args = parser.parse_args()
    if args.mode == "compare":
        compare()
    else:
        execute(args.mode)


if __name__ == "__main__":
    main()
