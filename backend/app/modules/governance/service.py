"""Persistence services for frozen evaluation datasets and model promotion."""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.models import (
    DatasetStatus,
    EvaluationDataset,
    EvaluationExample,
    LifecycleStatus,
    ModelRegistry,
)
from app.modules.governance.validation import (
    DATASET_LABELS,
    DatasetRow,
    build_dataset_manifest,
    build_model_evaluation_record,
    validate_dataset_rows,
    validate_provenance,
)


def _to_example(row: DatasetRow, dataset_id: str) -> EvaluationExample:
    return EvaluationExample(
        dataset_id=dataset_id,
        example_key=row.example_key,
        split=row.split,
        label=row.label,
        text_sha256=row.text_sha256,
        author_key_hash=row.author_key_hash,
        domain=row.domain,
        genre=row.genre,
        language=row.language,
        generation_source=row.generation_source,
        editing_intensity=row.editing_intensity,
        document_key_hash=row.document_key_hash,
        source_document_hash=row.source_document_hash,
        document_length=row.document_length,
        writing_proficiency=row.writing_proficiency,
        metadata_json=dict(row.metadata),
    )


def _to_dataset_row(example: EvaluationExample) -> DatasetRow:
    return DatasetRow(
        example_key=example.example_key,
        split=example.split,
        label=example.label,
        text_sha256=example.text_sha256,
        author_key_hash=example.author_key_hash,
        document_key_hash=example.document_key_hash,
        source_document_hash=example.source_document_hash,
        language=example.language,
        domain=example.domain,
        genre=example.genre,
        document_length=example.document_length,
        writing_proficiency=example.writing_proficiency,
        generation_source=example.generation_source,
        editing_intensity=example.editing_intensity,
        metadata=example.metadata_json or {},
    )


class GovernanceService:
    async def create_dataset_version(
        self,
        db: AsyncSession,
        *,
        dataset_id: str,
        version: str,
        description: str,
        rows: Sequence[DatasetRow],
        provenance: Mapping[str, Any],
        schema_json: Mapping[str, Any] | None = None,
        required_labels: Iterable[str] = DATASET_LABELS,
    ) -> EvaluationDataset:
        if (
            not _nonempty(dataset_id)
            or not _nonempty(version)
            or not _nonempty(description)
        ):
            raise ValueError("dataset_id, version, and description are required")
        required_label_set = set(required_labels)
        provenance_report = validate_provenance(provenance)
        if not provenance_report["valid"]:
            raise ValueError(
                f"Dataset provenance is incomplete: {provenance_report['missing']}"
            )
        checks = validate_dataset_rows(
            rows, required_labels=required_label_set, require_group_keys=True
        )
        if not checks["valid"]:
            raise ValueError(f"Dataset validation failed: {checks['errors']}")
        manifest_sha256, _ = build_dataset_manifest(rows, provenance)
        existing = await db.execute(
            select(EvaluationDataset).where(
                EvaluationDataset.dataset_id == dataset_id,
                EvaluationDataset.version == version,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Dataset version already exists: {dataset_id}@{version}")
        dataset = EvaluationDataset(
            dataset_id=dataset_id,
            version=version,
            description=description,
            status=DatasetStatus.VALIDATED,
            schema_json=dict(
                schema_json
                or {
                    "labels": sorted(required_label_set),
                    "row_contract": "DatasetRow-v1",
                }
            ),
            manifest_sha256=manifest_sha256,
            row_count=len(rows),
            leakage_checks={**checks, "provenance": provenance_report},
            provenance_json=dict(provenance),
            immutable=False,
        )
        db.add(dataset)
        await db.flush()
        for row in rows:
            db.add(_to_example(row, str(dataset.id)))
        await db.flush()
        await db.refresh(dataset)
        return dataset

    async def freeze_dataset_version(
        self, db: AsyncSession, dataset: EvaluationDataset
    ) -> EvaluationDataset:
        if dataset.status == DatasetStatus.FROZEN or dataset.immutable:
            return dataset
        if dataset.status != DatasetStatus.VALIDATED:
            raise ValueError("Only a validated dataset can be frozen")
        rows_result = await db.execute(
            select(EvaluationExample).where(
                EvaluationExample.dataset_id == str(dataset.id)
            )
        )
        rows = [_to_dataset_row(example) for example in rows_result.scalars().all()]
        checks = validate_dataset_rows(
            rows,
            required_labels=(dataset.schema_json or {}).get("labels", DATASET_LABELS),
            require_group_keys=True,
        )
        if not checks["valid"]:
            raise ValueError(
                f"Dataset validation failed before freeze: {checks['errors']}"
            )
        manifest_sha256, _ = build_dataset_manifest(rows, dataset.provenance_json or {})
        if manifest_sha256 != dataset.manifest_sha256:
            raise ValueError("Dataset manifest changed before freeze")
        dataset.leakage_checks = {
            **checks,
            "provenance": validate_provenance(dataset.provenance_json or {}),
        }
        dataset.status = DatasetStatus.FROZEN.value
        dataset.immutable = True
        dataset.frozen_at = datetime.now(timezone.utc)
        await db.flush()
        return dataset

    async def register_model_evaluation(
        self,
        db: AsyncSession,
        *,
        dataset: EvaluationDataset,
        model_id: str,
        model_version: str,
        pipeline_version: str,
        report: Mapping[str, Any],
        requested_status: str = "EXPERIMENTAL",
        max_fpr: float = 0.05,
    ) -> ModelRegistry:
        if requested_status == "PRODUCTION" and not dataset.immutable:
            raise ValueError(
                "Production promotion requires an immutable frozen dataset version"
            )
        report_payload = dict(report)
        report_payload["dataset_status"] = (
            dataset.status.value
            if hasattr(dataset.status, "value")
            else str(dataset.status)
        )
        report_payload["leakage_free"] = bool(
            (dataset.leakage_checks or {}).get("valid")
        )
        record = build_model_evaluation_record(
            model_id=model_id,
            model_version=model_version,
            dataset_version=dataset.version,
            pipeline_version=pipeline_version,
            report=report_payload,
            requested_status=requested_status,
            max_fpr=max_fpr,
        )
        existing_result = await db.execute(
            select(ModelRegistry).where(
                ModelRegistry.model_id == model_id,
                ModelRegistry.model_version == model_version,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing and existing.lifecycle_status in {
            LifecycleStatus.PRODUCTION,
            LifecycleStatus.RETIRED,
        }:
            raise ValueError(
                "A production or retired model registry record cannot be mutated"
            )
        registry = existing or ModelRegistry(
            model_id=model_id, model_version=model_version
        )
        registry.pipeline_version = pipeline_version
        registry.dataset_version = dataset.version
        registry.lifecycle_status = LifecycleStatus(requested_status).value
        registry.metrics = record["metrics"]
        registry.limitations = record["limitations"]
        registry.provenance = {
            "dataset_id": dataset.dataset_id,
            "dataset_version": dataset.version,
            "dataset_manifest_sha256": dataset.manifest_sha256,
            "evaluation_report_sha256": sha256(
                _canonical_json(report_payload).encode("utf-8")
            ).hexdigest(),
            "promotion_blockers": record["promotion_blockers"],
        }
        registry.promoted_at = (
            datetime.now(timezone.utc) if requested_status == "PRODUCTION" else None
        )
        if existing is None:
            db.add(registry)
        await db.flush()
        await db.refresh(registry)
        return registry


def _canonical_json(value: Any) -> str:
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _nonempty(value: str | None) -> bool:
    return bool(value and value.strip())
