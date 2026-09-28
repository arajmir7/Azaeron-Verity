"""Bounded worker enumeration for expired usage leases and text receipts."""

from alembic import op

revision = "20260924_0035"
down_revision = "20260924_0034"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """CREATE FUNCTION app.usage_maintenance_candidates() RETURNS SETOF text
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
      SELECT DISTINCT organization_id::text FROM usage_operations
      WHERE (status='RESERVED' AND expires_at<=clock_timestamp())
        OR (response_ciphertext IS NOT NULL AND response_expires_at<=clock_timestamp())
      ORDER BY organization_id::text LIMIT 100
    $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION app.usage_maintenance_candidates() FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app.usage_maintenance_candidates() TO azaeron_app"
    )


def downgrade():
    op.execute("DROP FUNCTION app.usage_maintenance_candidates()")
