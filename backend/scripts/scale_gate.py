"""Authenticated, synthetic scale-gate workload for the running API.

This is an operator benchmark, not a production data generator. It exercises
the real presigned-upload, confirmation, Celery processing, and tenant-scoped
read paths. Results are emitted as JSON so they can be retained with a release
record without inventing aggregate statistics.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import statistics
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
import asyncpg

# The Docker operator command runs this file by path (`python scripts/...`).
# Put the application root on sys.path without changing the production image
# or relying on the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings


PASSWORD = "ScaleGatePassword123!"
BASE_TEXT = (
    "A measured evidence pipeline preserves source text, immutable versions, "
    "tenant boundaries, and reproducible analysis metadata. "
)


@dataclass(frozen=True)
class TimedResult:
    name: str
    elapsed_ms: float
    ok: bool
    detail: dict[str, Any]


def percentiles(values: Iterable[float]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}

    def percentile(q: float) -> float:
        index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
        return round(ordered[index], 3)

    return {
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
    }


async def request_json(
    client: httpx.AsyncClient, method: str, path: str, **kwargs: Any
) -> tuple[httpx.Response, dict[str, Any]]:
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault(
        "Origin", os.getenv("AZAERON_BENCHMARK_ORIGIN", "http://localhost:3000")
    )
    response = await client.request(method, path, headers=headers, **kwargs)
    try:
        body = response.json()
    except ValueError:
        body = {"text": response.text[:500]}
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} returned {response.status_code}: {body}")
    return response, body


async def authenticate(client: httpx.AsyncClient) -> dict[str, str]:
    run_id = uuid.uuid4().hex[:12]
    # Use a syntactically valid non-delivery domain; the API's email validator
    # intentionally rejects reserved special-use domains such as `.test`.
    email = f"scale-gate-{run_id}@loadtest.com"
    await request_json(
        client,
        "POST",
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "first_name": "Scale",
            "last_name": "Gate",
        },
    )
    await request_json(
        client,
        "POST",
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    _, organization = await request_json(
        client, "POST", "/api/v1/organizations", json={"name": f"Scale Gate {run_id}"}
    )
    await request_json(
        client, "POST", f"/api/v1/organizations/{organization['id']}/select"
    )
    return {"run_id": run_id, "organization_id": organization["id"]}


async def upload_document(
    client: httpx.AsyncClient, text: str, index: int, prefix: str
) -> TimedResult:
    content = text.encode("utf-8")
    started = time.perf_counter()
    try:
        _, upload = await request_json(
            client,
            "POST",
            "/api/v1/documents/upload-request",
            json={
                "filename": f"{prefix}-{index}.txt",
                "content_type": "text/plain",
                "file_size": len(content),
            },
        )
        request_elapsed = (time.perf_counter() - started) * 1000
        put_started = time.perf_counter()
        put_response = await client.put(
            upload["upload_url"],
            content=content,
            headers={"Content-Type": "text/plain"},
        )
        put_elapsed = (time.perf_counter() - put_started) * 1000
        if put_response.status_code >= 400:
            raise RuntimeError(
                f"presigned PUT returned {put_response.status_code}: {put_response.text[:500]}"
            )
        confirm_started = time.perf_counter()
        _, document = await request_json(
            client,
            "POST",
            "/api/v1/documents/upload-confirm",
            json={
                "upload_id": upload["upload_id"],
                "storage_key": upload["storage_key"],
                "sha256_fingerprint": hashlib.sha256(content).hexdigest(),
            },
        )
        confirm_elapsed = (time.perf_counter() - confirm_started) * 1000
        return TimedResult(
            name="upload",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            ok=True,
            detail={
                "document_id": document["id"],
                "bytes": len(content),
                "request_ms": round(request_elapsed, 3),
                "storage_put_ms": round(put_elapsed, 3),
                "confirm_ms": round(confirm_elapsed, 3),
            },
        )
    except Exception as exc:
        return TimedResult(
            name="upload",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            ok=False,
            detail={"error": str(exc)},
        )


async def wait_for_completion(
    pool: asyncpg.Pool, organization_id: str, document_id: str, timeout_seconds: float
) -> TimedResult:
    started = time.perf_counter()
    deadline = started + timeout_seconds
    last_status = "unknown"
    while time.perf_counter() < deadline:
        async with pool.acquire() as connection:
            await connection.execute(
                "SELECT set_config('app.current_organization_id', $1, false)",
                organization_id,
            )
            status_value = await connection.fetchval(
                "SELECT status::text FROM documents WHERE id = $1 AND organization_id = $2",
                document_id,
                organization_id,
            )
            last_status = str(status_value or "unknown").lower()
        if last_status in {"completed", "failed", "archived"}:
            return TimedResult(
                name="analysis",
                elapsed_ms=(time.perf_counter() - started) * 1000,
                ok=last_status == "completed",
                detail={"document_id": document_id, "status": last_status},
            )
        await asyncio.sleep(0.5)
    return TimedResult(
        name="analysis",
        elapsed_ms=(time.perf_counter() - started) * 1000,
        ok=False,
        detail={"document_id": document_id, "status": last_status, "error": "timeout"},
    )


def summarize(
    name: str, samples: list[TimedResult], wall_seconds: float | None = None
) -> dict[str, Any]:
    successful = [sample for sample in samples if sample.ok]
    result: dict[str, Any] = {
        "workload": name,
        "samples": len(samples),
        "successful": len(successful),
        "failed": len(samples) - len(successful),
        "latency": percentiles(sample.elapsed_ms for sample in samples),
    }
    if wall_seconds is not None and wall_seconds > 0:
        result["throughput_per_second"] = round(len(successful) / wall_seconds, 3)
        result["wall_time_seconds"] = round(wall_seconds, 3)
    if samples:
        result["details"] = [sample.detail for sample in samples if not sample.ok][:10]
    return result


async def run(args: argparse.Namespace) -> dict[str, Any]:
    timeout = httpx.Timeout(args.http_timeout_seconds, connect=5.0)
    limits = httpx.Limits(
        max_connections=max(args.concurrent, 16),
        max_keepalive_connections=max(args.concurrent, 16),
    )
    async with httpx.AsyncClient(
        base_url=args.base_url, timeout=timeout, limits=limits, follow_redirects=True
    ) as client:
        identity = await authenticate(client)
        status_pool = await asyncpg.create_pool(
            settings.DATABASE_URL.replace("+asyncpg", ""),
            min_size=1,
            max_size=4,
        )
        small_text = BASE_TEXT * args.small_repeats
        large_text = (
            BASE_TEXT + "Corpus-specific evidence remains separately verifiable. "
        ) * args.large_repeats

        scenarios: list[dict[str, Any]] = []
        started = time.perf_counter()
        small = [
            await upload_document(client, small_text, index, "small")
            for index in range(args.small_samples)
        ]
        scenarios.append(
            summarize("small_upload", small, time.perf_counter() - started)
        )

        started = time.perf_counter()
        large = [
            await upload_document(client, large_text, index, "large")
            for index in range(args.large_samples)
        ]
        scenarios.append(
            summarize("large_upload", large, time.perf_counter() - started)
        )

        started = time.perf_counter()
        concurrent_uploads = await asyncio.gather(
            *(
                upload_document(client, small_text, index, "concurrent")
                for index in range(args.concurrent)
            ),
        )
        scenarios.append(
            summarize(
                "concurrent_upload",
                list(concurrent_uploads),
                time.perf_counter() - started,
            )
        )

        analysis_documents = [
            sample.detail["document_id"]
            for sample in [*small, *large, *concurrent_uploads]
            if sample.ok and "document_id" in sample.detail
        ]
        started = time.perf_counter()
        analyses = await asyncio.gather(
            *(
                wait_for_completion(
                    status_pool,
                    identity["organization_id"],
                    document_id,
                    args.analysis_timeout_seconds,
                )
                for document_id in analysis_documents
            ),
        )
        scenarios.append(
            summarize(
                "concurrent_analysis", list(analyses), time.perf_counter() - started
            )
        )

        corpus_started = time.perf_counter()
        corpus_uploads = await asyncio.gather(
            *(
                upload_document(
                    client, BASE_TEXT * args.corpus_repeats, index, "corpus"
                )
                for index in range(args.corpus_documents)
            ),
        )
        corpus_analysis_documents = [
            sample.detail["document_id"]
            for sample in corpus_uploads
            if sample.ok and "document_id" in sample.detail
        ]
        corpus_analysis = await asyncio.gather(
            *(
                wait_for_completion(
                    status_pool,
                    identity["organization_id"],
                    document_id,
                    args.analysis_timeout_seconds,
                )
                for document_id in corpus_analysis_documents
            ),
        )
        target_text = (
            BASE_TEXT * args.corpus_repeats
            + " A distinct target sentence tests bounded retrieval."
        )
        target = await upload_document(client, target_text, 0, "corpus-target")
        target_analysis = []
        if target.ok:
            target_analysis.append(
                await wait_for_completion(
                    status_pool,
                    identity["organization_id"],
                    target.detail["document_id"],
                    args.analysis_timeout_seconds,
                )
            )
            matches_started = time.perf_counter()
            _, match_body = await request_json(
                client,
                "GET",
                f"/api/v1/similarity/documents/{target.detail['document_id']}/matches",
            )
            match_elapsed = (time.perf_counter() - matches_started) * 1000
            match_result = {
                "latency_ms": round(match_elapsed, 3),
                "matches": match_body.get("total", 0),
            }
        else:
            match_result = {"error": target.detail.get("error", "target upload failed")}
        scenarios.append(
            {
                "workload": "large_similarity_corpus",
                "corpus_documents": len(corpus_uploads),
                "corpus_analysis": summarize(
                    "corpus_analysis",
                    list(corpus_analysis),
                    time.perf_counter() - corpus_started,
                ),
                "target_analysis": summarize("corpus_target_analysis", target_analysis),
                "match_read_latency": match_result,
            }
        )

        await status_pool.close()
        return {
            "run_id": identity["run_id"],
            "organization_id": identity["organization_id"],
            "base_url": args.base_url,
            "synthetic_workload": True,
            "parameters": vars(args),
            "scenarios": scenarios,
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--base-url", default=os.getenv("AZAERON_BASE_URL", "http://backend:8000")
    )
    result.add_argument("--small-samples", type=int, default=5)
    result.add_argument("--small-repeats", type=int, default=60)
    result.add_argument("--large-samples", type=int, default=2)
    result.add_argument("--large-repeats", type=int, default=600)
    result.add_argument("--concurrent", type=int, default=8)
    result.add_argument("--corpus-documents", type=int, default=24)
    result.add_argument("--corpus-repeats", type=int, default=60)
    result.add_argument("--analysis-timeout-seconds", type=float, default=180.0)
    result.add_argument("--http-timeout-seconds", type=float, default=30.0)
    return result


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run(parser().parse_args())), indent=2, sort_keys=True))
