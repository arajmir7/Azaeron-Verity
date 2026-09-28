"""Measured application workloads against isolated, real API/DB/storage/workers."""

import argparse
import asyncio
from collections import Counter
import hashlib
import io
import json
import math
import platform
import secrets
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.api.v1.documents import get_storage_client


def percentiles(values):
    values = sorted(values)
    return (
        {
            f"p{p}": round(values[max(0, math.ceil(len(values) * p / 100) - 1)], 3)
            for p in (50, 95, 99)
        }
        if values
        else {}
    )


async def main(args):
    assert settings.ENVIRONMENT == "development"
    samples, observations = [], []
    fixtures = []
    document_locks = [asyncio.Lock() for _ in range(8)]
    password = secrets.token_urlsafe(24) + "Aa1!"
    headers = {"Origin": args.origin}
    stop = asyncio.Event()
    async with httpx.AsyncClient(
        base_url=args.base_url,
        headers=headers,
        timeout=60,
        limits=httpx.Limits(max_connections=24),
    ) as client:

        async def required(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.is_success, (
                method,
                path.split("?")[0],
                response.status_code,
            )
            return response.json()

        async def measured(name, concurrency, method, path, accepted=(200,), **kwargs):
            started = time.perf_counter()
            try:
                response = await client.request(method, path, **kwargs)
                samples.append(
                    {
                        "workload": name,
                        "concurrency": concurrency,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "status": response.status_code,
                        "expected": response.status_code in accepted,
                        "bytes": len(response.content),
                        "trace_id": response.headers.get("X-Trace-ID"),
                    }
                )
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.with_suffix(".samples.json").write_text(
                    json.dumps(samples, indent=2) + "\n"
                )
                return response
            except httpx.HTTPError:
                samples.append(
                    {
                        "workload": name,
                        "concurrency": concurrency,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "status": 0,
                        "expected": False,
                        "bytes": 0,
                        "trace_id": None,
                    }
                )
                return None

        credentials = {"email": f"load-{uuid4().hex}@example.com", "password": password}
        await required("POST", "/api/v1/auth/register", json=credentials)
        await required("POST", "/api/v1/auth/login", json=credentials)
        await required(
            "POST", "/api/v1/auth/onboarding", json={"product_role": "researcher"}
        )
        base_text = "Controlled fixture records stable measurements, preserves citations, and reviews each revision. "
        for i in range(8):
            content = (base_text * (8 if i < 6 else 80) + f" Fixture {i}.").encode()
            upload = await required(
                "POST",
                "/api/v1/documents/upload-request",
                json={
                    "filename": f"load-{i}.txt",
                    "content_type": "text/plain",
                    "file_size": len(content),
                },
            )
            await asyncio.to_thread(
                get_storage_client().put_object,
                settings.MINIO_BUCKET,
                upload["storage_key"],
                io.BytesIO(content),
                len(content),
                content_type="text/plain",
            )
            response = await measured(
                "job_creation",
                1,
                "POST",
                "/api/v1/documents/upload-confirm",
                json={
                    "upload_id": upload["upload_id"],
                    "storage_key": upload["storage_key"],
                    "sha256_fingerprint": hashlib.sha256(content).hexdigest(),
                    "original_filename": f"load-{i}.txt",
                },
            )
            assert response is not None and response.is_success, (
                samples[-1]["status"],
                samples[-1]["trace_id"],
            )
            fixtures.append(
                {
                    "id": response.json()["id"],
                    "text": content.decode(),
                    "bytes": len(content),
                }
            )
        for fixture in fixtures:
            for attempt in range(180):
                response = await client.get(
                    f'/api/v1/documents/{fixture["id"]}/content'
                )
                if response.is_success:
                    fixture["version"] = response.json()["document_version_id"]
                    break
                await asyncio.sleep(1)
            else:
                raise AssertionError("Fixture processing failed")
        await asyncio.sleep(2)

        async def observe():
            from redis.asyncio import Redis

            redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            try:
                while not stop.is_set():
                    async with AsyncSessionLocal() as db:
                        stats = (
                            (
                                await db.execute(
                                    text(
                                        "SELECT count(*) AS connections, count(*) FILTER (WHERE state='active') AS active, count(*) FILTER (WHERE wait_event_type='Lock') AS lock_waiters FROM pg_stat_activity WHERE datname=current_database()"
                                    )
                                )
                            )
                            .mappings()
                            .one()
                        )
                    row = {
                        **dict(stats),
                        "time": time.time(),
                        "queue": await redis.llen("document_processing"),
                    }
                    metric = (
                        await client.get(
                            "/metrics",
                            headers={
                                "Authorization": "Bearer "
                                + str(settings.METRICS_TOKEN or "")
                            },
                        )
                    ).text
                    for line in metric.splitlines():
                        if line.startswith(
                            (
                                "azaeron_db_pool_checked_out ",
                                "azaeron_db_pool_overflow ",
                                "azaeron_db_pool_size ",
                            )
                        ):
                            key, value = line.split()
                            row[key] = float(value)
                    observations.append(row)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=0.5)
                    except TimeoutError:
                        pass
            finally:
                await redis.aclose()

        observer = asyncio.create_task(observe())
        try:
            for concurrency in args.concurrency:
                key = await required(
                    "POST",
                    "/api/v1/api-keys",
                    json={
                        "name": f"Load {concurrency}",
                        "scopes": ["documents:read", "text:analyze"],
                    },
                )
                key_header = {"X-API-Key": key["secret"]}
                semaphore = asyncio.Semaphore(concurrency)

                async def workload(name, index):
                    async with semaphore:
                        fixture = fixtures[index % len(fixtures)]
                        doc = fixture["id"]
                        if name == "document_read":
                            await measured(
                                name, concurrency, "GET", f"/api/v1/documents/{doc}"
                            )
                        elif name == "document_list":
                            await measured(
                                name,
                                concurrency,
                                "GET",
                                "/api/v1/documents?page_size=5",
                            )
                        elif name == "version_history":
                            await measured(
                                name,
                                concurrency,
                                "GET",
                                f"/api/v1/provenance/documents/{doc}/timeline",
                            )
                        elif name == "api_key_read":
                            await measured(
                                name,
                                concurrency,
                                "GET",
                                f"/api/v1/documents/{doc}",
                                headers=key_header,
                            )
                        elif name == "analysis":
                            await measured(
                                name,
                                concurrency,
                                "POST",
                                "/api/v1/text/analyze",
                                accepted=(200, 429),
                                headers=key_header,
                                json={
                                    "operation_id": str(uuid4()),
                                    "text": fixture["text"],
                                },
                            )
                        elif name == "document_save":
                            async with document_locks[index % len(fixtures)]:
                                response = await measured(
                                    name,
                                    concurrency,
                                    "POST",
                                    f"/api/v1/documents/{doc}/revisions",
                                    json={
                                        "operation_id": str(uuid4()),
                                        "base_version_id": fixture["version"],
                                        "text": fixture["text"]
                                        + f" Revision {concurrency}-{index}.",
                                        "edit_ids": [],
                                    },
                                )
                                if response and response.is_success:
                                    fixture["version"] = response.json()["id"]
                        elif name == "revision_conflict":
                            async with document_locks[index % len(fixtures)]:
                                responses = await asyncio.gather(
                                    *(
                                        measured(
                                            name,
                                            concurrency,
                                            "POST",
                                            f"/api/v1/documents/{doc}/revisions",
                                            accepted=(200, 409),
                                            json={
                                                "operation_id": str(uuid4()),
                                                "base_version_id": fixture["version"],
                                                "text": fixture["text"]
                                                + f" Conflict {concurrency}-{index}-{n}.",
                                                "edit_ids": [],
                                            },
                                        )
                                        for n in range(2)
                                    )
                                )
                                assert sorted(
                                    r.status_code if r is not None else 0
                                    for r in responses
                                ) == [200, 409]
                                fixture["version"] = next(
                                    r.json()["id"]
                                    for r in responses
                                    if r.status_code == 200
                                )
                        elif name == "job_poll":
                            await measured(
                                name, concurrency, "GET", "/api/v1/jobs?page_size=20"
                            )

                for name in [
                    "document_read",
                    "document_list",
                    "version_history",
                    "api_key_read",
                    "analysis",
                    "document_save",
                    "revision_conflict",
                    "job_poll",
                ]:
                    count = 4 if name == "revision_conflict" else args.requests
                    await asyncio.gather(*(workload(name, i) for i in range(count)))
            # Verify the measured saves have drained and every processing job completed.
            for attempt in range(180):
                jobs = await required(
                    "GET", "/api/v1/jobs?page_size=100&job_type=document_processing"
                )
                if all(j["status"] == "completed" for j in jobs["items"]):
                    break
                assert not any(j["status"] == "failed" for j in jobs["items"])
                await asyncio.sleep(1)
            else:
                raise AssertionError("Measured job backlog did not drain")
        finally:
            stop.set()
            await observer
        grouped = []
        for name, concurrency in sorted(
            {(s["workload"], s["concurrency"]) for s in samples}
        ):
            rows = [
                s
                for s in samples
                if (s["workload"], s["concurrency"]) == (name, concurrency)
            ]
            grouped.append(
                {
                    "workload": name,
                    "concurrency": concurrency,
                    "requests": len(rows),
                    "latency_ms": percentiles([s["latency_ms"] for s in rows]),
                    "status_counts": dict(Counter(str(s["status"]) for s in rows)),
                    "unexpected_error_rate": sum(not s["expected"] for s in rows)
                    / len(rows),
                    "max_response_bytes": max(s["bytes"] for s in rows),
                }
            )
        report = {
            "scope": "synthetic local application performance; not model inference or production capacity",
            "platform": platform.platform(),
            "dataset": {
                "documents": len(fixtures),
                "initial_bytes": [f["bytes"] for f in fixtures],
                "processing_jobs": len(jobs["items"]),
            },
            "profiles": grouped,
            "samples": samples,
            "saturation_samples": observations,
            "model_inference": "BLOCKED: approved assets/hardware unavailable",
            "result": "PASS" if all(s["expected"] for s in samples) else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in {"samples", "saturation_samples"}
                },
                indent=2,
            )
        )
        if report["result"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://backend:8000")
    parser.add_argument("--origin", default="http://localhost:4700")
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
