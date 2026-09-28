"""AZAERON background tasks."""

import asyncio
import json
import time
from datetime import datetime, timezone
from sqlalchemy import select
from redis import Redis

from app.workers.celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal, apply_tenant_context
from app.core.logging import get_logger
from app.core.observability import (
    record_dead_letter,
    record_job_finished,
    record_job_retry,
    record_job_started,
)
from app.modules.jobs.service import JobService
from app.modules.jobs.models import JobStatus, Job
from app.modules.documents.target import AnalysisTarget
from app.modules.documents.service import DocumentService
from app.modules.documents.models import DocumentStatus, DocumentVersion
from app.modules.processing.service import DocumentProcessingService
from app.modules.detection.service import DetectionService
from app.modules.similarity.service import SimilarityService
from app.modules.citations.service import CitationService
from app.modules.authorship.service import (
    AuthorshipService,
)
from app.modules.provenance.service import ProvenanceService
from app.modules.provenance.models import ProvenanceEventType
from app.modules.evidence.service import EvidenceService
from app.modules.audit.service import AuditService
from app.modules.audit.models import AuditAction
from app.modules.governance.models import (
    AnalysisRun,
    AnalysisRunStatus,
    ModelRegistry,
    LifecycleStatus,
)

logger = get_logger(__name__)


class JobNotCommitted(Exception):
    """Broker delivery can arrive just before its enclosing API transaction commits."""


def _redis_client() -> Redis:
    from app.core.config import settings

    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    )


def _enqueue_dead_letter(payload: dict) -> None:
    """Persist terminal task input for operator replay or inspection."""
    from app.core.config import settings

    client = _redis_client()
    try:
        client.rpush(
            settings.DEAD_LETTER_QUEUE_KEY,
            json.dumps(payload, sort_keys=True, default=str),
        )
        client.expire(
            settings.DEAD_LETTER_QUEUE_KEY, settings.DEAD_LETTER_QUEUE_TTL_SECONDS
        )
        record_dead_letter("document_processing")
    finally:
        client.close()


def _run_with_job_lock(job_id: str, operation):
    """Prevent duplicate delivery from concurrently processing one job."""
    from app.core.config import settings

    client = _redis_client()
    lock = client.lock(
        f"azaeron:lock:document-job:{job_id}",
        timeout=settings.CELERY_TASK_TIME_LIMIT_SECONDS + 120,
        blocking_timeout=1,
    )
    acquired = False
    try:
        acquired = lock.acquire(blocking=True)
        if not acquired:
            logger.warning("document_processing_duplicate_delivery", job_id=job_id)
            return None
        return operation()
    finally:
        if acquired:
            lock.release()
        client.close()


