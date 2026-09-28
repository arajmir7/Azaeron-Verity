"""Require provenance on every evaluation dataset version.

Revision ID: 20260912_0012
Revises: 20260912_0011
Create Date: 2026-09-12
"""

from alembic import op


revision = "20260912_0012"
down_revision = "20260912_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column("evaluation_datasets", "provenance_json", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.alter_column("evaluation_datasets", "provenance_json", nullable=True)
