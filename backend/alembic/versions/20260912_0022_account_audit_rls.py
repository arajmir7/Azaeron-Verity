"""Isolate account audit events and default new workspaces to the free plan."""

from alembic import op

revision = "20260912_0022"
down_revision = "20260912_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE organizations ALTER COLUMN subscription_tier SET DEFAULT 'FREE'"
    )
    op.execute("DROP POLICY audit_logs_tenant_isolation ON audit_logs")
    predicate = "(organization_id = app.current_organization_id() OR (organization_id IS NULL AND user_id = app.current_user_id()))"
    op.execute(
        f"CREATE POLICY audit_logs_tenant_isolation ON audit_logs USING ({predicate}) WITH CHECK ({predicate})"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE organizations ALTER COLUMN subscription_tier DROP DEFAULT")
    op.execute("DROP POLICY audit_logs_tenant_isolation ON audit_logs")
    predicate = "(organization_id = app.current_organization_id() OR (organization_id IS NULL AND app.current_user_id() IS NULL))"
    op.execute(
        f"CREATE POLICY audit_logs_tenant_isolation ON audit_logs USING ({predicate}) WITH CHECK ({predicate})"
    )
