"""Reproducible private candidate evaluation. Missing inputs remain BLOCKED.

Runs only licensed, approved runtime records through the private mTLS gateway.
The command never downloads models, promotes a registry entry or fabricates
hardware/quality measurements. Dataset rows are operator-owned test inputs.
"""

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import time
from uuid import uuid4

from app.modules.inference.service import registry, gateway
from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable
from app.modules.verification.service import deterministic_reasons


async def evaluate(dataset_path, concurrency):
    report = {
        "status": "BLOCKED",
        "production_certified": False,
        "candidates": [],
        "blockers": [],
        "protocol": "private-model-bakeoff-1",
        "concurrency": concurrency,
    }
    try:
        catalog = registry()
    except InferenceUnavailable as error:
        report["blockers"].append(error.code)
        return report
    candidates = [
        model
        for model in catalog.models
        if model.status == "APPROVED" and "refine" in model.tasks
    ]
    if len(candidates) < 2:
        report["blockers"].append(
            "At least two commercially reviewed approved private candidates are required."
        )
    if dataset_path is None or not dataset_path.is_file():
        report["blockers"].append("No licensed evaluation dataset supplied.")
    if report["blockers"]:
        return report
    dataset = json.loads(dataset_path.read_text())
    if not dataset.get("license_review_reference") or not dataset.get(
        "provenance_review_reference"
    ):
        raise ValueError("Dataset rights and provenance review are required")
    examples = dataset["examples"]
    if not 10 <= len(examples) <= 1000 or any(
        not row.get("id")
        or not row.get("domain")
        or not row.get("language")
        or not 1 <= len(row.get("text", "")) <= 60_000
        for row in examples
    ):
        raise ValueError(
            "Use 10 to 1000 bounded, identified, domain/language-labelled examples"
        )
    if len({row["id"] for row in examples}) != len(examples):
        raise ValueError("Duplicate evaluation example IDs")
    report["dataset_sha256"] = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    report["registry_sha256"] = hashlib.sha256(
        catalog.model_dump_json().encode()
    ).hexdigest()
    report["domains"] = dict(Counter(row["domain"] for row in examples))
    report["languages"] = dict(Counter(row["language"] for row in examples))
    for candidate in sorted(candidates, key=lambda model: model.model_id):
        private = gateway()
        private.router.registry = catalog.model_copy(
            update={"routes": {**catalog.routes, "refine": candidate.model_id}}
        )
        verifier = catalog.select("verify")
        if (
            candidate.model_id == verifier.model_id
            or candidate.revision == verifier.revision
        ):
            raise ValueError("An independent verifier is required")
        slots = asyncio.Semaphore(concurrency)

        async def run(row):
            async with slots:
                began = time.monotonic()
                try:
                    result = await private.run(
                        AzaeronInferenceJob(
                            operation_id=uuid4(),
                            organization_id=uuid4(),
                            user_id=uuid4(),
                            task="refine",
                            text=row["text"],
                        )
                    )
                    reasons = deterministic_reasons(row["text"], result.output)
                    return {
                        "id": row["id"],
                        "status": "EXECUTED",
                        "duration_ms": result.duration_ms,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "protected_spans_pass": not reasons,
                        "reasons": reasons,
                        "candidate_sha256": hashlib.sha256(
                            result.output.encode()
                        ).hexdigest(),
                    }
                except InferenceUnavailable as error:
                    return {
                        "id": row["id"],
                        "status": "UNAVAILABLE",
                        "code": error.code,
                        "duration_ms": round((time.monotonic() - began) * 1000),
                    }

        began = time.monotonic()
        rows = await asyncio.gather(*(run(row) for row in examples))
        duration = time.monotonic() - began
        completed = [row for row in rows if row["status"] == "EXECUTED"]
        report["candidates"].append(
            {
                "model_id": candidate.model_id,
                "revision": candidate.revision,
                "license": candidate.license,
                "context_limit": candidate.context_limit,
                "languages": candidate.languages,
                "configured_hardware": candidate.hardware,
                "measured_peak_vram_bytes": None,
                "measured_peak_ram_bytes": None,
                "recovery_drill": "BLOCKED",
                "p50_duration_ms": (
                    statistics.median(row["duration_ms"] for row in completed)
                    if completed
                    else None
                ),
                "tokens_per_second": sum(row["output_tokens"] for row in completed)
                / duration,
                "examples": rows,
            }
        )
    report["blockers"] = [
        "Blind human quality, contradiction/addition adjudication, measured VRAM/RAM, fairness and failure recovery evidence are still required. No winner selected."
    ]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--concurrency", type=int, choices=(1, 2, 4, 8), default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.dataset, args.concurrency))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(report["status"])
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
