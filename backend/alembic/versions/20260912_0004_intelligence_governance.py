"""Add intelligence governance, run lineage, and honest abstention metadata.

Revision ID: 20260912_0004
Revises: 20260910_0003
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0004"
down_revision = "20260910_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("dataset_version", sa.String(length=120)),
        sa.Column(
            "lifecycle_status",
            sa.String(length=20),
            nullable=False,
            server_default="EXPERIMENTAL",
        ),
        sa.Column("metrics", sa.JSON()),
        sa.Column("limitations", sa.JSON()),
        sa.Column("provenance", sa.JSON()),
        sa.Column("promoted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "model_id", "model_version", name="uq_model_registry_identity"
        ),
    )
    op.create_index("ix_model_registry_model_id", "model_registry", ["model_id"])

    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="DRAFT"
        ),
        sa.Column("schema_json", sa.JSON()),
        sa.Column("manifest_sha256", sa.String(length=64)),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("leakage_checks", sa.JSON()),
        sa.UniqueConstraint(
            "dataset_id", "version", name="uq_evaluation_dataset_identity"
        ),
    )
    op.create_index(
        "ix_evaluation_datasets_dataset_id", "evaluation_datasets", ["dataset_id"]
    )

    op.create_table(
        "evaluation_examples",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("example_key", sa.String(length=180), nullable=False),
        sa.Column("split", sa.String(length=30), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("author_key_hash", sa.String(length=128)),
        sa.Column("domain", sa.String(length=120)),
        sa.Column("genre", sa.String(length=120)),
        sa.Column("language", sa.String(length=20)),
        sa.Column("generation_source", sa.String(length=120)),
        sa.Column("editing_intensity", sa.String(length=80)),
        sa.Column("metadata_json", sa.JSON()),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["evaluation_datasets.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "dataset_id", "example_key", name="uq_evaluation_example_key"
        ),
    )
    op.create_index(
        "ix_evaluation_examples_dataset_id", "evaluation_examples", ["dataset_id"]
    )
    op.create_index(
        "ix_evaluation_examples_text_sha256", "evaluation_examples", ["text_sha256"]
    )
    op.create_index(
        "ix_evaluation_examples_author_key_hash",
        "evaluation_examples",
        ["author_key_hash"],
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36)),
        sa.Column("job_id", sa.String(length=36)),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("dataset_version", sa.String(length=120)),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="STARTED"
        ),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("input_fingerprint", sa.String(length=64)),
        sa.Column("metadata_json", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    for name, column in (
        ("ix_analysis_runs_organization_id", "organization_id"),
        ("ix_analysis_runs_document_id", "document_id"),
        ("ix_analysis_runs_document_version_id", "document_version_id"),
        ("ix_analysis_runs_job_id", "job_id"),
    ):
        op.create_index(name, "analysis_runs", [column])

    op.add_column(
        "processed_documents",
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_processed_documents_document_version",
        "processed_documents",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_processed_documents_document_version_id",
        "processed_documents",
        ["document_version_id"],
    )

    op.add_column(
        "authorship_signals",
        sa.Column(
            "verdict",
            sa.String(length=40),
            nullable=True,
            server_default="INSUFFICIENT_DATA",
        ),
    )
    op.add_column(
        "authorship_signals",
        sa.Column("baseline_quality", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "authorship_signals",
        sa.Column(
            "model_version",
            sa.String(length=80),
            nullable=True,
            server_default="authorship-unavailable-v1",
        ),
    )
    op.add_column(
        "authorship_signals",
        sa.Column(
            "pipeline_version",
            sa.String(length=80),
            nullable=True,
            server_default="authorship-pipeline-v1",
        ),
    )
    op.add_column(
        "authorship_signals", sa.Column("feature_data", sa.JSON(), nullable=True)
    )
    op.alter_column("authorship_signals", "consistency_score", nullable=True)
    op.alter_column("authorship_signals", "confidence", nullable=True)
    op.execute(
        "UPDATE authorship_signals SET verdict = 'INSUFFICIENT_DATA' WHERE verdict IS NULL"
    )
    op.execute(
        "UPDATE authorship_signals SET model_version = 'authorship-unavailable-v1' WHERE model_version IS NULL"
    )
    op.execute(
        "UPDATE authorship_signals SET pipeline_version = 'authorship-pipeline-v1' WHERE pipeline_version IS NULL"
    )
    op.alter_column("authorship_signals", "verdict", nullable=False)
    op.alter_column("authorship_signals", "model_version", nullable=False)
    op.alter_column("authorship_signals", "pipeline_version", nullable=False)

    op.add_column(
        "detection_results",
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column(
            "release_status",
            sa.String(length=20),
            nullable=True,
            server_default="EXPERIMENTAL",
        ),
    )
    op.add_column(
        "detection_results",
        sa.Column("abstained", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    op.create_foreign_key(
        "fk_detection_results_document_version",
        "detection_results",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_detection_results_analysis_run",
        "detection_results",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_detection_results_document_version_id",
        "detection_results",
        ["document_version_id"],
    )
    op.create_index(
        "ix_detection_results_analysis_run_id", "detection_results", ["analysis_run_id"]
    )
    op.execute(
        "UPDATE detection_results SET release_status = 'EXPERIMENTAL' WHERE release_status IS NULL"
    )
    op.execute("UPDATE detection_results SET abstained = TRUE WHERE abstained IS NULL")
    op.alter_column("detection_results", "release_status", nullable=False)
    op.alter_column("detection_results", "abstained", nullable=False)

    op.add_column(
        "evidence_nodes",
        sa.Column("organization_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "evidence_nodes",
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "evidence_nodes",
        sa.Column(
            "finding_type",
            sa.String(length=80),
            nullable=True,
            server_default="evidence",
        ),
    )
    op.add_column(
        "evidence_nodes", sa.Column("source_id", sa.String(length=180), nullable=True)
    )
    op.add_column(
        "evidence_nodes", sa.Column("model_id", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "evidence_nodes",
        sa.Column("model_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "evidence_nodes",
        sa.Column("pipeline_version", sa.String(length=80), nullable=True),
    )
    op.execute(
        "UPDATE evidence_nodes AS node SET organization_id = document.organization_id FROM documents AS document WHERE document.id = node.document_id"
    )
    op.execute(
        "UPDATE evidence_nodes SET finding_type = node_type::text WHERE finding_type IS NULL OR finding_type = 'evidence'"
    )
    op.create_foreign_key(
        "fk_evidence_nodes_organization",
        "evidence_nodes",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_evidence_nodes_document_version",
        "evidence_nodes",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_evidence_nodes_organization_id", "evidence_nodes", ["organization_id"]
    )
    op.create_index(
        "ix_evidence_nodes_document_version_id",
        "evidence_nodes",
        ["document_version_id"],
    )
    op.alter_column("evidence_nodes", "finding_type", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for name, table in (
        ("ix_evidence_nodes_document_version_id", "evidence_nodes"),
        ("ix_evidence_nodes_organization_id", "evidence_nodes"),
        ("ix_detection_results_analysis_run_id", "detection_results"),
        ("ix_detection_results_document_version_id", "detection_results"),
        ("ix_processed_documents_document_version_id", "processed_documents"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_constraint(
        "fk_evidence_nodes_document_version", "evidence_nodes", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_evidence_nodes_organization", "evidence_nodes", type_="foreignkey"
    )
    for column in (
        "pipeline_version",
        "model_version",
        "model_id",
        "source_id",
        "finding_type",
        "document_version_id",
        "organization_id",
    ):
        op.drop_column("evidence_nodes", column)
    op.drop_constraint(
        "fk_detection_results_analysis_run", "detection_results", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_detection_results_document_version", "detection_results", type_="foreignkey"
    )
    for column in (
        "abstained",
        "release_status",
        "analysis_run_id",
        "document_version_id",
    ):
        op.drop_column("detection_results", column)
    for column in (
        "feature_data",
        "pipeline_version",
        "model_version",
        "baseline_quality",
        "verdict",
    ):
        op.drop_column("authorship_signals", column)
    op.alter_column("authorship_signals", "consistency_score", nullable=False)
    op.alter_column("authorship_signals", "confidence", nullable=False)
    op.drop_constraint(
        "fk_processed_documents_document_version",
        "processed_documents",
        type_="foreignkey",
    )
    op.drop_column("processed_documents", "document_version_id")
    op.drop_table("analysis_runs")
    op.drop_table("evaluation_examples")
    op.drop_table("evaluation_datasets")
    op.drop_table("model_registry")
