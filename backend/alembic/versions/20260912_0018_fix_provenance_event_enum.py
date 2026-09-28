"""Add the SQLAlchemy enum member name used for analysis-run events.

Revision ID: 20260912_0018
Revises: 20260912_0017
"""

from alembic import op


revision = "20260912_0018"
down_revision = "20260912_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Existing provenanceeventtype values are SQLAlchemy Enum member
        # names (CREATED, REVISION, ...), not Python Enum .value strings.
        op.execute(
            "ALTER TYPE provenanceeventtype ADD VALUE IF NOT EXISTS 'ANALYSIS_RUN'"
        )


def downgrade() -> None:
    # PostgreSQL does not safely remove enum labels in-place. The label is
    # harmless for historical schemas and is retained on downgrade.
    pass
