"""Add the incremental originality retrieval index and match evidence contract.

Revision ID: 20260912_0013
Revises: 20260912_0012
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0013"
down_revision = "20260912_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # PostgreSQL enum labels are append-only. PARAPHRASE is retained for
    # historical rows; PROBABLE_PARAPHRASE is not emitted by this pipeline.
    op.execute(
        "ALTER TYPE similaritytype ADD VALUE IF NOT EXISTS 'LEXICAL' AFTER 'NEAR_DUPLICATE'"
    )
    op.execute(
        "ALTER TYPE similaritytype ADD VALUE IF NOT EXISTS 'PROBABLE_PARAPHRASE' AFTER 'STRUCTURAL'"
    )

    op.add_column(
        "similarity_matches",
        sa.Column("target_document_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "similarity_matches",
        sa.Column("evidence_id", sa.String(length=36), nullable=True),
    )
    for name in (
        "retrieval_score",
        "lexical_score",
        "ngram_score",
        "structural_score",
        "verification_score",
    ):
        op.add_column("similarity_matches", sa.Column(name, sa.Float(), nullable=True))
    op.add_column(
        "similarity_matches",
        sa.Column("confidence_reliability", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "similarity_matches", sa.Column("candidate_rank", sa.Integer(), nullable=True)
    )
    op.add_column(
        "similarity_matches", sa.Column("retrieval_methods", sa.JSON(), nullable=True)
    )
    op.add_column(
        "similarity_matches",
        sa.Column("verification_methods", sa.JSON(), nullable=True),
    )
    op.execute(
        "UPDATE similarity_matches SET target_document_id = document_id WHERE target_document_id IS NULL"
    )
    op.execute(
        "UPDATE similarity_matches SET confidence_reliability = 'EXPERIMENTAL' WHERE confidence_reliability IS NULL"
    )
    op.alter_column("similarity_matches", "target_document_id", nullable=False)
    op.alter_column("similarity_matches", "confidence_reliability", nullable=False)
    op.create_foreign_key(
        "fk_similarity_matches_target_document",
        "similarity_matches",
        "documents",
        ["target_document_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_similarity_matches_evidence",
        "similarity_matches",
        "evidence_nodes",
        ["evidence_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_similarity_matches_target_document_id",
        "similarity_matches",
        ["target_document_id"],
    )
    op.create_index(
        "ix_similarity_matches_evidence_id", "similarity_matches", ["evidence_id"]
    )

    op.add_column(
        "document_chunks", sa.Column("normalized_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "document_chunks",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("index_version", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("index_status", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE document_chunks SET normalized_text = trim(lower(regexp_replace(text, '\\s+', ' ', 'g'))) WHERE normalized_text IS NULL"
    )
    op.execute(
        "UPDATE document_chunks SET content_hash = encode(digest(text, 'sha256'), 'hex') WHERE content_hash IS NULL"
    )
    op.execute(
        "UPDATE document_chunks SET index_version = 'inverted-terms-v1' WHERE index_version IS NULL"
    )
    op.execute(
        "UPDATE document_chunks SET index_status = 'STALE' WHERE index_status IS NULL"
    )
    op.alter_column("document_chunks", "index_version", nullable=False)
    op.alter_column("document_chunks", "index_status", nullable=False)
    op.create_index(
        "ix_document_chunks_content_hash", "document_chunks", ["content_hash"]
    )
    op.drop_constraint(
        "uq_document_chunks_document_index", "document_chunks", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_chunks_version_index",
        "document_chunks",
        ["document_id", "document_version_id", "chunk_index"],
    )

    op.create_table(
        "similarity_index_entries",
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
        sa.Column("chunk_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("term", sa.String(length=300), nullable=False),
        sa.Column("term_type", sa.String(length=20), nullable=False),
        sa.Column("term_frequency", sa.Float(), nullable=False, server_default="1"),
        sa.Column("positions", sa.JSON(), nullable=True),
        sa.Column("index_version", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_similarity_index_organization",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_similarity_index_document_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            name="fk_similarity_index_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_similarity_index_document",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "chunk_id",
            "index_version",
            "term_type",
            "term",
            name="uq_similarity_index_chunk_term",
        ),
        sa.CheckConstraint(
            "term_type IN ('token', 'ngram')", name="ck_similarity_index_term_type"
        ),
        sa.CheckConstraint(
            "term_frequency > 0", name="ck_similarity_index_term_frequency"
        ),
    )
    op.create_index(
        "ix_similarity_index_org_version_term",
        "similarity_index_entries",
        ["organization_id", "index_version", "term"],
    )
    op.create_index(
        "ix_similarity_index_chunk_id", "similarity_index_entries", ["chunk_id"]
    )
    op.create_index(
        "ix_similarity_index_document_id", "similarity_index_entries", ["document_id"]
    )

    op.execute("ALTER TABLE similarity_index_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE similarity_index_entries FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY similarity_index_entries_tenant_isolation ON similarity_index_entries
        USING (organization_id = app.current_organization_id())
        WITH CHECK (organization_id = app.current_organization_id())"""
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DROP POLICY IF EXISTS similarity_index_entries_tenant_isolation ON similarity_index_entries"
    )
    op.drop_index(
        "ix_similarity_index_document_id", table_name="similarity_index_entries"
    )
    op.drop_index("ix_similarity_index_chunk_id", table_name="similarity_index_entries")
    op.drop_index(
        "ix_similarity_index_org_version_term", table_name="similarity_index_entries"
    )
    op.drop_table("similarity_index_entries")
    op.drop_constraint(
        "uq_document_chunks_version_index", "document_chunks", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    for column in (
        "indexed_at",
        "index_status",
        "index_version",
        "content_hash",
        "normalized_text",
    ):
        op.drop_column("document_chunks", column)
    op.drop_index("ix_similarity_matches_evidence_id", table_name="similarity_matches")
    op.drop_index(
        "ix_similarity_matches_target_document_id", table_name="similarity_matches"
    )
    op.drop_constraint(
        "fk_similarity_matches_evidence", "similarity_matches", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_similarity_matches_target_document",
        "similarity_matches",
        type_="foreignkey",
    )
    for column in (
        "verification_methods",
        "retrieval_methods",
        "candidate_rank",
        "confidence_reliability",
        "verification_score",
        "structural_score",
        "ngram_score",
        "lexical_score",
        "retrieval_score",
        "evidence_id",
        "target_document_id",
    ):
        op.drop_column("similarity_matches", column)
