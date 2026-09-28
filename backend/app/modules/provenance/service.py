"""Append-only document provenance, timelines, and secure export snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.core.logging import get_logger
from app.core.security import generate_sha256_fingerprint
from app.modules.documents.models import Document, DocumentVersion
from app.modules.governance.models import AnalysisRun
from app.modules.provenance.models import (
    ProvenanceEvent,
    ProvenanceEventType,
    ProvenanceExport,
    ProvenanceReport,
)

logger = get_logger(__name__)

PIPELINE_VERSION = "provenance-lineage-v2"
MODEL_VERSION = "sha256-provenance-v2"
EXPORT_VERSION = "provenance-export-v1"


class ProvenanceService:
    """All writes are append-only except explicit version lifecycle transitions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_event(
        self,
        document_id: str,
        event_type: ProvenanceEventType,
        user_id: Optional[str] = None,
        description: str | None = None,
        sha256_before: str | None = None,
        sha256_after: str | None = None,
        metadata: dict | None = None,
        document_version_id: str | None = None,
        analysis_run_id: str | None = None,
    ) -> ProvenanceEvent:
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not document:
            raise ValueError("Provenance event requires a document")
        version = None
        if document_version_id:
            version = (
                await self.db.execute(
                    select(DocumentVersion).where(
                        DocumentVersion.id == document_version_id,
                        DocumentVersion.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()
        else:
            version = (
                await self.db.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == document_id)
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        if not version:
            raise ValueError(
                "Provenance event requires an immutable document version lineage"
            )
        if analysis_run_id:
            analysis_run = (
                await self.db.execute(
                    select(AnalysisRun).where(
                        AnalysisRun.id == analysis_run_id,
                        AnalysisRun.document_id == document_id,
                    )
                )
            ).scalar_one_or_none()
            if not analysis_run:
                raise ValueError("Provenance event references an unknown analysis run")
        event = ProvenanceEvent(
            document_id=document_id,
            organization_id=str(document.organization_id),
            document_version_id=str(version.id),
            pipeline_version=PIPELINE_VERSION,
            model_version=MODEL_VERSION,
            event_type=event_type,
            user_id=user_id,
            analysis_run_id=analysis_run_id,
            event_timestamp=datetime.now(timezone.utc),
            description=description or f"Provenance event recorded: {event_type.value}",
            sha256_before=sha256_before,
            sha256_after=sha256_after,
            metadata_json=metadata or {},
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        logger.info(
            "provenance_event_recorded",
            document_id=document_id,
            event_type=event_type.value,
            document_version_id=str(version.id),
        )
        return event

    async def build_timeline(
        self, document_id: str, organization_id: str
    ) -> dict[str, Any]:
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(
                    Document.id == document_id,
                    Document.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if not document:
            raise ValueError("Document not found")
        versions = (
            (
                await self.db.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == document_id)
                    .order_by(DocumentVersion.version_number.asc())
                )
            )
            .scalars()
            .all()
        )
        events = (
            (
                await self.db.execute(
                    select(ProvenanceEvent)
                    .where(
                        ProvenanceEvent.document_id == document_id,
                        ProvenanceEvent.organization_id == organization_id,
                    )
                    .order_by(
                        ProvenanceEvent.event_timestamp.asc(),
                        ProvenanceEvent.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await self.db.execute(
                    select(AnalysisRun)
                    .where(
                        AnalysisRun.document_id == document_id,
                        AnalysisRun.organization_id == organization_id,
                    )
                    .order_by(
                        AnalysisRun.started_at.asc(), AnalysisRun.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return {
            "schema_version": EXPORT_VERSION,
            "document": {
                "id": str(document.id),
                "organization_id": str(document.organization_id),
                "status": (
                    document.status.value
                    if hasattr(document.status, "value")
                    else str(document.status)
                ),
                "content_hash": document.sha256_fingerprint,
                "storage_object": document.storage_path,
                "created_at": self._iso(document.created_at),
                "uploaded_at": self._iso(document.uploaded_at),
            },
            "versions": [self._version_data(version) for version in versions],
            "analysis_runs": [self._run_data(run) for run in runs],
            "provenance_events": [self._event_data(event) for event in events],
            "limitations": [
                "Hashes establish content identity and ordering; they do not establish who authored the content.",
                "Storage object identifiers are included for auditability; document content is not included in this export.",
            ],
        }

    async def export_history(
        self, document_id: str, organization_id: str, user_id: str
    ) -> tuple[ProvenanceExport, dict[str, Any]]:
        timeline = await self.build_timeline(document_id, organization_id)
        latest_version = timeline["versions"][-1] if timeline["versions"] else None
        if not latest_version:
            raise ValueError("Provenance export requires an immutable document version")
        exported_at = datetime.now(timezone.utc)
        payload = {
            **timeline,
            "export": {
                "format": "json",
                "exported_at": exported_at.isoformat(),
                "exported_by": user_id,
                "document_version_id": latest_version["id"],
            },
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        export_hash = generate_sha256_fingerprint(canonical.encode("utf-8"))
        export = ProvenanceExport(
            document_id=document_id,
            organization_id=organization_id,
            document_version_id=latest_version["id"],
            pipeline_version=EXPORT_VERSION,
            model_version="sha256-export-v1",
            exported_by_id=user_id,
            exported_at=exported_at,
            export_format="json",
            export_hash=export_hash,
            payload=payload,
        )
        self.db.add(export)
        await self.db.flush()
        await self.record_event(
            document_id,
            ProvenanceEventType.EXPORTED,
            user_id=user_id,
            description="Provenance history exported as a tenant-authorized JSON snapshot",
            sha256_after=export_hash,
            metadata={
                "export_id": str(export.id),
                "export_hash": export_hash,
                "format": "json",
            },
            document_version_id=latest_version["id"],
        )
        return export, payload

    async def generate_report(self, document_id: str, user_id: str) -> ProvenanceReport:
        """Compatibility report writer; repeated calls never mutate an existing report."""
        document = (
            await self.db.execute(
                select(Document)
                .options(lazyload("*"))
                .where(Document.id == document_id)
            )
        ).scalar_one_or_none()
        if not document:
            raise ValueError("Provenance report requires a tenant-scoped document")
        existing = (
            await self.db.execute(
                select(ProvenanceReport).where(
                    ProvenanceReport.document_id == document_id
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        timeline = await self.build_timeline(document_id, str(document.organization_id))
        report_json = json.dumps(timeline, sort_keys=True, separators=(",", ":"))
        report = ProvenanceReport(
            document_id=document_id,
            organization_id=str(document.organization_id),
            document_version_id=timeline["versions"][-1]["id"],
            pipeline_version="provenance-report-v2",
            model_version=MODEL_VERSION,
            report_hash=generate_sha256_fingerprint(report_json.encode("utf-8")),
            signed_at=None,
            signed_by_id=user_id,
            report_data=timeline,
        )
        self.db.add(report)
        await self.db.flush()
        return report

    @classmethod
    def _version_data(cls, version: DocumentVersion) -> dict[str, Any]:
        return {
            "id": str(version.id),
            "document_id": str(version.document_id),
            "version_number": version.version_number,
            "content_hash": version.content_hash,
            "sha256_fingerprint": version.sha256_fingerprint,
            "created_by_id": (
                str(version.created_by_id) if version.created_by_id else None
            ),
            "uploaded_by_id": (
                str(version.uploaded_by_id) if version.uploaded_by_id else None
            ),
            "created_at": cls._iso(version.created_at),
            "uploaded_at": cls._iso(version.uploaded_at),
            "storage_object": version.storage_path,
            "previous_version_id": (
                str(version.previous_version_id)
                if version.previous_version_id
                else None
            ),
            "lifecycle_state": version.lifecycle_state,
            "change_summary": version.change_summary,
            "edit_type": version.edit_type,
        }

    @classmethod
    def _event_data(cls, event: ProvenanceEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "event_type": event.event_type.value,
            "document_version_id": str(event.document_version_id),
            "analysis_run_id": (
                str(event.analysis_run_id) if event.analysis_run_id else None
            ),
            "user_id": str(event.user_id) if event.user_id else None,
            "event_timestamp": cls._iso(event.event_timestamp),
            "description": event.description,
            "sha256_before": event.sha256_before,
            "sha256_after": event.sha256_after,
            "metadata": event.metadata_json or {},
            "pipeline_version": event.pipeline_version,
            "model_version": event.model_version,
        }

    @classmethod
    def _run_data(cls, run: AnalysisRun) -> dict[str, Any]:
        return {
            "id": str(run.id),
            "document_version_id": str(run.document_version_id),
            "job_id": str(run.job_id) if run.job_id else None,
            "model_id": run.model_id,
            "model_version": run.model_version,
            "pipeline_version": run.pipeline_version,
            "dataset_version": run.dataset_version,
            "status": (
                run.status.value if hasattr(run.status, "value") else str(run.status)
            ),
            "abstained": run.abstained,
            "input_fingerprint": run.input_fingerprint,
            "started_at": cls._iso(run.started_at),
            "completed_at": cls._iso(run.completed_at),
            "metadata": run.metadata_json or {},
        }

    @staticmethod
    def _iso(value: Any) -> str | None:
        return value.isoformat() if value else None
