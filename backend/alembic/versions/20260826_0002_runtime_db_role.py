"""Create a non-superuser database role for runtime services.

Revision ID: 20260826_0002
Revises: 20260826_0001
Create Date: 2026-08-26
"""

import os

from alembic import op


revision = "20260826_0002"
down_revision = "20260826_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Separate migration authority from the runtime RLS subject."""
    if op.get_bind().dialect.name != "postgresql":
        return
    password = os.environ.get("APP_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "APP_DB_PASSWORD is required to provision the runtime database role"
        )
    escaped_password = password.replace("'", "''")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'azaeron_app') THEN
            CREATE ROLE azaeron_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{escaped_password}';
          ELSE
            ALTER ROLE azaeron_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{escaped_password}';
          END IF;
        END $$;
    """
    )
    op.execute("GRANT USAGE ON SCHEMA public, app TO azaeron_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO azaeron_app"
    )
    op.execute(
        "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO azaeron_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO azaeron_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO azaeron_app"
    )


def downgrade() -> None:
    # Preserve the role: dropping it could break a running deployment and
    # revoke ownership-independent access unexpectedly.
    pass
