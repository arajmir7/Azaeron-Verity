"""Harden AZAERON WRITE with tenant/version lineage and edit metadata.

Revision ID: 20260912_0020
Revises: 20260912_0019
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0020"
down_revision = "20260912_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    for value in (
        "WRITING_SUGGESTIONS",
        "WRITING_REFINEMENT",
        "WRITING_EDIT_APPLIED",
        "WRITING_EDIT_REJECTED",
    ):
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column(
        "aegis_edits", sa.Column("organization_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "aegis_edits",
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "aegis_edits", sa.Column("parent_edit_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "aegis_edits", sa.Column("dimension", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "aegis_edits", sa.Column("preserve_voice", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "aegis_edits", sa.Column("engine_version", sa.String(length=80), nullable=True)
    )
    op.add_column(
        "aegis_edits",
        sa.Column("source_text_hash", sa.String(length=64), nullable=True),
    )

    op.execute(
        """
        UPDATE aegis_edits edit
           SET organization_id = document.organization_id,
               document_version_id = latest_version.id,
               dimension = lower(edit.edit_type::text),
               preserve_voice = true,
               engine_version = 'legacy-aegiswrite-v1'
          FROM documents document
          JOIN LATERAL (
              SELECT version.id
                FROM document_versions version
               WHERE version.document_id = document.id
               ORDER BY version.version_number DESC
               LIMIT 1
          ) latest_version ON true
         WHERE edit.document_id = document.id
    """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
              SELECT 1 FROM aegis_edits
               WHERE organization_id IS NULL
                  OR document_version_id IS NULL
                  OR dimension IS NULL
                  OR preserve_voice IS NULL
                  OR engine_version IS NULL
          ) THEN
            RAISE EXCEPTION 'Existing AegisWrite edits could not be assigned immutable tenant/version lineage';
          END IF;
        END $$;
    """
    )
    op.alter_column("aegis_edits", "organization_id", nullable=False)
    op.alter_column("aegis_edits", "document_version_id", nullable=False)
    op.alter_column("aegis_edits", "dimension", nullable=False)
    op.alter_column("aegis_edits", "preserve_voice", nullable=False)
    op.alter_column("aegis_edits", "engine_version", nullable=False)
    op.create_index(
        "ix_aegis_edits_organization_id", "aegis_edits", ["organization_id"]
    )
    op.create_index(
        "ix_aegis_edits_document_version_id", "aegis_edits", ["document_version_id"]
    )
    op.create_index("ix_aegis_edits_parent_edit_id", "aegis_edits", ["parent_edit_id"])
    op.create_foreign_key(
        "fk_aegis_edits_organization",
        "aegis_edits",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_aegis_edits_document_version",
        "aegis_edits",
        "document_versions",
        ["document_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_aegis_edits_parent",
        "aegis_edits",
        "aegis_edits",
        ["parent_edit_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint("fk_aegis_edits_parent", "aegis_edits", type_="foreignkey")
    op.drop_constraint(
        "fk_aegis_edits_document_version", "aegis_edits", type_="foreignkey"
    )
    op.drop_constraint("fk_aegis_edits_organization", "aegis_edits", type_="foreignkey")
    op.drop_index("ix_aegis_edits_parent_edit_id", table_name="aegis_edits")
    op.drop_index("ix_aegis_edits_document_version_id", table_name="aegis_edits")
    op.drop_index("ix_aegis_edits_organization_id", table_name="aegis_edits")
    for column in (
        "source_text_hash",
        "engine_version",
        "preserve_voice",
        "dimension",
        "parent_edit_id",
        "document_version_id",
        "organization_id",
    ):
        op.drop_column("aegis_edits", column)
