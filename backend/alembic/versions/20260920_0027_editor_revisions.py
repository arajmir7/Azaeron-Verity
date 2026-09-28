"""Bind retry identities to immutable editor revisions."""

from alembic import op
import sqlalchemy as sa

revision = "20260920_0027"
down_revision = "20260919_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("operation_id", sa.String(36)))
    op.add_column(
        "document_versions", sa.Column("operation_fingerprint", sa.String(64))
    )
    op.create_unique_constraint(
        "uq_document_versions_operation",
        "document_versions",
        ["document_id", "operation_id"],
    )
    op.create_check_constraint(
        "ck_document_versions_operation",
        "document_versions",
        "(operation_id IS NULL AND operation_fingerprint IS NULL) OR (operation_id IS NOT NULL AND operation_fingerprint IS NOT NULL AND length(operation_fingerprint) = 64)",
    )

    op.execute(
        """CREATE FUNCTION app.freeze_document_operation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.operation_id IS DISTINCT FROM NEW.operation_id
        OR OLD.operation_fingerprint IS DISTINCT FROM NEW.operation_fingerprint THEN
        RAISE EXCEPTION 'document operation identity is immutable';
      END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER document_version_operation_immutable BEFORE UPDATE ON document_versions FOR EACH ROW EXECUTE FUNCTION app.freeze_document_operation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER document_version_operation_immutable ON document_versions")
    op.execute("DROP FUNCTION app.freeze_document_operation()")
    op.drop_constraint(
        "ck_document_versions_operation", "document_versions", type_="check"
    )
    op.drop_constraint(
        "uq_document_versions_operation", "document_versions", type_="unique"
    )
    op.drop_column("document_versions", "operation_fingerprint")
    op.drop_column("document_versions", "operation_id")
