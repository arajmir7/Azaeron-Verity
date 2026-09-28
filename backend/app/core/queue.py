"""Bounded task publication with an explicit unavailable-queue outcome."""

from __future__ import annotations

import time
from typing import Any, Sequence

from celery import Task
from kombu.exceptions import OperationalError
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class QueueUnavailable(RuntimeError):
    """Raised when a task cannot be published after bounded retries."""


def enqueue_with_retry(task: Task, args: Sequence[Any]) -> Any:
    """Publish without creating an acknowledged job that has no task.

    The surrounding API transaction is rolled back by the caller when this
    raises.  The upload object remains safely retryable because confirmation is
    idempotent by storage key.
    """
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            from app.core.observability import trace_headers

            return task.apply_async(
                args=list(args), retry=False, headers=trace_headers()
            )
        except (OperationalError, RedisError, OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(min(0.25 * (2**attempt), 1.0))
                continue
    logger.error(
        "task_publish_failed",
        task_name=getattr(task, "name", "unknown"),
        attempts=3,
        error_type=type(last_error).__name__ if last_error else "unknown",
    )
    raise QueueUnavailable from last_error
