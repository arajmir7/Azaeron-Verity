"""Invalidate issued access tokens after logout, password change and replay."""

from alembic import op
import sqlalchemy as sa

revision = "20260919_0026"
down_revision = "20260913_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_users_session_version", "users", "session_version >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_session_version", "users", type_="check")
    op.drop_column("users", "session_version")
