"""Identity challenges, encrypted mail outbox and MFA replay state."""

from alembic import op
import sqlalchemy as sa

revision = "20260920_0029"
down_revision = "20260920_0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("mfa_pending_secret", sa.String(255)))
    op.add_column(
        "users", sa.Column("mfa_pending_expires_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "users",
        sa.Column(
            "mfa_last_counter", sa.Integer(), nullable=False, server_default="-1"
        ),
    )
    op.add_column("users", sa.Column("mfa_recovery_hashes", sa.Text()))

    def common():
        return [
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "user_id",
                sa.String(36),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
        ]

    op.create_table(
        "identity_tokens",
        *common(),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True))
    )
    op.create_index("ix_identity_tokens_user_id", "identity_tokens", ["user_id"])
    op.create_index(
        "ix_identity_tokens_digest", "identity_tokens", ["digest"], unique=True
    )
    op.create_table(
        "identity_mail",
        *common(),
        sa.Column("encrypted_payload", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(40))
    )
    op.create_index("ix_identity_mail_user_id", "identity_mail", ["user_id"])
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON identity_tokens, identity_mail TO azaeron_app"
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM users WHERE mfa_enabled")):
        raise RuntimeError(
            "Cannot remove MFA replay/recovery state while MFA is enabled; use a compatible application rollback"
        )
    op.drop_table("identity_mail")
    op.drop_table("identity_tokens")
    for column in [
        "mfa_recovery_hashes",
        "mfa_last_counter",
        "mfa_pending_expires_at",
        "mfa_pending_secret",
    ]:
        op.drop_column("users", column)
