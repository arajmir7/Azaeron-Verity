"""Allow deletion of unfrozen evaluation versions while protecting frozen ones.

Revision ID: 20260912_0011
Revises: 20260912_0010
Create Date: 2026-09-12
"""

from alembic import op


revision = "20260912_0011"
down_revision = "20260912_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
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
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
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


def downgrade() -> None:
    return
