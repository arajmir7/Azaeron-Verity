"""Add canonical evidence graph identity, span text, and endpoint integrity.

Revision ID: 20260912_0019
Revises: 20260912_0018
"""

from alembic import op
import sqlalchemy as sa


revision = "20260912_0019"
down_revision = "20260912_0018"
branch_labels = None
depends_on = None


EDGE_TYPES = (
    "CONTAINS",
    "VERSION_OF",
    "CITES",
    "SUPPORTED_BY",
    "SIMILAR_TO",
    "HAS_SIGNAL",
    "DERIVED_FROM",
    "GENERATED_FINDING",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "evidence_nodes",
        sa.Column("canonical_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "evidence_nodes", sa.Column("entity_id", sa.String(length=180), nullable=True)
    )
    op.add_column(
        "evidence_nodes", sa.Column("entity_type", sa.String(length=60), nullable=True)
    )
    op.add_column("evidence_nodes", sa.Column("span_text", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE evidence_nodes
           SET canonical_type = CASE node_type::text
               WHEN 'DOCUMENT' THEN 'DOCUMENT'
               WHEN 'CLAIM' THEN 'CLAIM'
               WHEN 'CITATION' THEN 'CITATION'
               WHEN 'SOURCE' THEN 'SOURCE'
               WHEN 'SIMILARITY' THEN 'SIMILARITY_MATCH'
               WHEN 'AUTHORSHIP' THEN 'AUTHORSHIP_SIGNAL'
               WHEN 'PROVENANCE' THEN 'PROVENANCE_EVENT'
               WHEN 'DETECTION' THEN 'AI_SIGNAL'
               WHEN 'REVISION' THEN 'DOCUMENT_VERSION'
               ELSE 'FINDING'
           END,
               entity_id = CASE node_type::text
               WHEN 'DOCUMENT' THEN document_id
               ELSE COALESCE(NULLIF(source_id, ''), node_id)
           END,
               entity_type = CASE node_type::text
               WHEN 'DOCUMENT' THEN 'document'
               WHEN 'CLAIM' THEN 'claim'
               WHEN 'CITATION' THEN 'citation'
               WHEN 'SOURCE' THEN 'source'
               WHEN 'SIMILARITY' THEN 'similarity_match'
               WHEN 'AUTHORSHIP' THEN 'authorship_signal'
               WHEN 'PROVENANCE' THEN 'provenance_event'
               WHEN 'DETECTION' THEN 'ai_signal'
               WHEN 'REVISION' THEN 'document_version'
               ELSE 'finding'
           END
    """
    )
    op.alter_column("evidence_nodes", "canonical_type", nullable=False)
    op.alter_column("evidence_nodes", "entity_id", nullable=False)
    op.alter_column("evidence_nodes", "entity_type", nullable=False)
    op.create_index(
        "ix_evidence_nodes_canonical_type", "evidence_nodes", ["canonical_type"]
    )
    op.create_index("ix_evidence_nodes_entity_id", "evidence_nodes", ["entity_id"])
    op.create_check_constraint(
        "ck_evidence_nodes_canonical_type",
        "evidence_nodes",
        "canonical_type IN ('DOCUMENT', 'DOCUMENT_VERSION', 'CLAIM', 'CITATION', 'SOURCE', 'SIMILARITY_MATCH', 'AI_SIGNAL', 'AUTHORSHIP_SIGNAL', 'PROVENANCE_EVENT', 'FINDING', 'REPORT')",
    )
    op.create_check_constraint(
        "ck_evidence_nodes_entity_id_nonempty",
        "evidence_nodes",
        "length(entity_id) > 0",
    )
    op.create_check_constraint(
        "ck_evidence_nodes_node_id_nonempty", "evidence_nodes", "length(node_id) > 0"
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM evidence_nodes GROUP BY node_id HAVING count(*) > 1)
             OR EXISTS (SELECT 1 FROM evidence_nodes WHERE node_id IS NULL OR node_id = '') THEN
            RAISE EXCEPTION 'evidence_nodes contain duplicate or empty graph node ids';
          END IF;
          IF EXISTS (
              SELECT 1 FROM evidence_edges edge
               LEFT JOIN evidence_nodes source_node ON source_node.node_id = edge.source_node_id
               LEFT JOIN evidence_nodes target_node ON target_node.node_id = edge.target_node_id
              WHERE source_node.id IS NULL OR target_node.id IS NULL
          ) THEN
            RAISE EXCEPTION 'evidence_edges contain orphan endpoints';
          END IF;
          IF EXISTS (SELECT 1 FROM evidence_edges WHERE edge_type NOT IN ('CONTAINS', 'VERSION_OF', 'CITES', 'SUPPORTED_BY', 'SIMILAR_TO', 'HAS_SIGNAL', 'DERIVED_FROM', 'GENERATED_FINDING')) THEN
            RAISE EXCEPTION 'evidence_edges contain an unsupported relationship type';
          END IF;
        END $$;
    """
    )
    op.create_unique_constraint(
        "uq_evidence_nodes_node_id", "evidence_nodes", ["node_id"]
    )
    op.create_check_constraint(
        "ck_evidence_edges_type",
        "evidence_edges",
        "edge_type IN ('CONTAINS', 'VERSION_OF', 'CITES', 'SUPPORTED_BY', 'SIMILAR_TO', 'HAS_SIGNAL', 'DERIVED_FROM', 'GENERATED_FINDING')",
    )
    op.create_foreign_key(
        "fk_evidence_edges_source_node",
        "evidence_edges",
        "evidence_nodes",
        ["source_node_id"],
        ["node_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_evidence_edges_target_node",
        "evidence_edges",
        "evidence_nodes",
        ["target_node_id"],
        ["node_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint(
        "fk_evidence_edges_target_node", "evidence_edges", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_evidence_edges_source_node", "evidence_edges", type_="foreignkey"
    )
    op.drop_constraint("ck_evidence_edges_type", "evidence_edges", type_="check")
    op.drop_constraint("uq_evidence_nodes_node_id", "evidence_nodes", type_="unique")
    op.drop_constraint(
        "ck_evidence_nodes_node_id_nonempty", "evidence_nodes", type_="check"
    )
    op.drop_constraint(
        "ck_evidence_nodes_entity_id_nonempty", "evidence_nodes", type_="check"
    )
    op.drop_constraint(
        "ck_evidence_nodes_canonical_type", "evidence_nodes", type_="check"
    )
    op.drop_index("ix_evidence_nodes_entity_id", table_name="evidence_nodes")
    op.drop_index("ix_evidence_nodes_canonical_type", table_name="evidence_nodes")
    for column in ("span_text", "entity_type", "entity_id", "canonical_type"):
        op.drop_column("evidence_nodes", column)
