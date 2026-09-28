"""Versioned similarity snapshots and per-version processed text.

Revision ID: 20260913_0023
Revises: 20260912_0022
"""

from alembic import op
import sqlalchemy as sa

revision = "20260913_0023"
down_revision = "20260912_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "ix_processed_documents_document_id", table_name="processed_documents"
    )
    op.create_index(
        "ix_processed_documents_document_id", "processed_documents", ["document_id"]
    )
    op.create_unique_constraint(
        "uq_processed_documents_version", "processed_documents", ["document_version_id"]
    )
    op.create_table(
        "similarity_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("pipeline_version", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(80)),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("corpus_state", sa.String(30), nullable=False),
        sa.Column("corpus_version_count", sa.Integer(), nullable=False),
        sa.Column("index_version", sa.String(80), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "document_version_id",
            "pipeline_version",
            name="uq_similarity_analysis_version_pipeline",
        ),
    )
    for column in ("organization_id", "document_id", "document_version_id"):
        op.create_index(
            f"ix_similarity_analyses_{column}", "similarity_analyses", [column]
        )
    op.add_column(
        "similarity_matches",
        sa.Column("source_document_version_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "similarity_matches", sa.Column("analysis_id", sa.String(36), nullable=True)
    )
    op.create_foreign_key(
        "fk_similarity_source_version",
        "similarity_matches",
        "document_versions",
        ["source_document_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_similarity_analysis",
        "similarity_matches",
        "similarity_analyses",
        ["analysis_id"],
        ["id"],
        ondelete="CASCADE",
    )
    for column in ("source_document_version_id", "analysis_id"):
        op.create_index(
            f"ix_similarity_matches_{column}", "similarity_matches", [column]
        )
    op.create_index(
        "ix_similarity_index_lookup",
        "similarity_index_entries",
        ["organization_id", "index_version", "term_type", "term"],
    )
    op.execute("ALTER TABLE similarity_analyses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE similarity_analyses FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY similarity_analyses_tenant_isolation ON similarity_analyses
        USING (organization_id = app.current_organization_id())
        WITH CHECK (organization_id = app.current_organization_id())"""
    )


def downgrade() -> None:
    # Restoring document-wide uniqueness is impossible once multiple versions
    # exist. Fail without deleting historical data in that case.
    op.create_index(
        "rollback_processed_document_unique",
        "processed_documents",
        ["document_id"],
        unique=True,
    )
    op.drop_index("ix_similarity_index_lookup", table_name="similarity_index_entries")
    for column, constraint in (
        ("analysis_id", "fk_similarity_analysis"),
        ("source_document_version_id", "fk_similarity_source_version"),
    ):
        op.drop_constraint(constraint, "similarity_matches", type_="foreignkey")
        op.drop_index(
            f"ix_similarity_matches_{column}", table_name="similarity_matches"
        )
        op.drop_column("similarity_matches", column)
    op.drop_table("similarity_analyses")
    op.drop_constraint(
        "uq_processed_documents_version", "processed_documents", type_="unique"
    )
    op.drop_index(
        "ix_processed_documents_document_id", table_name="processed_documents"
    )
    op.execute(
        "ALTER INDEX rollback_processed_document_unique RENAME TO ix_processed_documents_document_id"
    )
