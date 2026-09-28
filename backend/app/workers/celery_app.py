"""AZAERON Celery application."""

import socket
import json

import app.workers.telemetry  # noqa: F401

from celery import Celery
from app.core.config import settings
from app.core.logging import get_logger
from celery.signals import heartbeat_sent, worker_ready, worker_shutdown

# Workers do not import FastAPI's application module, so they must register the
# full ORM graph explicitly before task sessions configure SQLAlchemy mappers.
import app.models  # noqa: F401

logger = get_logger(__name__)

celery_app = Celery(
    "azaeron",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    beat_schedule={
        "usage-reconciliation": {
            "task": "app.workers.tasks.reconcile_usage",
            "schedule": 60.0,
        },
        "storage-retention": {
            "task": "app.workers.tasks.maintain_private_storage",
            "schedule": 3600.0,
        },
        "privacy-erasure": {
            "task": "app.workers.tasks.erase_private_data",
            "schedule": 30.0,
        },
        "identity-mail-delivery": {
            "task": "app.workers.tasks.deliver_identity_mail",
            "schedule": 30.0,
        },
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_acks_on_failure_or_timeout=False,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=None,
    broker_transport_options={
        "visibility_timeout": settings.CELERY_TASK_TIME_LIMIT_SECONDS + 300,
        "socket_timeout": settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        "socket_connect_timeout": settings.REDIS_CONNECT_TIMEOUT_SECONDS,
    },
    result_expires=86400,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 5,
    },
    worker_max_tasks_per_child=50,
    worker_send_task_events=True,
    task_routes={
        "app.workers.tasks.reconcile_usage": {"queue": "identity"},
        "app.workers.tasks.deliver_identity_mail": {"queue": "identity"},
        "app.workers.tasks.erase_private_data": {"queue": "identity"},
        "app.workers.tasks.maintain_private_storage": {"queue": "identity"},
        "app.workers.tasks.process_document": {"queue": "document_processing"},
        "app.workers.tasks.run_similarity_analysis": {"queue": "similarity_analysis"},
        "app.workers.tasks.run_ai_detection": {"queue": "ai_detection"},
        "app.workers.tasks.generate_integrity_report": {"queue": "report_generation"},
    },
)


def _worker_heartbeat_key(sender) -> str:
    hostname = getattr(sender, "hostname", None) or socket.gethostname()
    return f"{settings.WORKER_HEARTBEAT_KEY_PREFIX}:{hostname}"


def _write_worker_heartbeat(sender) -> None:
    from redis import Redis

    client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        client.set(
            _worker_heartbeat_key(sender),
            json.dumps(sorted(_worker_queues)),
            ex=settings.WORKER_HEARTBEAT_TTL_SECONDS,
        )
    finally:
        client.close()


_worker_queues: set[str] = set()


@worker_ready.connect
def mark_worker_ready(sender=None, **kwargs):
    _worker_queues.update(queue.name for queue in sender.task_consumer.queues)
    try:
        _write_worker_heartbeat(sender)
    except Exception as exc:
        logger.warning("worker_heartbeat_write_failed", error_type=type(exc).__name__)


@heartbeat_sent.connect
def refresh_worker_heartbeat(sender=None, **kwargs):
    try:
        _write_worker_heartbeat(sender)
    except Exception as exc:
        logger.warning("worker_heartbeat_refresh_failed", error_type=type(exc).__name__)


@worker_shutdown.connect
def clear_worker_heartbeat(sender=None, **kwargs):
    from redis import Redis

    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        client.delete(_worker_heartbeat_key(sender))
    except Exception as exc:
        logger.warning("worker_heartbeat_clear_failed", error_type=type(exc).__name__)
    finally:
        client.close()
