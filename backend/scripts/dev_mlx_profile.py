"""Bounded local MLX latency/context/concurrency profile; DEV_ONLY evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import statistics
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from app.modules.inference.dev_mlx import DevMlxGateway
from app.modules.inference.gateway import AzaeronInferenceJob

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/verity/evidence/live-ai-stabilization-20261010/profile.json"


def job(text: str, max_output_tokens: int = 64) -> AzaeronInferenceJob:
    return AzaeronInferenceJob(
        operation_id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        task="chat",
        text=text,
        max_output_tokens=max_output_tokens,
    )


async def timed(gateway: DevMlxGateway, prompt: str, limit: int = 64) -> dict:
    started = time.monotonic()
    first = []

    async def delta(_text: str) -> None:
        if not first:
            first.append(round((time.monotonic() - started) * 1000))

    result = await gateway.run(job(prompt, limit), on_delta=delta)
    decode_ms = result.duration_ms - first[0] if first else None
    return {
        "input_bytes": len(prompt.encode()),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "duration_ms": result.duration_ms,
        "ttft_ms": first[0] if first else None,
        "decode_tokens_per_s": (
            round(1000 * result.output_tokens / decode_ms, 2)
            if decode_ms and decode_ms > 0
            else None
        ),
        "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
        "model_revision": result.model_revision,
    }


def footprint(pid: int) -> dict:
    try:
        completed = subprocess.run(
            ["footprint", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        lines = [
            line.strip()
            for line in completed.stdout.splitlines()
            if line.strip().startswith(("phys_footprint:", "phys_footprint_peak:"))
        ]
        return {"status": "measured", "lines": lines[:4]}
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable"}


def model_pid() -> int:
    lines = subprocess.check_output(
        ["lsof", "-t", "-iTCP:8080", "-sTCP:LISTEN"], text=True
    ).splitlines()
    for line in lines:
        pid = int(line)
        command = subprocess.check_output(
            ["ps", "-o", "command=", "-p", str(pid)], text=True
        )
        if "mlx_lm.server" in command:
            return pid
    raise SystemExit("Expected local MLX process not found")


async def main() -> None:
    if OUTPUT.exists():
        raise SystemExit("Profile already exists; refusing overwrite")
    gateway = DevMlxGateway("http://127.0.0.1:8080")
    if (await gateway.health())["status"] != "AVAILABLE":
        raise SystemExit("Pinned local model unavailable")
    pid = model_pid()
    report = {
        "purpose": "DEV_ONLY measured profile, no production SLO claim",
        "server_pid": pid,
        "footprint_before": footprint(pid),
        "context_scaling": [],
        "generation": [],
        "concurrency": [],
    }
    for target in (512, 2048, 8192, 12000):
        filler = ("context alpha beta gamma. " * ((target // 26) + 1))[:target]
        prompt = "Reply with only READY after reading this context:\n" + filler
        report["context_scaling"].append(await timed(gateway, prompt, 32))
    for _ in range(3):
        report["generation"].append(
            await timed(
                gateway,
                "List the integers from 1 through 50 in order, separated by commas.",
                256,
            )
        )
    for count in (1, 2, 4):
        started = time.monotonic()
        calls = await asyncio.gather(
            *(timed(gateway, "Reply only OK.", 16) for _ in range(count)),
            return_exceptions=True,
        )
        report["concurrency"].append(
            {
                "requests": count,
                "wall_ms": round((time.monotonic() - started) * 1000),
                "completed": sum(isinstance(item, dict) for item in calls),
                "errors": [
                    type(item).__name__
                    for item in calls
                    if isinstance(item, BaseException)
                ],
            }
        )
    report["footprint_after"] = footprint(pid)
    decode = [
        row["decode_tokens_per_s"]
        for row in report["generation"]
        if row["decode_tokens_per_s"] is not None
    ]
    report["generation_decode_tokens_per_s_median"] = (
        statistics.median(decode) if decode else None
    )
    report["limitations"] = [
        "Warm process on a shared Mac; cache state and other workloads were not controlled.",
        "Adapter concurrency limit is process-local; multi-process coordination was not measured.",
        "Decode rate subtracts observed first-visible-token time from end-to-end duration; it is approximate.",
        "Context tests stop below the adapter's 16,000-byte request ceiling; model maximum context was not established.",
    ]
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "context_cases": len(report["context_scaling"]),
                "generation_decode_tokens_per_s_median": report[
                    "generation_decode_tokens_per_s_median"
                ],
                "concurrency": report["concurrency"],
                "footprint_after": report["footprint_after"],
            }
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
