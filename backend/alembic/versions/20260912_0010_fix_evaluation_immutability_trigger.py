"""Fix the frozen-dataset trigger to allow the initial freeze transition.

Revision ID: 20260912_0010
Revises: 20260912_0009
Create Date: 2026-09-12
"""

from alembic import op


revision = "20260912_0010"
down_revision = "20260912_0009"
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
    # The previous trigger implementation was incorrect for the freeze
    # transition; retaining the corrected function is safer than restoring it.
    return
