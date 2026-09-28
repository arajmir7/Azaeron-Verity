"""Add auditable authorship consistency and independent AI-signal fields.

Revision ID: 20260912_0015
Revises: 20260912_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0015"
down_revision = "20260912_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "authorship_signals", sa.Column("stylistic_deviation", sa.JSON(), nullable=True)
    )
    op.add_column(
        "authorship_signals", sa.Column("ai_writing_signal", sa.JSON(), nullable=True)
    )
    op.add_column(
        "authorship_signals",
        sa.Column("confidence_type", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "authorship_signals",
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_authorship_signals_evidence",
        "authorship_signals",
        "evidence_nodes",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_authorship_signals_evidence_id", "authorship_signals", ["evidence_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_authorship_signals_evidence_id", table_name="authorship_signals")
    op.drop_constraint(
        "fk_authorship_signals_evidence", "authorship_signals", type_="foreignkey"
    )
    for column in (
        "evidence_id",
        "confidence_type",
        "ai_writing_signal",
        "stylistic_deviation",
    ):
        op.drop_column("authorship_signals", column)
