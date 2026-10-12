#!/usr/bin/env python3
"""Run a sealed, offline, targeted non-training probe of controlled Qwen 4-bit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
MODEL = ROOT / ".verity-local/qwen3-4b-mlx-controlled-1cfa9a-4bit"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    protocol_bytes = (HERE / "protocol.json").read_bytes()
    protocol = json.loads(protocol_bytes)
    if (HERE / "result.json").exists():
        raise SystemExit("refusing to overwrite result.json")
    if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib"] * 1024**3:
        raise SystemExit("insufficient disk headroom")
    if digest(MODEL / "model.safetensors") != protocol["checkpoint_sha256"]:
        raise SystemExit("controlled checkpoint hash mismatch")
    if os.environ.get("HF_HUB_OFFLINE") != "1" or os.environ.get("TRANSFORMERS_OFFLINE") != "1":
        raise SystemExit("offline environment required")

    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = load(str(MODEL), trust_remote_code=False)
    if tokenizer.eos_token_ids != {151643, 151645}:
        raise SystemExit("unexpected tokenizer stop IDs")
    results: list[dict] = []
    for case in protocol["cases"]:
        if shutil.disk_usage(ROOT).free < protocol["minimum_free_disk_gib"] * 1024**3:
            raise SystemExit("disk headroom fell below guard")
        ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": case["prompt"]}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=case["thinking"],
        )
        start = time.perf_counter()
        pieces = []
        last = None
        for last in stream_generate(
            model,
            tokenizer,
            ids,
            max_tokens=protocol["max_tokens"],
            sampler=make_sampler(temp=0.0),
        ):
            pieces.append(last.text)
        if last is None:
            raise SystemExit(f"empty generation: {case['id']}")
        response = "".join(pieces)
        tags = ("<think>", "</think>", "<|im_start|>", "<|im_end|>")
        record = {
            "id": case["id"],
            "thinking": case["thinking"],
            "prompt_sha256": hashlib.sha256(case["prompt"].encode()).hexdigest(),
            "prompt_tokens": len(ids),
            "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
            "response_text": response if case.get("record_raw_text", True) else None,
            "required_exact_present": {v: v in response for v in case.get("required_exact", [])},
            "required_any_present": any(v in response.casefold() for v in case.get("required_any", [])),
            "exact_match": response.strip() == case["exact"] if "exact" in case else None,
            "visible_tags": [v for v in tags if v in response],
            "finish_reason": last.finish_reason,
            "last_token_id": int(last.token),
            "generation_tokens": last.generation_tokens,
            "elapsed_seconds": round(time.perf_counter() - start, 4),
        }
        results.append(record)
        print(f"{case['id']}: finish={last.finish_reason} token={int(last.token)}", flush=True)
    no_think = [r for r in results if not r["thinking"]]
    checks = {
        "no_thinking_cases_end_with_im_end": all(r["last_token_id"] == 151645 for r in no_think),
        "no_thinking_cases_no_visible_thinking_or_special_tags": all(not r["visible_tags"] for r in no_think),
        "no_thinking_cases_no_length_stop": all(r["finish_reason"] != "length" for r in no_think),
        "peak_mlx_gb_max": round(mx.get_peak_memory() / 1e9, 3)
        <= protocol["predeclared_stopping_checks"]["max_peak_mlx_gb"],
    }
    report = {
        "classification": protocol["classification"],
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "runner_sha256": digest(HERE / "run.py"),
        "checkpoint_sha256": protocol["checkpoint_sha256"],
        "peak_mlx_gb": round(mx.get_peak_memory() / 1e9, 3),
        "free_disk_gib_after": round(shutil.disk_usage(ROOT).free / 1024**3, 3),
        "checks": checks,
        "stopping_screen_pass": all(checks.values()),
        "results": results,
    }
    (HERE / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
