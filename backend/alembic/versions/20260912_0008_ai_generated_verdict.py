"""Add the explicit AI_GENERATED state while preserving historical AI rows.

Revision ID: 20260912_0008
Revises: 20260912_0007
Create Date: 2026-09-12
"""

from alembic import op


revision = "20260912_0008"
down_revision = "20260912_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE detectionverdict ADD VALUE IF NOT EXISTS 'AI_GENERATED'")


def downgrade() -> None:
    # PostgreSQL cannot safely remove an enum value in-place. The value is
    # additive and unused by historical rows, so the downgrade is a no-op.
    return
