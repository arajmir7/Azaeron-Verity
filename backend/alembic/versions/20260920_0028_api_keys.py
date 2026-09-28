"""Versioned, revocable API key credentials; legacy records are never accepted."""

from alembic import op
import sqlalchemy as sa

revision = "20260920_0028"
down_revision = "20260920_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "credential_version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.alter_column("api_keys", "credential_version", server_default="1")
    op.add_column("api_keys", sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.add_column(
        "api_keys",
        sa.Column(
            "rotated_from_id",
            sa.String(36),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
        ),
    )
    op.create_index(
        "uq_api_keys_v1_digest",
        "api_keys",
        ["hashed_key"],
        unique=True,
        postgresql_where=sa.text("credential_version = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_api_keys_v1_digest", table_name="api_keys")
    op.drop_column("api_keys", "rotated_from_id")
    op.drop_column("api_keys", "revoked_at")
    op.drop_column("api_keys", "credential_version")
