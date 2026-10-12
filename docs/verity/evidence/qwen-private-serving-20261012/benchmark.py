"""Bounded DEV_ONLY localhost benchmark for the hash-verified controlled Qwen bundle.

Run ``prepare`` and commit its seal before starting the model server. ``run``
stores only timings, token counts, response hashes, and small environment facts.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
MODEL = ROOT / ".verity-local/qwen3-4b-mlx-controlled-1cfa9a-4bit"
EXPECTED_WEIGHT_SHA = "55467c6157306f2a4463e9d149b0ed2552943f187778cc67d02e5bef4735773d"
ENDPOINT = "http://127.0.0.1:18080"
FIXTURES = HERE / "fixtures.json"
SEAL = HERE / "seal.json"
RESULT = HERE / "result.json"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fixtures() -> dict:
    # Original, non-customer strings, fixed before execution. Deliberately short.
    prompts = [
        "Reply with one sentence explaining why a document citation is useful.",
        "Rewrite without changing facts: Mira Shah submitted 17 forms on 6 August 2024.",
        "Summarize in one sentence: The library opened on 4 June 2023. It has 24 desks. It closes on Mondays.",
        "Answer using only this source: Document R4 states that 29 visits occurred on 8 May 2024. How many visits occurred?",
        "Explain in one sentence why an absent source fact should remain unknown.",
        "Rewrite without changing facts: Noor Sen did not approve the 12-item request [1].",
        "Summarize in one sentence: Report R7 lists 15 visits and 2 cancellations. No breach was recorded.",
        "Answer using only this source: Record R8 reports 31 books returned. How many books were returned?",
        "Explain in one sentence what a reversible edit means for document history.",
        "Rewrite without changing facts: On 9 July 2024, Ira Mehta paid 42 rupees [2].",
        "Summarize in one sentence: Document R11 was signed on 3 March 2022. The approved total was 18 units.",
        "Answer using only this source: Note R12 says the meeting happened on 5 April 2024. When did it happen?",
    ]
    return {
        "classification": "DEV_ONLY_ORIGINAL_SYNTHETIC_PERFORMANCE_ONLY",
        "endpoint": ENDPOINT,
        "model_path": str(MODEL),
        "weight_sha256": EXPECTED_WEIGHT_SHA,
        "server_flags": {
            "host": "127.0.0.1", "port": 18080,
            "chat_template_args": {"enable_thinking": False},
            "max_tokens": 64, "prompt_cache_size": 0,
            "decode_concurrency": 1, "prompt_concurrency": 1,
        },
        "warmup": 2,
        "serial": [{"id": f"serial-{i + 1:02d}", "prompt": p} for i, p in enumerate(prompts)],
        "concurrency": [
            {"parallel": 2, "rounds": 4, "prompt_indices": [0, 3]},
            {"parallel": 4, "rounds": 2, "prompt_indices": [1, 4, 7, 10]},
        ],
        "error_recovery": "POST missing required messages, then one valid streamed request",
        "cancel_recovery": "Close one stream after first visible delta, then one valid streamed request",
        "generation": {"stream": True, "temperature": 0, "max_tokens": 64, "timeout_seconds": 45},
        "minimum_free_disk_gib": 15,
        "maximum_physical_ram_gib": 16,
        "no_external_inference": True,
        "no_training": True,
        "no_release_certification": True,
    }


def prepare() -> None:
    if FIXTURES.exists() or SEAL.exists() or RESULT.exists():
        raise SystemExit("Existing benchmark file; refusing overwrite")
    FIXTURES.write_text(json.dumps(fixtures(), indent=2) + "\n")
    SEAL.write_text(json.dumps({
        "fixture_sha256": digest(FIXTURES),
        "scoring_code_sha256": digest(Path(__file__)),
        "pre_execution": True,
    }, indent=2) + "\n")
    print(json.dumps({"fixture_sha256": digest(FIXTURES), "seal_sha256": digest(SEAL)}))


def check_seal() -> dict:
    seal = json.loads(SEAL.read_text())
    if digest(FIXTURES) != seal["fixture_sha256"] or digest(Path(__file__)) != seal["scoring_code_sha256"]:
        raise SystemExit("Pre-execution seal mismatch")
    if RESULT.exists():
        raise SystemExit("Existing results; refusing overwrite")
    return json.loads(FIXTURES.read_text())


def post_json(path: str, payload: dict, *, timeout: int = 45) -> urllib.response.addinfourl:
    request = urllib.request.Request(
        ENDPOINT + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return OPENER.open(request, timeout=timeout)


def get_model_id() -> str:
    with OPENER.open(ENDPOINT + "/v1/models", timeout=5) as response:
        body = json.load(response)
    ids = [entry.get("id") for entry in body.get("data", [])]
    if len(ids) != 1 or ids[0] != str(MODEL):
        raise SystemExit(f"Unexpected serving identity: {ids!r}")
    return ids[0]


def request(model_id: str, prompt: str, *, cancel: bool = False) -> dict:
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Answer briefly. Do not reveal private reasoning."},
            {"role": "user", "content": prompt},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "temperature": 0,
        "max_tokens": 64,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    start = time.monotonic()
    first = None
    parts = []
    usage = None
    finish = None
    status = None
    with post_json("/v1/chat/completions", payload) as response:
        status = response.status
        for raw in response:
            if not raw.startswith(b"data: "):
                continue
            line = raw[6:].strip()
            if line == b"[DONE]":
                break
            event = json.loads(line)
            if event.get("model") != model_id:
                raise RuntimeError("Response model identity mismatch")
            if event.get("usage") is not None:
                usage = event["usage"]
            for choice in event.get("choices", []):
                delta = choice.get("delta") or {}
                content = delta.get("content") or ""
                if content:
                    if first is None:
                        first = time.monotonic()
                    parts.append(content)
                    if cancel:
                        return {"status": status, "first_visible_ms": round((first - start) * 1000, 2), "closed_after_first_delta": True}
                if choice.get("finish_reason") is not None:
                    finish = choice["finish_reason"]
    end = time.monotonic()
    text = "".join(parts)
    tokens = (usage or {}).get("completion_tokens")
    decode_seconds = end - first if first is not None else None
    return {
        "status": status,
        "first_visible_ms": round((first - start) * 1000, 2) if first else None,
        "end_to_end_ms": round((end - start) * 1000, 2),
        "prompt_tokens": (usage or {}).get("prompt_tokens"),
        "completion_tokens": tokens,
        "cached_tokens": ((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
        "decode_tokens_per_second_approx": round((tokens - 1) / decode_seconds, 2) if tokens and tokens > 1 and decode_seconds and decode_seconds > 0 else None,
        "finish_reason": finish,
        "response_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "reasoning_marker_visible": "<think>" in text or "</think>" in text,
    }


def p95(values: list[float]) -> float | None:
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else None


def memory(pid: int) -> dict:
    result = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True, timeout=25)
    return {
        "status": "MEASURED" if result.returncode == 0 else "UNAVAILABLE",
        "lines": [line.strip() for line in result.stdout.splitlines() if line.strip().startswith(("phys_footprint:", "phys_footprint_peak:"))][:4],
    }


def run(pid: int) -> None:
    config = check_seal()
    free_gib = int(subprocess.check_output(["df", "-k", str(ROOT)], text=True).splitlines()[1].split()[3]) / (1024 * 1024)
    ram = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)) / 1024**3
    if free_gib < config["minimum_free_disk_gib"] or ram > config["maximum_physical_ram_gib"] + 0.1:
        raise SystemExit("Hardware guard failed")
    if digest(MODEL / "model.safetensors") != EXPECTED_WEIGHT_SHA:
        raise SystemExit("Controlled checkpoint hash mismatch")
    command = subprocess.check_output(["ps", "-o", "command=", "-p", str(pid)], text=True).strip()
    if "mlx_lm server" not in command or str(MODEL) not in command or "--host 127.0.0.1" not in command or "--port 18080" not in command:
        raise SystemExit("Unrecognized serving process")
    model_id = get_model_id()
    before = memory(pid)
    for i in range(config["warmup"]):
        request(model_id, config["serial"][i]["prompt"])
    serial = []
    for case in config["serial"]:
        row = request(model_id, case["prompt"])
        serial.append({"id": case["id"], **row})
        print(f"{case['id']} {row['end_to_end_ms']} ms", flush=True)
    concurrency = []
    for group in config["concurrency"]:
        for round_index in range(group["rounds"]):
            prompts = [config["serial"][i]["prompt"] for i in group["prompt_indices"]]
            began = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=group["parallel"]) as pool:
                futures = [pool.submit(request, model_id, p) for p in prompts]
                rows = [future.result(timeout=60) for future in futures]
            concurrency.append({
                "parallel": group["parallel"], "round": round_index + 1,
                "wall_ms": round((time.monotonic() - began) * 1000, 2),
                "rows": rows,
            })
            print(f"parallel-{group['parallel']} round-{round_index+1}", flush=True)
    try:
        with post_json("/v1/chat/completions", {"model": model_id, "stream": True}, timeout=5):
            invalid_status = 200
    except urllib.error.HTTPError as error:
        invalid_status = error.code
    after_invalid = request(model_id, config["serial"][0]["prompt"])
    cancelled = request(model_id, config["serial"][1]["prompt"], cancel=True)
    after_cancel = request(model_id, config["serial"][2]["prompt"])
    after = memory(pid)
    rates = [r["decode_tokens_per_second_approx"] for r in serial if r["decode_tokens_per_second_approx"] is not None]
    result = {
        "classification": "DEV_ONLY_CONTROLLED_QWEN_PRIVATE_SERVING_MEASUREMENT",
        "fixture_sha256": digest(FIXTURES),
        "scoring_code_sha256": digest(Path(__file__)),
        "weight_sha256": EXPECTED_WEIGHT_SHA,
        "runtime": "MLX-LM 0.32.0; localhost 127.0.0.1:18080; offline loading",
        "server_command": command,
        "model_id": model_id,
        "free_disk_before_gib": round(free_gib, 3),
        "physical_ram_gib": round(ram, 3),
        "memory_before": before,
        "memory_after": after,
        "serial": serial,
        "concurrency": concurrency,
        "error_recovery": {"invalid_request_status": invalid_status, "subsequent_request": after_invalid},
        "cancel_recovery": {"cancelled_stream": cancelled, "subsequent_request": after_cancel},
        "summary": {
            "serial_n": len(serial),
            "serial_ttft_p95_ms": p95([r["first_visible_ms"] for r in serial if r["first_visible_ms"] is not None]),
            "serial_end_to_end_p95_ms": p95([r["end_to_end_ms"] for r in serial]),
            "serial_decode_tps_median_approx": sorted(rates)[len(rates)//2] if rates else None,
            "parallel_2_wall_p95_ms": p95([r["wall_ms"] for r in concurrency if r["parallel"] == 2]),
            "parallel_4_wall_p95_ms": p95([r["wall_ms"] for r in concurrency if r["parallel"] == 4]),
            "successful_streams": sum(r["status"] == 200 and r["finish_reason"] == "stop" for r in serial),
            "reasoning_markers_visible": sum(r["reasoning_marker_visible"] for r in serial),
        },
        "limits": [
            "Small original synthetic prompts and warmed local process; no production traffic or long context.",
            "Raw MLX HTTP service, not authenticated Azaeron API or mTLS deployment.",
            "No approved Azaeron checkpoint, writer quality, load SLO, production model attestation, or release approval.",
            "Approximate decode throughput excludes first token and includes SSE/network parsing overhead.",
            "Nearest-rank p95 over small samples; shared Mac workloads may vary.",
        ],
    }
    RESULT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run"))
    parser.add_argument("--pid", type=int)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    else:
        if args.pid is None:
            raise SystemExit("--pid required")
        run(args.pid)