def validate_job_target(
    job: Job,
    organization_id: str,
    document_id: str,
    version_id: str | None,
    storage_key: str,
) -> None:
    if not version_id or (
        str(job.organization_id),
        str(job.document_id),
        str(job.document_version_id),
    ) != (organization_id, document_id, version_id):
        raise ValueError(
            "Worker arguments do not match the job organization/document/version target"
        )
    payload = job.input_data or {}
    if (
        payload.get("document_version_id") != version_id
        or payload.get("storage_key") != storage_key
    ):
        raise ValueError("Worker object does not match the recorded job input")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_document(
    self,
    job_id: str,
    document_id: str,
    storage_key: str,
    organization_id: str,
    document_version_id: str | None = None,
):
    """Process a document: extract text, run features, queue detection."""

    async def _record_failure(error: Exception) -> bool:
        """Persist a useful terminal/retry state using a fresh connection."""
        async with AsyncSessionLocal() as failure_db:
            try:
                await apply_tenant_context(failure_db, organization_id, None)
                job = await JobService(failure_db).get_job(job_id, organization_id)
                if not job:
                    logger.error("document_processing_job_missing", job_id=job_id)
                    return False
                if (
                    str(job.document_id) != document_id
                    or str(job.document_version_id) != document_version_id
                ):
                    return False
                job.retry_count += 1
                retry = job.retry_count <= job.max_retries
                job.status = JobStatus.RETRYING if retry else JobStatus.FAILED
                job.error_message = f"Document processing failed ({type(error).__name__}); retry or contact support with the job ID."
                if not retry:
                    doc = await DocumentService(failure_db).get_document(
                        document_id, organization_id
                    )
                    latest_id = (
                        await failure_db.execute(
                            select(DocumentVersion.id)
                            .where(DocumentVersion.document_id == document_id)
                            .order_by(DocumentVersion.version_number.desc())
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if doc and str(latest_id) == document_version_id:
                        doc.status = DocumentStatus.FAILED
                        doc.error_message = job.error_message
                    from app.modules.billing.usage import UsageService

                    await UsageService(failure_db).settle_job(
                        job_id, organization_id, success=False, outcome="failed"
                    )
                await failure_db.commit()
                if not retry:
                    try:
                        _enqueue_dead_letter(
                            {
                                "job_id": job_id,
                                "document_id": document_id,
                                "organization_id": organization_id,
                                "storage_key": storage_key,
                                "document_version_id": document_version_id,
                                "error_type": type(error).__name__,
                                "failed_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    except Exception as dead_letter_error:
                        logger.error(
                            "document_processing_dead_letter_failed",
                            job_id=job_id,
                            error_type=type(dead_letter_error).__name__,
                        )
                return retry
            except Exception as recording_error:
                await failure_db.rollback()
                logger.error(
                    "document_processing_failure_recording_failed",
                    job_id=job_id,
                    error_type=type(recording_error).__name__,
                )
                return False

    async def _process():
        failure: Exception | None = None
        async with AsyncSessionLocal() as db:
            try:
                await apply_tenant_context(db, organization_id, None)
                job_service = JobService(db)
                doc_service = DocumentService(db)

                job = await job_service.get_job(job_id, organization_id)
                if not job:
                    raise JobNotCommitted()
                # A completed job's original object may since have been safely
                # relocated. Redelivery must not resurrect terminal work.
                if job.status in {
                    JobStatus.COMPLETED,
                    JobStatus.CANCELLED,
                    JobStatus.FAILED,
                }:
                    return
                validate_job_target(
                    job, organization_id, document_id, document_version_id, storage_key
                )
                target = await AnalysisTarget.resolve(
                    db, organization_id, document_id, document_version_id, lock=True
                )
                if target.version.storage_path != storage_key:
                    raise ValueError(
                        "Requested document version does not match the processing object"
                    )
                job.status = JobStatus.RUNNING
                from datetime import datetime, timezone

                job.started_at = datetime.now(timezone.utc)
                await db.flush()

                from app.modules.uploads.service import UploadService
                from app.core.object_storage import Minio
                from app.core.config import settings

                storage = Minio(
                    settings.MINIO_ENDPOINT,
                    access_key=settings.MINIO_ACCESS_KEY,
                    secret_key=settings.MINIO_SECRET_KEY,
                    secure=settings.MINIO_SECURE,
                    region=settings.MINIO_REGION,
                )
                upload_service = UploadService(storage)
                content = upload_service.get_file_content(storage_key)

                doc = await doc_service.get_document(document_id, organization_id)
                if not doc:
                    raise ValueError(f"Document {document_id} not found")

                latest_id = (
                    await db.execute(
                        select(DocumentVersion.id)
                        .where(DocumentVersion.document_id == document_id)
                        .order_by(DocumentVersion.version_number.desc())
                        .limit(1)
                    )
                ).scalar_one()
                is_current = str(latest_id) == document_version_id
                if is_current:
                    await doc_service.update_status(
                        document_id, organization_id, DocumentStatus.PROCESSING
                    )
                version = target.version
                processor = DocumentProcessingService(db)
                processed = await processor.process_document(
                    doc, content, document_version_id=str(version.id)
                )

                model_id = "ai-writing-ensemble"
                model_version = "ensemble-orchestrator-v1"
                pipeline_version = "detector-ensemble-v1"
                from sqlalchemy.dialects.postgresql import insert

                await db.execute(
                    insert(ModelRegistry)
                    .values(
                        model_id=model_id,
                        model_version=model_version,
                        pipeline_version=pipeline_version,
                        lifecycle_status=LifecycleStatus.EXPERIMENTAL,
                        limitations=[
                            "No calibrated classifier is registered",
                            "Observed signals are not authorship proof",
                        ],
                        provenance={
                            "implementation": "versioned-signal-provider-ensemble",
                            "feature_version": "signal-features-v1",
                        },
                    )
                    .on_conflict_do_nothing(
                        index_elements=["model_id", "model_version"]
                    )
                )
                analysis_run = AnalysisRun(
                    organization_id=organization_id,
                    document_id=document_id,
                    document_version_id=str(version.id),
                    job_id=job_id,
                    model_id=model_id,
                    model_version=model_version,
                    pipeline_version=pipeline_version,
                    status=AnalysisRunStatus.STARTED,
                    abstained=True,
                    input_fingerprint=version.sha256_fingerprint,
                    started_at=datetime.now(timezone.utc),
                )
                db.add(analysis_run)
                await db.flush()

                detector = DetectionService(db)
                detection_result = await detector.analyze_document(
                    document_id,
                    processed,
                    job_id,
                    document_version_id=str(version.id),
                    analysis_run_id=str(analysis_run.id),
                    organization_id=organization_id,
                    inference_metadata={
                        "input_fingerprint": version.sha256_fingerprint,
                        "source": "celery-document-worker",
                    },
                )
                analysis_run.status = (
                    AnalysisRunStatus.ABSTAINED
                    if detection_result.abstained
                    else AnalysisRunStatus.COMPLETED
                )
                analysis_run.abstained = detection_result.abstained
                analysis_run.completed_at = datetime.now(timezone.utc)

                similarity_matches = await SimilarityService(db).analyze_similarity(
                    document_id, processed
                )
                citations = await CitationService(db).analyze_citations(
                    document_id, processed
                )
                authorship_signal = await AuthorshipService(db).analyze_authorship(
                    document_id, processed
                )
                provenance_event = await ProvenanceService(db).record_event(
                    document_id,
                    ProvenanceEventType.ANALYSIS_RUN,
                    user_id=str(doc.owner_id),
                    description="Document analysis run completed",
                    sha256_after=version.sha256_fingerprint,
                    metadata={
                        "status": analysis_run.status.value,
                        "model_id": model_id,
                        "model_version": model_version,
                        "pipeline_version": pipeline_version,
                    },
                    document_version_id=str(version.id),
                    analysis_run_id=str(analysis_run.id),
                )
                analysis_run.metadata_json = {
                    "parser_version": processed.parser_version,
                    "normalized_content_hash": processed.normalized_content_hash,
                    "structure_fingerprint": processed.structure_fingerprint,
                    "processed_document_id": str(processed.id),
                    "inference_id": detection_result.inference_id,
                    "feature_version": detection_result.feature_version,
                    "confidence_reliability": detection_result.confidence_reliability,
                    "abstention_reason": detection_result.abstention_reason,
                    "similarity_match_count": len(similarity_matches),
                    "citation_count": len(citations),
                    "authorship_verdict": authorship_signal.verdict,
                    "provenance_event_id": str(provenance_event.id),
                }

                await EvidenceService(db).materialize_document_graph(
                    document_id=document_id,
                    organization_id=organization_id,
                    document_version_id=str(version.id),
                )

                if is_current:
                    doc.word_count = processed.word_count
                    doc.language = processed.language
                    await doc_service.update_status(
                        document_id, organization_id, DocumentStatus.COMPLETED
                    )

                job.status = JobStatus.COMPLETED
                job.progress_percent = 100
                job.completed_at = datetime.now(timezone.utc)
                job.result_data = {
                    "organization_id": organization_id,
                    "document_id": document_id,
                    "document_version_id": str(version.id),
                    "parser_version": processed.parser_version,
                    "normalized_content_hash": processed.normalized_content_hash,
                    "word_count": processed.word_count,
                    "detection_verdict": detection_result.overall_verdict.value,
                    "similarity_match_count": len(similarity_matches),
                    "citation_count": len(citations),
                    "authorship_verdict": authorship_signal.verdict,
                }
                from app.modules.billing.usage import UsageService

                await UsageService(db).settle_job(
                    job_id,
                    organization_id,
                    success=True,
                    outcome="completed",
                    duration_ms=round((time.perf_counter() - started) * 1000),
                )
                await db.flush()
                await db.commit()

                logger.info(
                    "document_processing_complete",
                    document_id=document_id,
                    job_id=job_id,
                )

            except Exception as exc:
                logger.error(
                    "document_processing_failed",
                    job_id=job_id,
                    error_type=type(exc).__name__,
                )
                await db.rollback()
                failure = exc

        if failure is not None:
            if isinstance(failure, JobNotCommitted):
                raise self.retry(
                    countdown=2, exc=RuntimeError("Job is not visible yet")
                ) from None
            if await _record_failure(failure):
                record_job_retry("document_processing")
                from app.core.config import settings

                retry_number = max(0, int(getattr(self.request, "retries", 0)))
                countdown = min(
                    settings.CELERY_MAX_RETRY_BACKOFF_SECONDS,
                    settings.CELERY_RETRY_BACKOFF_BASE_SECONDS * (2**retry_number),
                )
                raise self.retry(
                    countdown=countdown, exc=RuntimeError("Document processing failed")
                ) from None
            raise RuntimeError("Document processing failed") from None

    job_type = "document_processing"
    started = time.perf_counter()
    record_job_started(job_type)
    from app.core.observability import safe_span

    try:
        with safe_span("celery.process_document") as span:
            span.set_attribute("celery.task", "process_document")
            span.set_attribute("job.id", job_id)
            span.set_attribute("operation.id", job_id)
            result = _run_with_job_lock(job_id, lambda: asyncio.run(_process()))
    except Exception:
        retrying = int(getattr(self.request, "retries", 0)) < int(
            getattr(self, "max_retries", 0)
        )
        record_job_finished(
            job_type,
            "retrying" if retrying else "failed",
            time.perf_counter() - started,
        )
        raise
    else:
        record_job_finished(job_type, "completed", time.perf_counter() - started)
        return result


if settings.ENVIRONMENT != "production":

    @celery_app.task(name="app.workers.tasks.failure_gate_sleep")
    def failure_gate_sleep(seconds: float) -> str:
        """Failure-injection probe; deliberately unavailable in production."""
        time.sleep(min(max(float(seconds), 0.0), 60.0))
        return "completed"


@celery_app.task(name="app.workers.tasks.deliver_identity_mail", ignore_result=True)
def deliver_identity_mail():
    from app.core.database import AsyncSessionLocal
    from app.modules.auth.mail import deliver_pending

    async def run():
        async with AsyncSessionLocal.begin() as db:
            return await deliver_pending(db)

    return asyncio.run(run())


@celery_app.task(name="app.workers.tasks.erase_private_data")
def erase_private_data():
    from app.modules.privacy.service import run_pending
    from app.modules.privacy.storage import maintenance_client

    return asyncio.run(run_pending(maintenance_client()))


@celery_app.task(name="app.workers.tasks.maintain_private_storage")
def maintain_private_storage():
    from app.modules.privacy.storage import maintenance_client, maintain_storage

    return asyncio.run(maintain_storage(maintenance_client()))


@celery_app.task(name="app.workers.tasks.reconcile_usage")
def reconcile_usage():
    from app.modules.billing.maintenance import maintain_usage

    return asyncio.run(maintain_usage())
