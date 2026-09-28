"""Dependency health and operational gauge refreshes.

Health endpoints intentionally expose dependency state, not exception text or
credentials.  Readiness fails closed when a required dependency is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable

from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger
from app.core.observability import (
    QUEUE_DEPTH,
    REDIS_HEALTH,
    REDIS_OPERATIONS,
    DEPENDENCY_HEALTH,
    WORKER_COUNT,
    WORKER_HEALTH,
    _update_pool_metrics,
)

logger = get_logger(__name__)

CELERY_QUEUES = (
    "document_processing",
    "similarity_analysis",
    "citation_analysis",
    "ai_detection",
    "authorship_analysis",
    "report_generation",
    "identity",
)


async def _check(name: str, operation: Callable[[], Awaitable[Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            operation(), timeout=settings.HEALTHCHECK_TIMEOUT_SECONDS
        )
        DEPENDENCY_HEALTH.labels(name).set(1)
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            **(result or {}),
        }
    except asyncio.TimeoutError:
        DEPENDENCY_HEALTH.labels(name).set(0)
        logger.warning("dependency_health_timeout", dependency=name)
        return {
            "status": "timeout",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        DEPENDENCY_HEALTH.labels(name).set(0)
        logger.warning(
            "dependency_health_failed", dependency=name, error_type=type(exc).__name__
        )
        return {
            "status": "failed",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }


async def _check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    _update_pool_metrics(engine)
    return None


async def _check_redis() -> None:
    from redis.asyncio import Redis

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        await client.ping()
        REDIS_HEALTH.set(1)
        return None
    finally:
        await client.aclose()


def _storage_ping() -> None:
    from app.core.object_storage import Minio

    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
        region=settings.MINIO_REGION,
    )
    # Iterating the generator performs the request while bounding the amount
    # of data returned.  The prefix also exercises the app policy namespace.
    next(
        iter(
            client.list_objects(
                settings.MINIO_BUCKET, prefix="uploads/", recursive=False
            )
        ),
        None,
    )


async def _check_storage() -> None:
    await asyncio.to_thread(_storage_ping)
    return None


def _worker_ping() -> dict[str, int]:
    from redis import Redis

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    coverage = {queue: 0 for queue in CELERY_QUEUES}
    count = 0
    try:
        for key in client.scan_iter(
            match=f"{settings.WORKER_HEARTBEAT_KEY_PREFIX}:*", count=100
        ):
            value = client.get(key)
            if not isinstance(value, str):
                continue
            queues = json.loads(value)
            if not isinstance(queues, list):
                continue  # Old heartbeat format does not prove queue coverage.
            count += 1
            for queue in coverage:
                coverage[queue] += int(queue in queues)
        WORKER_COUNT.set(count)
        for queue, consumers in coverage.items():
            WORKER_HEALTH.labels(queue).set(consumers)
        return coverage
    finally:
        client.close()


async def _check_workers() -> dict[str, Any]:
    coverage = await asyncio.to_thread(_worker_ping)
    if not all(coverage.values()):
        raise RuntimeError("required queue has no live consumer")
    return {"queue_consumers": coverage}


async def _check_inference() -> None:
    from app.modules.inference.service import gateway

    if (await gateway().health())["status"] != "AVAILABLE":
        raise RuntimeError("private inference unavailable")


async def readiness_report() -> dict[str, Any]:
    checks = {
        "database": await _check("database", _check_database),
        "redis": await _check("redis", _check_redis),
        "storage": await _check("storage", _check_storage),
    }
    if settings.READINESS_REQUIRE_WORKER:
        checks["workers"] = await _check("workers", _check_workers)
    else:
        checks["workers"] = {"status": "not_required"}
    required = ("database", "redis", "storage") + (
        ("workers",) if settings.READINESS_REQUIRE_WORKER else ()
    )
    if settings.INFERENCE_ENABLED:
        checks["inference"] = await _check("inference", _check_inference)
        required += ("inference",)
    ready = all(checks[name]["status"] == "ok" for name in required)
    return {"status": "ready" if ready else "not_ready", "checks": checks}


async def refresh_operational_metrics() -> None:
    """Refresh gauges that cannot be maintained by request instrumentation."""
    _update_pool_metrics(engine)
    from redis.asyncio import Redis

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=min(settings.REDIS_CONNECT_TIMEOUT_SECONDS, 1),
        socket_timeout=min(settings.REDIS_SOCKET_TIMEOUT_SECONDS, 1),
    )
    try:
        await asyncio.wait_for(client.ping(), timeout=1)
        REDIS_HEALTH.set(1)
        pipeline = client.pipeline(transaction=False)
        for queue in CELERY_QUEUES:
            for priority in (0, 3, 6, 9):
                pipeline.llen(queue if priority == 0 else f"{queue}\x06\x16{priority}")
        depths = await asyncio.wait_for(pipeline.execute(), timeout=2)
        for index, queue in enumerate(CELERY_QUEUES):
            QUEUE_DEPTH.labels(queue).set(sum(depths[index * 4 : index * 4 + 4]))
        REDIS_OPERATIONS.labels("metrics_refresh", "success").inc()
    except Exception:
        REDIS_HEALTH.set(0)
        for queue in CELERY_QUEUES:
            QUEUE_DEPTH.labels(queue).set(float("nan"))
        REDIS_OPERATIONS.labels("metrics_refresh", "error").inc()
    finally:
        await client.aclose()
    await asyncio.gather(
        _check("database", _check_database),
        _check("storage", _check_storage),
        _check("workers", _check_workers),
    )
