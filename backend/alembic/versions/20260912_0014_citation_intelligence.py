"""Add auditable claim/reference/source citation intelligence.

Revision ID: 20260912_0014
Revises: 20260912_0013
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260912_0014"
down_revision = "20260912_0013"
branch_labels = None
depends_on = None


SUPPORT_VALUES = ("SUPPORTED", "PARTIALLY_SUPPORTED", "NOT_SUPPORTED", "UNVERIFIABLE")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    support_enum = postgresql.ENUM(*SUPPORT_VALUES, name="supportstatus")
    support_enum.create(bind, checkfirst=True)
    support_column_enum = postgresql.ENUM(
        *SUPPORT_VALUES, name="supportstatus", create_type=False
    )

    op.create_table(
        "citation_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors", sa.JSON(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("retrieval_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retrieval_status",
            sa.String(length=30),
            nullable=False,
            server_default="NOT_ATTEMPTED",
        ),
        sa.Column("abstract_text", sa.Text(), nullable=True),
        sa.Column("retrieved_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_citation_sources_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_citation_sources_document_version",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_citation_sources_org_key",
        "citation_sources",
        ["organization_id", "source_key"],
    )
    op.create_index("ix_citation_sources_doi", "citation_sources", ["doi"])

    op.create_table(
        "citation_references",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("reference_key", sa.String(length=180), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("journal", sa.Text(), nullable=True),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_citation_references_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_citation_references_document_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_citation_references_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["citation_sources.id"],
            name="fk_citation_references_source",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_citation_references_document_id", "citation_references", ["document_id"]
    )
    op.create_index(
        "ix_citation_references_reference_key", "citation_references", ["reference_key"]
    )

    op.add_column(
        "citations", sa.Column("reference_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "citations", sa.Column("source_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "citations", sa.Column("evidence_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "citations", sa.Column("citation_key", sa.String(length=180), nullable=True)
    )
    op.add_column(
        "citations", sa.Column("support_status", support_column_enum, nullable=True)
    )
    op.add_column(
        "citations",
        sa.Column("retrieval_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE citations SET support_status = 'UNVERIFIABLE' WHERE support_status IS NULL"
    )
    op.alter_column("citations", "support_status", nullable=False)
    op.create_foreign_key(
        "fk_citations_reference",
        "citations",
        "citation_references",
        ["reference_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_citations_source",
        "citations",
        "citation_sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_citations_evidence",
        "citations",
        "evidence_nodes",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_citations_reference_id", "citations", ["reference_id"])
    op.create_index("ix_citations_source_id", "citations", ["source_id"])
    op.create_index("ix_citations_evidence_id", "citations", ["evidence_id"])

    op.add_column(
        "claims", sa.Column("support_status", support_column_enum, nullable=True)
    )
    op.add_column(
        "claims", sa.Column("evidence_id", sa.String(length=36), nullable=True)
    )
    op.execute(
        "UPDATE claims SET support_status = 'UNVERIFIABLE' WHERE support_status IS NULL"
    )
    op.alter_column("claims", "support_status", nullable=False)
    op.create_foreign_key(
        "fk_claims_evidence",
        "claims",
        "evidence_nodes",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_claims_evidence_id", "claims", ["evidence_id"])

    op.create_table(
        "citation_findings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_version", sa.String(length=80), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=36), nullable=True),
        sa.Column("citation_id", sa.String(length=36), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
        sa.Column("finding_type", sa.String(length=60), nullable=False),
        sa.Column("support_status", support_column_enum, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_citation_findings_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_citation_findings_document_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_citation_findings_document",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            name="fk_citation_findings_claim",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["citation_id"],
            ["citations.id"],
            name="fk_citation_findings_citation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reference_id"],
            ["citation_references.id"],
            name="fk_citation_findings_reference",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["citation_sources.id"],
            name="fk_citation_findings_source",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence_nodes.id"],
            name="fk_citation_findings_evidence",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_citation_findings_confidence",
        ),
    )
    for column in (
        "document_id",
        "claim_id",
        "citation_id",
        "reference_id",
        "source_id",
        "evidence_id",
        "finding_type",
    ):
        op.create_index(f"ix_citation_findings_{column}", "citation_findings", [column])

    for table in ("citation_sources", "citation_references", "citation_findings"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_tenant_isolation ON {table}
            USING (organization_id = app.current_organization_id())
            WITH CHECK (organization_id = app.current_organization_id())"""
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in ("citation_sources", "citation_references", "citation_findings"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    for column in (
        "finding_type",
        "evidence_id",
        "source_id",
        "reference_id",
        "citation_id",
        "claim_id",
        "document_id",
    ):
        op.drop_index(f"ix_citation_findings_{column}", table_name="citation_findings")
    op.drop_table("citation_findings")
    op.drop_constraint("fk_claims_evidence", "claims", type_="foreignkey")
    op.drop_index("ix_claims_evidence_id", table_name="claims")
    op.drop_column("claims", "evidence_id")
    op.drop_column("claims", "support_status")
    for name in (
        "ix_citations_evidence_id",
        "ix_citations_source_id",
        "ix_citations_reference_id",
    ):
        op.drop_index(name, table_name="citations")
    for name, column in (
        ("fk_citations_evidence", "evidence_id"),
        ("fk_citations_source", "source_id"),
        ("fk_citations_reference", "reference_id"),
    ):
        op.drop_constraint(name, "citations", type_="foreignkey")
        op.drop_column("citations", column)
    op.drop_column("citations", "retrieval_timestamp")
    op.drop_column("citations", "support_status")
    op.drop_column("citations", "citation_key")
    op.drop_table("citation_references")
    op.drop_table("citation_sources")
    sa.Enum(*SUPPORT_VALUES, name="supportstatus").drop(bind, checkfirst=True)
