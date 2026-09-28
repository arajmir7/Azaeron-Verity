"""Enforce tenant isolation for analysis run lineage.

Revision ID: 20260912_0005
Revises: 20260912_0004
Create Date: 2026-09-12
"""

from alembic import op


revision = "20260912_0005"
down_revision = "20260912_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE analysis_runs FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS analysis_runs_tenant_isolation ON analysis_runs")
    op.execute(
        """
        CREATE POLICY analysis_runs_tenant_isolation ON analysis_runs
        USING (organization_id = app.current_organization_id())
        WITH CHECK (organization_id = app.current_organization_id())
    """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP POLICY IF EXISTS analysis_runs_tenant_isolation ON analysis_runs")
