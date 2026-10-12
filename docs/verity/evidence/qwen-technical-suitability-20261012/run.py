#!/usr/bin/env python3
"""Offline, self-authored, non-training BF16/quantized compatibility screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
SOURCE = ROOT / ".verity-local/qwen3-4b-source-1cfa9a"
CONVERTED = ROOT / ".verity-local/qwen3-4b-mlx-controlled-1cfa9a-4bit"
MIN_FREE_BYTES = 15 * 1024**3


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed() -> tuple[dict, list[dict]]:
    seal = json.loads((EVIDENCE / "seal.json").read_text())
    for name in ("protocol.json", "fixtures.json", "run.py"):
        if sha256(EVIDENCE / name) != seal["sha256"][name]:
            raise SystemExit(f"sealed artifact changed: {name}")
    return (
        json.loads((EVIDENCE / "protocol.json").read_text()),
        json.loads((EVIDENCE / "fixtures.json").read_text()),
    )


def check_disk() -> float:
    free = shutil.disk_usage(ROOT).free
    if free < MIN_FREE_BYTES:
        raise SystemExit(f"free disk below 15 GiB: {free / 1024**3:.2f} GiB")
    return round(free / 1024**3, 3)


def dump(model_name: str, output: Path) -> None:
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler

    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    protocol, fixtures = sealed()
    model_path = SOURCE if model_name == "source_bf16" else CONVERTED
    if sha256(CONVERTED / "model.safetensors") != protocol["artifacts"]["converted_checkpoint_sha256"]:
        raise SystemExit("converted checkpoint hash changed")
    free_before = check_disk()
    model, tokenizer = load(str(model_path), trust_remote_code=False)
    if tokenizer.eos_token_ids != {151643, 151645}:
        raise SystemExit(f"unexpected tokenizer stop ids: {tokenizer.eos_token_ids}")
    rows = []
    for fixture in fixtures:
        check_disk()
        ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": fixture["prompt"]}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        start = time.perf_counter()
        first_token = None
        first_content = None
        chunks = []
        last = None
        for result in stream_generate(
            model,
            tokenizer,
            ids,
            max_tokens=protocol["generation"]["max_tokens_per_item"],
            sampler=make_sampler(temp=0.0),
        ):
            now = time.perf_counter()
            if first_token is None:
                first_token = now - start
            if result.text and first_content is None:
                first_content = now - start
            chunks.append(result.text)
            last = result
        if last is None:
            raise RuntimeError("no generation result")
        rows.append(
            {
                "id": fixture["id"],
                "prompt_sha256": hashlib.sha256(fixture["prompt"].encode()).hexdigest(),
                "token_ids_sha256": hashlib.sha256(
                    json.dumps(ids, separators=(",", ":")).encode()
                ).hexdigest(),
                "prompt_tokens": len(ids),
                "text": "".join(chunks),
                "first_token_seconds": round(first_token, 4),
                "first_content_seconds": round(first_content, 4) if first_content else None,
                "elapsed_seconds": round(time.perf_counter() - start, 4),
                "generation_tokens": last.generation_tokens,
                "generation_tps": round(last.generation_tps, 3),
                "peak_mlx_gb": round(last.peak_memory, 3),
                "finish_reason": last.finish_reason,
                "last_token_id": int(last.token),
            }
        )
        print(f"{model_name}: {fixture['id']} complete; free={check_disk()} GiB", flush=True)
    repeat = None
    if model_name == "source_bf16":
        first = fixtures[0]
        ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": first["prompt"]}],
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        repeat = "".join(
            result.text
            for result in stream_generate(
                model, tokenizer, ids, max_tokens=96, sampler=make_sampler(temp=0.0)
            )
        )
    report = {
        "classification": protocol["classification"],
        "model_name": model_name,
        "model_path": str(model_path.relative_to(ROOT)),
        "seal_sha256": sha256(EVIDENCE / "seal.json"),
        "free_disk_gib_before": free_before,
        "free_disk_gib_after": check_disk(),
        "mlx_peak_gb": round(mx.get_peak_memory() / 1e9, 3),
        "eos_token_ids": sorted(tokenizer.eos_token_ids),
        "source_first_case_repeat_equal": repeat == rows[0]["text"] if repeat is not None else None,
        "rows": rows,
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


def score(fixture: dict, text: str) -> dict:
    lower = text.casefold()
    required_missing = [v for v in fixture.get("required", []) if v.casefold() not in lower]
    any_present = any(v.casefold() in lower for v in fixture.get("required_any", []))
    any_missing = bool(fixture.get("required_any")) and not any_present
    forbidden_found = [v for v in fixture.get("forbidden", []) if v.casefold() in lower]
    exact = fixture.get("exact")
    exact_mismatch = exact is not None and text.strip() != exact
    json_error = None
    if fixture.get("json_object"):
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                json_error = "not_an_object"
        except json.JSONDecodeError:
            json_error = "invalid_json"
    thinking_leak = any(v in text for v in ("<think>", "</think>", "<|im_start|>", "<|im_end|>"))
    return {
        "pass": not (required_missing or any_missing or forbidden_found or exact_mismatch or json_error or thinking_leak),
        "required_missing": required_missing,
        "required_any_missing": any_missing,
        "forbidden_found": forbidden_found,
        "exact_mismatch": exact_mismatch,
        "json_error": json_error,
        "thinking_or_special_token_leak": thinking_leak,
    }


def compare(source_path: Path, converted_path: Path, output: Path) -> None:
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    protocol, fixtures = sealed()
    left = json.loads(source_path.read_text())
    right = json.loads(converted_path.read_text())
    if (
        left["seal_sha256"] != right["seal_sha256"]
        or left["seal_sha256"] != sha256(EVIDENCE / "seal.json")
    ):
        raise SystemExit("inconsistent seal")
    if len(left["rows"]) != len(fixtures) or len(right["rows"]) != len(fixtures):
        raise SystemExit("case count mismatch")
    rows = []
    for fixture, a, b in zip(fixtures, left["rows"], right["rows"], strict=True):
        if (
            a["id"] != b["id"]
            or a["id"] != fixture["id"]
            or a["prompt_sha256"] != b["prompt_sha256"]
        ):
            raise SystemExit("case mismatch")
        if a["token_ids_sha256"] != b["token_ids_sha256"]:
            raise SystemExit(f"chat-template tokens differ: {fixture['id']}")
        rows.append(
            {
                "id": fixture["id"],
                "task": fixture["task"],
                "critical": fixture["critical"],
                "source": score(fixture, a["text"]),
                "controlled": score(fixture, b["text"]),
                "source_text": a["text"],
                "controlled_text": b["text"],
                "source_finish": a["finish_reason"],
                "controlled_finish": b["finish_reason"],
                "controlled_last_token_id": b["last_token_id"],
            }
        )
    n_source_pass = sum(v["source"]["pass"] for v in rows)
    n_both_pass = sum(v["source"]["pass"] and v["controlled"]["pass"] for v in rows)
    new_critical = sum(v["critical"] and v["source"]["pass"] and not v["controlled"]["pass"] for v in rows)
    warm = [v["first_token_seconds"] for v in right["rows"][1:]]
    ordered_warm = sorted(warm)
    p95 = ordered_warm[min(len(warm) - 1, int(0.95 * len(warm) + 0.999999) - 1)]
    metrics = {
        "source_task_pass_fraction": round(n_source_pass / len(rows), 4),
        "controlled_task_pass_given_source_pass_fraction": round(n_both_pass / n_source_pass, 4) if n_source_pass else 0,
        "controlled_new_critical_fact_or_injection_errors": new_critical,
        "unexpected_thinking_or_special_token_leaks": sum(v["controlled"]["thinking_or_special_token_leak"] for v in rows),
        "unexpected_endoftext_stops": sum(v["controlled_last_token_id"] == 151643 for v in rows),
        "length_stops": sum(v["controlled_finish"] == "length" for v in rows),
        "controlled_peak_mlx_gb": right["mlx_peak_gb"],
        "controlled_warm_first_token_p95_seconds": p95,
        "controlled_median_decode_tokens_per_second": round(statistics.median(v["generation_tps"] for v in right["rows"]), 3),
        "minimum_free_disk_gib": min(left["free_disk_gib_after"], right["free_disk_gib_after"]),
    }
    thresholds = protocol["predeclared_engineering_screen"]
    checks = {
        "source_task_pass_fraction_min": metrics["source_task_pass_fraction"] >= thresholds["source_task_pass_fraction_min"],
        "controlled_task_pass_given_source_pass_fraction_min": metrics["controlled_task_pass_given_source_pass_fraction"] >= thresholds["controlled_task_pass_given_source_pass_fraction_min"],
        "controlled_new_critical_fact_or_injection_errors_max": metrics["controlled_new_critical_fact_or_injection_errors"] <= thresholds["controlled_new_critical_fact_or_injection_errors_max"],
        "unexpected_thinking_or_special_token_leaks_max": metrics["unexpected_thinking_or_special_token_leaks"] <= thresholds["unexpected_thinking_or_special_token_leaks_max"],
        "unexpected_endoftext_stops_max": metrics["unexpected_endoftext_stops"] <= thresholds["unexpected_endoftext_stops_max"],
        "length_stops_max": metrics["length_stops"] <= thresholds["length_stops_max"],
        "controlled_peak_mlx_gb_max": metrics["controlled_peak_mlx_gb"] <= thresholds["controlled_peak_mlx_gb_max"],
        "controlled_warm_first_token_p95_seconds_max": metrics["controlled_warm_first_token_p95_seconds"] <= thresholds["controlled_warm_first_token_p95_seconds_max"],
        "controlled_median_decode_tokens_per_second_min": metrics["controlled_median_decode_tokens_per_second"] >= thresholds["controlled_median_decode_tokens_per_second_min"],
        "minimum_free_disk_gib": metrics["minimum_free_disk_gib"] >= thresholds["minimum_free_disk_gib"],
        "same_chat_template_token_ids": True,
        "source_first_case_repeat_equal": left["source_first_case_repeat_equal"] is True,
    }
    result = {
        "classification": protocol["classification"],
        "seal_sha256": sha256(EVIDENCE / "seal.json"),
        "metrics": metrics,
        "checks": checks,
        "screen_pass": all(checks.values()),
        "rows": rows,
        "limitation": "Self-authored objective-marker screen, not commercial data, human quality review, legal admission, or proof of semantic/logit equivalence.",
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("source_bf16", "controlled_4bit"):
        p = sub.add_parser(name)
        p.add_argument("--output", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--converted", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "compare":
        compare(args.source, args.converted, args.output)
    else:
        dump(args.mode, args.output)
