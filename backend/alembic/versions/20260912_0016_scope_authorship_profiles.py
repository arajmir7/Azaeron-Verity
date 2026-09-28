"""Tenant-scope authorship baseline profiles.

Revision ID: 20260912_0016
Revises: 20260912_0015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0016"
down_revision = "20260912_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "authorship_profiles",
        sa.Column("organization_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_authorship_profiles_organization",
        "authorship_profiles",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_authorship_profiles_organization_id",
        "authorship_profiles",
        ["organization_id"],
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE authorship_profiles ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE authorship_profiles FORCE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY authorship_profiles_tenant_isolation ON authorship_profiles
            USING (organization_id = app.current_organization_id())
            WITH CHECK (organization_id = app.current_organization_id())
        """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "DROP POLICY IF EXISTS authorship_profiles_tenant_isolation ON authorship_profiles"
        )
    op.drop_index(
        "ix_authorship_profiles_organization_id", table_name="authorship_profiles"
    )
    op.drop_constraint(
        "fk_authorship_profiles_organization", "authorship_profiles", type_="foreignkey"
    )
    op.drop_column("authorship_profiles", "organization_id")
