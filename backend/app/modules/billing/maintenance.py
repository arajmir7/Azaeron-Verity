"""Reconcile crashed work and erase expired cached text without forgiving usage."""

from sqlalchemy import select, text, update

from app.core.database import AsyncSessionLocal, apply_tenant_context
from app.modules.billing.models import UsageOperation
from app.modules.billing.usage import UsageService, now
from app.modules.jobs.models import Job, JobStatus


async def maintain_usage():
    report = {"organizations": 0, "released": 0, "receipts_expired": 0}
    async with AsyncSessionLocal() as db:
        organizations = list(
            (
                await db.scalars(
                    text("SELECT * FROM app.usage_maintenance_candidates()")
                )
            ).all()
        )
        await db.commit()
        for org in organizations:
            await apply_tenant_context(db, org, None)
            service = UsageService(db)
            # Lock job rows first, matching worker settlement order. Active worker
            # transactions are skipped; their hard time limit bounds recovery.
            jobs = list(
                (
                    await db.scalars(
                        select(Job)
                        .join(UsageOperation, UsageOperation.job_id == Job.id)
                        .where(
                            UsageOperation.organization_id == org,
                            UsageOperation.status == "RESERVED",
                            UsageOperation.expires_at <= now(),
                        )
                        .with_for_update(of=Job, skip_locked=True)
                        .limit(100)
                    )
                ).all()
            )
            await service.lock(org)
            report["released"] += await service.expire(org)
            for job in jobs:
                success = job.status == JobStatus.COMPLETED
                if job.status not in {
                    JobStatus.COMPLETED,
                    JobStatus.CANCELLED,
                    JobStatus.FAILED,
                }:
                    job.status = JobStatus.FAILED
                    job.error_message = "Processing lease expired before completion; create a new revision to retry."
                await service.settle_job(
                    str(job.id),
                    org,
                    success=success,
                    outcome="completed" if success else "lease_expired",
                )
                report["released"] += int(not success)
            changed = await db.execute(
                update(UsageOperation)
                .where(
                    UsageOperation.organization_id == org,
                    UsageOperation.response_ciphertext.is_not(None),
                    UsageOperation.response_expires_at <= now(),
                )
                .values(response_ciphertext=None)
            )
            report["receipts_expired"] += changed.rowcount
            await db.commit()
            report["organizations"] += 1
    return report
