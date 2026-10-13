#!/usr/bin/env python3
"""Trace original failed prompts without changing their sealed benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINAL = HERE.parent / "qwen-technical-32case-20261013"
PRIVATE = ROOT / ".verity-local/qwen-root-cause-20261013"
BUNDLES = {
    "source": ROOT / ".verity-local/qwen3-4b-source-1cfa9a",
    "candidate": ROOT / ".verity-local/qwen3-4b-mlx-controlled-1cfa9a-4bit",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def save_new(path: Path, value: dict, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def inputs() -> tuple[dict, dict]:
    seal = json.loads((HERE / "seal.json").read_bytes())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError("new diagnostic seal mismatch: " + name)
    protocol = json.loads((HERE / "protocol.json").read_bytes())
    for name, key in (
        ("seal.json", "original_seal_sha256"),
        ("fixtures.json", "original_fixtures_sha256"),
        ("run-source.json", "original_run_source_sha256"),
        ("run-candidate.json", "original_run_candidate_sha256"),
    ):
        if sha(ORIGINAL / name) != protocol[key]:
            raise RuntimeError("original sealed input mismatch: " + name)
    original_seal = json.loads((ORIGINAL / "seal.json").read_bytes())
    for name, expected in original_seal["input_sha256"].items():
        if sha(ORIGINAL / name) != expected:
            raise RuntimeError("original benchmark seal mismatch: " + name)
    for stage in BUNDLES:
        old_summary = json.loads((ORIGINAL / f"run-{stage}.json").read_bytes())
        old_raw = (
            ROOT / ".verity-local/qwen-technical-32case-20261013" / f"raw-{stage}.json"
        )
        if (
            sha(old_raw) != old_summary["private_raw_sha256"]
            or old_summary["candidate_sha256"] != protocol["candidate_manifest_sha256"]
        ):
            raise RuntimeError("original benchmark raw or candidate mismatch")
    if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib"] * 1024**3:
        raise RuntimeError("disk headroom below sealed minimum")
    return protocol, json.loads((ORIGINAL / "fixtures.json").read_bytes())


def execute(stage: str) -> None:
    if stage not in BUNDLES:
        raise ValueError("unknown stage")
    protocol, fixtures = inputs()
    summary = json.loads((ORIGINAL / f"run-{stage}.json").read_bytes())
    bundle = BUNDLES[stage]
    if bundle.is_symlink():
        raise RuntimeError("symlink bundle rejected")
    for name, expected in summary["artifact_hashes"].items():
        path = bundle / name
        if path.is_symlink() or sha(path) != expected:
            raise RuntimeError("bundle hash mismatch: " + name)
    if (PRIVATE / f"raw-{stage}.json").exists() or (
        HERE / f"run-{stage}.json"
    ).exists():
        raise RuntimeError("refusing to overwrite executed diagnostic")

    os.environ.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
    )
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(str(bundle), trust_remote_code=False)
    sampler = make_sampler(temp=0.0)
    by_id = {item["id"]: ("tasks", item) for item in fixtures["tasks"]}
    by_id.update({item["id"]: ("stopping", item) for item in fixtures["stopping"]})
    records = []
    for case_id in protocol["diagnostic_case_ids"] + protocol["controls"]:
        if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib"] * 1024**3:
            raise RuntimeError("disk headroom fell below minimum")
        kind, case = by_id[case_id]
        ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": case["prompt"]}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        started = time.perf_counter()
        tokens: list[int] = []
        chunks: list[str] = []
        final = None
        limit = (
            protocol["max_tokens_task"]
            if kind == "tasks"
            else protocol["max_tokens_stopping"]
        )
        for item in stream_generate(
            model, tokenizer, ids, max_tokens=limit, sampler=sampler
        ):
            tokens.append(item.token)
            chunks.append(item.text)
            final = item
        if final is None or final.finish_reason is None:
            raise RuntimeError("generation did not terminate")
        response = "".join(chunks)
        records.append(
            {
                "id": case_id,
                "kind": kind,
                "prompt_sha256": text_sha(case["prompt"]),
                "prompt_token_ids_sha256": text_sha(
                    json.dumps(ids, separators=(",", ":"))
                ),
                "tokens": tokens,
                "response": response,
                "response_sha256": text_sha(response),
                "finish_reason": final.finish_reason,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        )
    raw = {
        "stage": stage,
        "protocol_sha256": sha(HERE / "protocol.json"),
        "model_class": type(model).__module__ + "." + type(model).__name__,
        "projection_class": type(model.model.layers[0].self_attn.q_proj).__module__
        + "."
        + type(model.model.layers[0].self_attn.q_proj).__name__,
        "eos_token_ids": sorted(tokenizer.eos_token_ids),
        "peak_mlx_memory_gib": round(mx.get_peak_memory() / 1024**3, 4),
        "records": records,
    }
    private_path = PRIVATE / f"raw-{stage}.json"
    save_new(private_path, raw, private=True)
    save_new(
        HERE / f"run-{stage}.json",
        {
            "stage": stage,
            "protocol_sha256": raw["protocol_sha256"],
            "private_raw_sha256": sha(private_path),
            "record_count": len(records),
            "eos_token_ids": raw["eos_token_ids"],
            "model_class": raw["model_class"],
            "projection_class": raw["projection_class"],
            "peak_mlx_memory_gib": raw["peak_mlx_memory_gib"],
        },
    )


def compare() -> None:
    protocol, fixtures = inputs()
    originals = {
        stage: json.loads(
            (
                ROOT
                / ".verity-local/qwen-technical-32case-20261013"
                / f"raw-{stage}.json"
            ).read_bytes()
        )
        for stage in BUNDLES
    }
    runs = {}
    for stage in BUNDLES:
        path = PRIVATE / f"raw-{stage}.json"
        summary = json.loads((HERE / f"run-{stage}.json").read_bytes())
        if sha(path) != summary["private_raw_sha256"]:
            raise RuntimeError("diagnostic raw hash mismatch")
        runs[stage] = json.loads(path.read_bytes())
    left, right = runs["source"], runs["candidate"]
    if (
        left["eos_token_ids"] != right["eos_token_ids"]
        or left["model_class"] != right["model_class"]
    ):
        raise RuntimeError("different effective EOS or model implementation")
    by_id = {
        item["id"]: item
        for group in (fixtures["tasks"], fixtures["stopping"])
        for item in group
    }
    rows = []
    for a, b in zip(left["records"], right["records"], strict=True):
        if (
            a["id"] != b["id"]
            or a["prompt_token_ids_sha256"] != b["prompt_token_ids_sha256"]
        ):
            raise RuntimeError("different diagnostic prompt tokenization")
        case_id = a["id"]
        case = by_id[case_id]
        old_group = "tasks" if a["kind"] == "tasks" else "stopping"
        for stage, current in (("source", a), ("candidate", b)):
            old = next(
                item
                for item in originals[stage]["records"][old_group]
                if item["id"] == case_id
            )
            if current["response_sha256"] != old["response_sha256"]:
                raise RuntimeError(
                    "repeat output differs from sealed failure: "
                    + case_id
                    + " "
                    + stage
                )
        prefix = 0
        for token_a, token_b in zip(a["tokens"], b["tokens"]):
            if token_a != token_b:
                break
            prefix += 1
        rows.append(
            {
                "id": case_id,
                "prompt_sha256": text_sha(case["prompt"]),
                "same_prompt_token_ids": True,
                "same_effective_eos_ids": True,
                "same_visible_responses_as_sealed_run": True,
                "first_different_token_index": (
                    prefix if a["tokens"] != b["tokens"] else None
                ),
                "first_different_token_ids": (
                    [a["tokens"][prefix], b["tokens"][prefix]]
                    if prefix < min(len(a["tokens"]), len(b["tokens"]))
                    else None
                ),
                "source_finish_reason": a["finish_reason"],
                "candidate_finish_reason": b["finish_reason"],
            }
        )
    save_new(
        HERE / "diagnosis.json",
        {
            "classification": "REPEATED_OFFLINE_DIAGNOSTIC_NOT_ADMISSION",
            "protocol_sha256": sha(HERE / "protocol.json"),
            "source_raw_sha256": sha(PRIVATE / "raw-source.json"),
            "candidate_raw_sha256": sha(PRIVATE / "raw-candidate.json"),
            "effective_eos_token_ids": left["eos_token_ids"],
            "model_class": left["model_class"],
            "source_projection_class": left["projection_class"],
            "candidate_projection_class": right["projection_class"],
            "rows": rows,
            "original_failure_preserved": True,
            "base_admitted": False,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["source", "candidate", "compare"])
    mode = parser.parse_args().mode
    if mode == "compare":
        compare()
    else:
        execute(mode)


if __name__ == "__main__":
    main()
