"""Make document provenance versioned, append-only, and exportable.

Revision ID: 20260912_0017
Revises: 20260912_0016
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0017"
down_revision = "20260912_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE documents SET uploaded_at = created_at WHERE uploaded_at IS NULL"
    )
    op.alter_column("documents", "uploaded_at", nullable=False)

    op.add_column(
        "document_versions",
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("previous_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "lifecycle_state",
            sa.String(length=20),
            nullable=True,
            server_default="DRAFT",
        ),
    )
    op.execute(
        "UPDATE document_versions SET content_hash = sha256_fingerprint WHERE content_hash IS NULL"
    )
    op.execute(
        "UPDATE document_versions SET uploaded_at = created_at WHERE uploaded_at IS NULL"
    )
    op.execute(
        "UPDATE document_versions SET lifecycle_state = 'DRAFT' WHERE lifecycle_state IS NULL"
    )
    op.alter_column("document_versions", "uploaded_at", nullable=False)
    op.alter_column("document_versions", "content_hash", nullable=False)
    op.alter_column("document_versions", "lifecycle_state", nullable=False)
    op.create_foreign_key(
        "fk_document_versions_uploaded_by",
        "document_versions",
        "users",
        ["uploaded_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_versions_previous",
        "document_versions",
        "document_versions",
        ["previous_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_versions_uploaded_by_id", "document_versions", ["uploaded_by_id"]
    )
    op.create_index(
        "ix_document_versions_previous_version_id",
        "document_versions",
        ["previous_version_id"],
    )
    op.create_check_constraint(
        "ck_document_versions_content_hash_length",
        "document_versions",
        "length(content_hash) = 64",
    )
    op.create_check_constraint(
        "ck_document_versions_lifecycle_state",
        "document_versions",
        "lifecycle_state IN ('DRAFT', 'REVISION', 'FINAL')",
    )

    op.add_column(
        "provenance_events",
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_provenance_events_analysis_run",
        "provenance_events",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_provenance_events_analysis_run_id", "provenance_events", ["analysis_run_id"]
    )

    op.create_table(
        "provenance_exports",
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
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80)),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("exported_by_id", sa.String(length=36), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "export_format", sa.String(length=20), nullable=False, server_default="json"
        ),
        sa.Column("export_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exported_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("export_hash", name="uq_provenance_exports_hash"),
    )
    for name, column in (
        ("ix_provenance_exports_organization_id", "organization_id"),
        ("ix_provenance_exports_document_id", "document_id"),
        ("ix_provenance_exports_document_version_id", "document_version_id"),
        ("ix_provenance_exports_exported_by_id", "exported_by_id"),
    ):
        op.create_index(name, "provenance_exports", [column])

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TYPE provenanceeventtype ADD VALUE IF NOT EXISTS 'analysis_run'")
    op.execute("ALTER TABLE provenance_exports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE provenance_exports FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY provenance_exports_tenant_isolation ON provenance_exports
        USING (organization_id = app.current_organization_id())
        WITH CHECK (organization_id = app.current_organization_id())
    """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.prevent_document_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE old_rank integer; new_rank integer;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'document versions are append-only';
          END IF;
          IF OLD.document_id IS DISTINCT FROM NEW.document_id
             OR OLD.version_number IS DISTINCT FROM NEW.version_number
             OR OLD.storage_path IS DISTINCT FROM NEW.storage_path
             OR OLD.content_hash IS DISTINCT FROM NEW.content_hash
             OR OLD.sha256_fingerprint IS DISTINCT FROM NEW.sha256_fingerprint
             OR OLD.created_by_id IS DISTINCT FROM NEW.created_by_id
             OR OLD.uploaded_by_id IS DISTINCT FROM NEW.uploaded_by_id
             OR OLD.uploaded_at IS DISTINCT FROM NEW.uploaded_at
             OR OLD.previous_version_id IS DISTINCT FROM NEW.previous_version_id
             OR OLD.change_summary IS DISTINCT FROM NEW.change_summary
             OR OLD.edit_type IS DISTINCT FROM NEW.edit_type THEN
            RAISE EXCEPTION 'historical document version content and lineage are immutable';
          END IF;
          old_rank := CASE OLD.lifecycle_state WHEN 'DRAFT' THEN 0 WHEN 'REVISION' THEN 1 WHEN 'FINAL' THEN 2 ELSE -1 END;
          new_rank := CASE NEW.lifecycle_state WHEN 'DRAFT' THEN 0 WHEN 'REVISION' THEN 1 WHEN 'FINAL' THEN 2 ELSE -1 END;
          IF new_rank < old_rank OR new_rank > old_rank + 1 THEN
            RAISE EXCEPTION 'document lifecycle transitions must be monotonic and sequential';
          END IF;
          RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER document_versions_append_only
        BEFORE UPDATE OR DELETE ON document_versions
        FOR EACH ROW EXECUTE FUNCTION app.prevent_document_version_mutation()
    """
    )
    for table in ("provenance_events", "provenance_exports", "provenance_reports"):
        function_name = f"app.prevent_{table}_mutation"
        trigger_name = f"{table}_append_only"
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION '{table} are append-only';
            END;
            $$
        """
        )
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
        """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("provenance_events", "provenance_exports", "provenance_reports"):
            op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
            op.execute(f"DROP FUNCTION IF EXISTS app.prevent_{table}_mutation()")
        op.execute(
            "DROP TRIGGER IF EXISTS document_versions_append_only ON document_versions"
        )
        op.execute("DROP FUNCTION IF EXISTS app.prevent_document_version_mutation()")
        op.execute(
            "DROP POLICY IF EXISTS provenance_exports_tenant_isolation ON provenance_exports"
        )
    for name, table in (
        ("ix_provenance_exports_exported_by_id", "provenance_exports"),
        ("ix_provenance_exports_document_version_id", "provenance_exports"),
        ("ix_provenance_exports_document_id", "provenance_exports"),
        ("ix_provenance_exports_organization_id", "provenance_exports"),
        ("ix_provenance_events_analysis_run_id", "provenance_events"),
        ("ix_document_versions_previous_version_id", "document_versions"),
        ("ix_document_versions_uploaded_by_id", "document_versions"),
    ):
        op.drop_index(name, table_name=table)
    op.drop_table("provenance_exports")
    op.drop_constraint(
        "fk_provenance_events_analysis_run", "provenance_events", type_="foreignkey"
    )
    op.drop_column("provenance_events", "analysis_run_id")
    op.drop_constraint(
        "ck_document_versions_lifecycle_state", "document_versions", type_="check"
    )
    op.drop_constraint(
        "ck_document_versions_content_hash_length", "document_versions", type_="check"
    )
    op.drop_constraint(
        "fk_document_versions_previous", "document_versions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_document_versions_uploaded_by", "document_versions", type_="foreignkey"
    )
    for column in (
        "lifecycle_state",
        "previous_version_id",
        "content_hash",
        "uploaded_by_id",
        "uploaded_at",
    ):
        op.drop_column("document_versions", column)
    op.drop_column("documents", "uploaded_at")
