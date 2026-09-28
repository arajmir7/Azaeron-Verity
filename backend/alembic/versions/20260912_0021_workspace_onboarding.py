"""Persist product persona and authorized workspace preferences.

Revision ID: 20260912_0021
Revises: 20260912_0020
"""

from alembic import op
import sqlalchemy as sa

revision = "20260912_0021"
down_revision = "20260912_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    additions = (
        sa.Column("product_role", sa.String(30), nullable=True),
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("personal_organization_id", sa.String(36), nullable=True),
        sa.Column("last_active_organization_id", sa.String(36), nullable=True),
    )
    for column in additions:
        if column.name not in columns:
            op.add_column("users", column)
    if bind.dialect.name == "postgresql":
        foreign_keys = {
            tuple(constraint["constrained_columns"])
            for constraint in sa.inspect(bind).get_foreign_keys("users")
        }
        for column in ("personal_organization_id", "last_active_organization_id"):
            if (column,) not in foreign_keys:
                op.create_foreign_key(
                    f"fk_users_{column}",
                    "users",
                    "organizations",
                    [column],
                    ["id"],
                    ondelete="SET NULL",
                )
        op.create_check_constraint(
            "ck_users_product_role",
            "users",
            "product_role IS NULL OR product_role IN ('student', 'teacher', 'professor', 'researcher', 'reviewer', 'institution')",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("ck_users_product_role", "users", type_="check")
    for column in (
        "last_active_organization_id",
        "personal_organization_id",
        "onboarding_completed",
        "product_role",
    ):
        op.drop_column("users", column)
