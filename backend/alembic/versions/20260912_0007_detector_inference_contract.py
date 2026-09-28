"""Add explicit detector inference, calibration, and evidence metadata.

Revision ID: 20260912_0007
Revises: 20260912_0006
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0007"
down_revision = "20260912_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "detection_results",
        sa.Column("feature_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("calibrator_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("uncertainty_method", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("confidence_reliability", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("inference_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "detection_results",
        sa.Column("inference_metadata_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "detection_results", sa.Column("evidence_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "detection_results", sa.Column("abstention_reason", sa.Text(), nullable=True)
    )

    op.execute(
        "UPDATE detection_results SET feature_version = 'feature-extraction-v1' WHERE feature_version IS NULL"
    )
    op.execute(
        "UPDATE detection_results SET confidence_reliability = 'UNAVAILABLE' WHERE confidence_reliability IS NULL"
    )
    op.execute(
        "UPDATE detection_results SET inference_id = id WHERE inference_id IS NULL"
    )
    op.execute(
        "UPDATE detection_results SET evidence_json = '[]'::json WHERE evidence_json IS NULL"
    )

    op.alter_column("detection_results", "feature_version", nullable=False)
    op.alter_column(
        "detection_results",
        "confidence_reliability",
        nullable=False,
        server_default="UNAVAILABLE",
    )
    op.alter_column("detection_results", "inference_id", nullable=False)
    op.alter_column(
        "detection_results",
        "evidence_json",
        nullable=False,
        server_default=sa.text("'[]'::json"),
    )
    op.alter_column("detection_results", "confidence", nullable=True)
    op.alter_column("detection_results", "human_probability", nullable=True)
    op.alter_column("detection_results", "ai_probability", nullable=True)
    op.alter_column("detection_results", "mixed_probability", nullable=True)
    op.alter_column("detection_results", "uncertain_probability", nullable=True)
    op.create_index(
        "ix_detection_results_inference_id", "detection_results", ["inference_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_index("ix_detection_results_inference_id", table_name="detection_results")
    op.alter_column("detection_results", "uncertain_probability", nullable=False)
    op.alter_column("detection_results", "mixed_probability", nullable=False)
    op.alter_column("detection_results", "ai_probability", nullable=False)
    op.alter_column("detection_results", "human_probability", nullable=False)
    op.alter_column("detection_results", "confidence", nullable=False)
    op.drop_column("detection_results", "abstention_reason")
    op.drop_column("detection_results", "evidence_json")
    op.drop_column("detection_results", "inference_metadata_json")
    op.drop_column("detection_results", "inference_id")
    op.drop_column("detection_results", "confidence_reliability")
    op.drop_column("detection_results", "uncertainty_method")
    op.drop_column("detection_results", "calibrator_version")
    op.drop_column("detection_results", "feature_version")
