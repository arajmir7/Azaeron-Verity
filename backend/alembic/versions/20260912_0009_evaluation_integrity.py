"""Make evaluation dataset versions provenance-aware and immutable when frozen.

Revision ID: 20260912_0009
Revises: 20260912_0008
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0009"
down_revision = "20260912_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "evaluation_datasets", sa.Column("provenance_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "evaluation_datasets", sa.Column("immutable", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "evaluation_datasets",
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE evaluation_datasets SET immutable = false WHERE immutable IS NULL"
    )
    op.alter_column(
        "evaluation_datasets",
        "immutable",
        nullable=False,
        server_default=sa.text("false"),
    )

    op.add_column(
        "evaluation_examples",
        sa.Column("document_key_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "evaluation_examples",
        sa.Column("source_document_hash", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "evaluation_examples", sa.Column("document_length", sa.Integer(), nullable=True)
    )
    op.add_column(
        "evaluation_examples",
        sa.Column("writing_proficiency", sa.String(length=80), nullable=True),
    )
    op.create_index(
        "ix_evaluation_examples_document_key_hash",
        "evaluation_examples",
        ["document_key_hash"],
    )
    op.create_index(
        "ix_evaluation_examples_source_document_hash",
        "evaluation_examples",
        ["source_document_hash"],
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.prevent_frozen_evaluation_dataset_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_TABLE_NAME = 'evaluation_datasets' THEN
                IF OLD.immutable OR OLD.status IN ('FROZEN', 'RETIRED') THEN
                    RAISE EXCEPTION 'evaluation dataset version % is immutable', OLD.id;
                END IF;
                RETURN NEW;
            END IF;

            IF EXISTS (
                SELECT 1 FROM evaluation_datasets
                 WHERE id = COALESCE(NEW.dataset_id, OLD.dataset_id)
                   AND (immutable OR status IN ('FROZEN', 'RETIRED'))
            ) THEN
                RAISE EXCEPTION 'evaluation examples for a frozen dataset are immutable';
            END IF;
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END;
        $$
    """
    )
    op.execute(
        """
        CREATE TRIGGER evaluation_datasets_immutable_guard
        BEFORE UPDATE OR DELETE ON evaluation_datasets
        FOR EACH ROW EXECUTE FUNCTION app.prevent_frozen_evaluation_dataset_mutation()
    """
    )
    op.execute(
        """
        CREATE TRIGGER evaluation_examples_immutable_guard
        BEFORE INSERT OR UPDATE OR DELETE ON evaluation_examples
        FOR EACH ROW EXECUTE FUNCTION app.prevent_frozen_evaluation_dataset_mutation()
    """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DROP TRIGGER IF EXISTS evaluation_examples_immutable_guard ON evaluation_examples"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS evaluation_datasets_immutable_guard ON evaluation_datasets"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.prevent_frozen_evaluation_dataset_mutation()"
    )
    op.drop_index(
        "ix_evaluation_examples_source_document_hash", table_name="evaluation_examples"
    )
    op.drop_index(
        "ix_evaluation_examples_document_key_hash", table_name="evaluation_examples"
    )
    for column in (
        "writing_proficiency",
        "document_length",
        "source_document_hash",
        "document_key_hash",
    ):
        op.drop_column("evaluation_examples", column)
    for column in ("frozen_at", "immutable", "provenance_json"):
        op.drop_column("evaluation_datasets", column)
