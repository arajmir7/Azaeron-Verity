"""Require organization/version/pipeline lineage on every analysis output.

Revision ID: 20260912_0006
Revises: 20260912_0005
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0006"
down_revision = "20260912_0005"
branch_labels = None
depends_on = None


LINEAGE_TABLES = (
    "processed_documents",
    "document_chunks",
    "similarity_matches",
    "citations",
    "claims",
    "authorship_signals",
    "provenance_events",
    "provenance_reports",
    "integrity_reports",
    "detection_results",
    "evidence_nodes",
)


def _add_column_if_needed(table: str, column: sa.Column) -> None:
    # This revision is deployed once through Alembic; the helper keeps the
    # intent obvious for operators reading a migration during an incident.
    op.add_column(table, column)


def _add_lineage_columns(
    table: str,
    *,
    organization: bool = True,
    version: bool = True,
    pipeline: bool = True,
    model: bool = True,
) -> None:
    if organization:
        _add_column_if_needed(
            table, sa.Column("organization_id", sa.String(length=36), nullable=True)
        )
    if version:
        _add_column_if_needed(
            table, sa.Column("document_version_id", sa.String(length=36), nullable=True)
        )
    if pipeline:
        _add_column_if_needed(
            table, sa.Column("pipeline_version", sa.String(length=80), nullable=True)
        )
    if model:
        _add_column_if_needed(
            table, sa.Column("model_version", sa.String(length=80), nullable=True)
        )


def _create_lineage_fk(
    table: str,
    column: str,
    target: str,
    name: str,
    ondelete: str = "RESTRICT",
    create_index: bool = True,
) -> None:
    op.create_foreign_key(name, table, target, [column], ["id"], ondelete=ondelete)
    if create_index:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # Historical documents predate immutable version rows. Their current
    # stored object is the only honest source for a version-1 lineage record.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        INSERT INTO document_versions
            (id, created_at, updated_at, document_id, version_number, storage_path,
             sha256_fingerprint, created_by_id, change_summary, edit_type)
        SELECT gen_random_uuid()::text, now(), now(), d.id, 1, d.storage_path,
               d.sha256_fingerprint, d.owner_id, 'Backfilled immutable input version', 'migration'
          FROM documents AS d
         WHERE NOT EXISTS (
             SELECT 1 FROM document_versions AS v
              WHERE v.document_id = d.id AND v.version_number = 1
         )
    """
    )

    _add_lineage_columns("processed_documents", version=False)
    _add_lineage_columns("document_chunks")
    _add_lineage_columns("similarity_matches")
    _add_lineage_columns("citations")
    _add_lineage_columns("claims")
    _add_lineage_columns("authorship_signals", model=False, pipeline=False)
    _add_lineage_columns("provenance_events")
    _add_lineage_columns("provenance_reports")
    _add_lineage_columns("integrity_reports")
    _add_lineage_columns(
        "detection_results", version=False, pipeline=False, model=False
    )
    _add_lineage_columns(
        "evidence_nodes", organization=False, version=False, pipeline=False, model=False
    )

    # Populate only from real document and version records. No scores or
    # labels are invented here; the fields are lineage metadata only.
    updates = {
        "processed_documents": "document-processing-v2",
        "document_chunks": "indexing-tfidf-v1",
        "similarity_matches": "similarity-tfidf-sequence-v1",
        "citations": "citation-extraction-v1",
        "claims": "citation-extraction-v1",
        "authorship_signals": "authorship-pipeline-v1",
        "provenance_events": "provenance-lineage-v1",
        "provenance_reports": "provenance-report-v1",
        "integrity_reports": "integrity-report-v1",
        "detection_results": "uncalibrated-feature-pipeline",
        "evidence_nodes": "evidence-contract-v1",
    }
    for table, pipeline in updates.items():
        version_expression = "COALESCE(t.document_version_id, v.id)"
        op.execute(
            f"""
            UPDATE {table} AS t
               SET organization_id = d.organization_id,
                   document_version_id = {version_expression},
                   pipeline_version = COALESCE(t.pipeline_version, '{pipeline}')
              FROM documents AS d
              JOIN document_versions AS v ON v.document_id = d.id AND v.version_number = 1
             WHERE t.document_id = d.id
        """
        )

    op.execute(
        "UPDATE authorship_signals SET model_version = COALESCE(model_version, 'authorship-unavailable-v1')"
    )
    op.execute(
        "UPDATE document_chunks SET model_version = COALESCE(model_version, 'chunker-v1')"
    )
    op.execute(
        "UPDATE similarity_matches SET model_version = COALESCE(model_version, 'tfidf-sequence-v1')"
    )
    op.execute(
        "UPDATE citations SET model_version = COALESCE(model_version, 'regex-citation-v1')"
    )
    op.execute(
        "UPDATE claims SET model_version = COALESCE(model_version, 'regex-citation-v1')"
    )
    op.execute(
        "UPDATE provenance_events SET model_version = COALESCE(model_version, 'hash-chain-v1')"
    )
    op.execute(
        "UPDATE provenance_reports SET model_version = COALESCE(model_version, 'hash-chain-v1')"
    )
    op.execute(
        "UPDATE integrity_reports SET model_version = COALESCE(model_version, 'report-aggregator-v1')"
    )

    # Replace the old nullable version foreign keys with fail-closed
    # references, then enforce the contract on every analysis table.
    for table in ("processed_documents", "detection_results", "evidence_nodes"):
        op.drop_constraint(f"fk_{table}_document_version", table, type_="foreignkey")
    for table in ("processed_documents", "detection_results", "evidence_nodes"):
        _create_lineage_fk(
            table,
            "document_version_id",
            "document_versions",
            f"fk_{table}_document_version",
            create_index=False,
        )
    for table in (
        "document_chunks",
        "similarity_matches",
        "citations",
        "claims",
        "authorship_signals",
        "provenance_events",
        "provenance_reports",
        "integrity_reports",
    ):
        _create_lineage_fk(
            table, "organization_id", "organizations", f"fk_{table}_organization"
        )
        _create_lineage_fk(
            table,
            "document_version_id",
            "document_versions",
            f"fk_{table}_document_version",
        )
    for table in ("processed_documents", "detection_results"):
        _create_lineage_fk(
            table, "organization_id", "organizations", f"fk_{table}_organization"
        )

    for table in LINEAGE_TABLES:
        op.alter_column(table, "organization_id", nullable=False)
        op.alter_column(table, "document_version_id", nullable=False)
        op.alter_column(table, "pipeline_version", nullable=False)
    for table in (
        "document_chunks",
        "similarity_matches",
        "citations",
        "claims",
        "provenance_events",
        "provenance_reports",
        "integrity_reports",
    ):
        op.alter_column(table, "model_version", nullable=True)

    op.alter_column("analysis_runs", "document_version_id", nullable=False)
    op.drop_constraint(
        "analysis_runs_document_version_id_fkey", "analysis_runs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_analysis_runs_document_version_id",
        "analysis_runs",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint(
        "fk_analysis_runs_document_version_id", "analysis_runs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_analysis_runs_document_version_id",
        "analysis_runs",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("analysis_runs", "document_version_id", nullable=True)
    for table in LINEAGE_TABLES:
        op.alter_column(table, "pipeline_version", nullable=True)
        op.alter_column(table, "document_version_id", nullable=True)
        op.alter_column(table, "organization_id", nullable=True)
    preserved_indexes = {
        ("processed_documents", "document_version_id"),
        ("detection_results", "document_version_id"),
        ("evidence_nodes", "document_version_id"),
        ("evidence_nodes", "organization_id"),
    }
    preserved_constraints = {("evidence_nodes", "organization_id")}
    for table in LINEAGE_TABLES:
        for column in ("organization_id", "document_version_id"):
            if (table, column) not in preserved_indexes:
                op.drop_index(f"ix_{table}_{column}", table_name=table)
            if (table, column) not in preserved_constraints:
                op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
    for table, columns in {
        "processed_documents": ("model_version", "pipeline_version", "organization_id"),
        "document_chunks": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "similarity_matches": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "citations": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "claims": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "authorship_signals": ("document_version_id", "organization_id"),
        "provenance_events": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "provenance_reports": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "integrity_reports": (
            "model_version",
            "pipeline_version",
            "document_version_id",
            "organization_id",
        ),
        "detection_results": ("organization_id",),
        "evidence_nodes": (),
    }.items():
        for column in columns:
            op.drop_column(table, column)
