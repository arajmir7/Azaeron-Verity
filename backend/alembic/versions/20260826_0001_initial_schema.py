"""Create the initial AZAERON schema and tenant RLS policies.

Revision ID: 20260826_0001
Revises:
Create Date: 2026-08-26
"""

from alembic import op
from migration_snapshots.initial_20260826 import metadata

revision = "20260826_0001"
down_revision = None
branch_labels = None
depends_on = None

DIRECT_TENANT_TABLES = (
    "api_keys",
    "documents",
    "jobs",
    "assignments",
    "audit_logs",
    "compliance_reports",
    "billing_events",
)
DOCUMENT_TENANT_TABLES = (
    "document_versions",
    "processed_documents",
    "similarity_matches",
    "document_chunks",
    "citations",
    "claims",
    "detection_results",
    "evidence_nodes",
    "integrity_reports",
    "authorship_signals",
    "provenance_events",
    "provenance_reports",
    "aegis_edits",
)


def upgrade() -> None:
    bind = op.get_bind()
    # Freeze the original schema: importing live models here made a fresh
    # database contain later columns/constraints before their revisions ran.
    metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_organization_id() RETURNS TEXT
        LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_organization_id', true), '') $$
    """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS TEXT
        LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_user_id', true), '') $$
    """
    )
    for table in DIRECT_TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        predicate = "organization_id = app.current_organization_id()"
        if table == "audit_logs":
            predicate = "(organization_id = app.current_organization_id() OR (organization_id IS NULL AND app.current_user_id() IS NULL))"
        op.execute(
            f"""CREATE POLICY {table}_tenant_isolation ON "{table}"
            USING ({predicate}) WITH CHECK ({predicate})"""
        )
    for table in DOCUMENT_TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""CREATE POLICY {table}_tenant_isolation ON "{table}"
            USING (EXISTS (SELECT 1 FROM documents WHERE documents.id = "{table}".document_id
                           AND documents.organization_id = app.current_organization_id()))
            WITH CHECK (EXISTS (SELECT 1 FROM documents WHERE documents.id = "{table}".document_id
                                AND documents.organization_id = app.current_organization_id()))"""
        )
    # Detection segments do not carry a document ID; constrain them through
    # their parent result instead of allowing unscoped access.
    op.execute("ALTER TABLE detection_segments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE detection_segments FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY detection_segments_tenant_isolation ON detection_segments
        USING (EXISTS (SELECT 1 FROM detection_results JOIN documents ON documents.id = detection_results.document_id
                       WHERE detection_results.id = detection_segments.detection_result_id
                         AND documents.organization_id = app.current_organization_id()))
        WITH CHECK (EXISTS (SELECT 1 FROM detection_results JOIN documents ON documents.id = detection_results.document_id
                            WHERE detection_results.id = detection_segments.detection_result_id
                              AND documents.organization_id = app.current_organization_id()))"""
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in (
            DIRECT_TENANT_TABLES + DOCUMENT_TENANT_TABLES + ("detection_segments",)
        ):
            op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON "{table}"')
        op.execute("DROP SCHEMA IF EXISTS app CASCADE")
    metadata.drop_all(bind=bind)
