"""Close tenant-policy gaps and add database integrity guards.

Revision ID: 20260910_0003
Revises: 20260826_0002
Create Date: 2026-09-10

This revision is additive. It intentionally does not alter historical
migrations: an already-applied migration is part of a deployment's audit trail.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260910_0003"
down_revision = "20260826_0002"
branch_labels = None
depends_on = None


def _add_constraint(name: str, table: str, condition: str) -> None:
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # These constraints make invalid states impossible regardless of the API
    # path used to create a record.
    _add_constraint("ck_documents_file_size_positive", "documents", "file_size > 0")
    _add_constraint(
        "ck_documents_sha256_length", "documents", "length(sha256_fingerprint) = 64"
    )
    op.create_unique_constraint(
        "uq_documents_storage_path", "documents", ["storage_path"]
    )
    _add_constraint(
        "ck_document_versions_number_positive",
        "document_versions",
        "version_number > 0",
    )
    op.create_unique_constraint(
        "uq_document_versions_document_number",
        "document_versions",
        ["document_id", "version_number"],
    )
    _add_constraint(
        "ck_jobs_progress_range",
        "jobs",
        "progress_percent >= 0 AND progress_percent <= 100",
    )
    _add_constraint("ck_jobs_retry_count_nonnegative", "jobs", "retry_count >= 0")
    _add_constraint("ck_jobs_max_retries_nonnegative", "jobs", "max_retries >= 0")
    _add_constraint(
        "ck_document_chunks_index_nonnegative", "document_chunks", "chunk_index >= 0"
    )
    _add_constraint(
        "ck_document_chunks_span",
        "document_chunks",
        "start_char >= 0 AND end_char >= start_char",
    )
    op.create_unique_constraint(
        "uq_document_chunks_document_index",
        "document_chunks",
        ["document_id", "chunk_index"],
    )
    _add_constraint(
        "ck_similarity_matches_document_span",
        "similarity_matches",
        "document_span_start >= 0 AND document_span_end >= document_span_start",
    )
    _add_constraint(
        "ck_similarity_matches_score_range",
        "similarity_matches",
        "similarity_score >= 0 AND similarity_score <= 1",
    )
    _add_constraint(
        "ck_similarity_matches_confidence_range",
        "similarity_matches",
        "confidence >= 0 AND confidence <= 1",
    )
    _add_constraint(
        "ck_detection_results_confidence_range",
        "detection_results",
        "confidence >= 0 AND confidence <= 1",
    )
    _add_constraint(
        "ck_detection_results_human_probability_range",
        "detection_results",
        "human_probability >= 0 AND human_probability <= 1",
    )
    _add_constraint(
        "ck_detection_results_ai_probability_range",
        "detection_results",
        "ai_probability >= 0 AND ai_probability <= 1",
    )
    _add_constraint(
        "ck_detection_results_mixed_probability_range",
        "detection_results",
        "mixed_probability >= 0 AND mixed_probability <= 1",
    )
    _add_constraint(
        "ck_detection_results_uncertain_probability_range",
        "detection_results",
        "uncertain_probability >= 0 AND uncertain_probability <= 1",
    )
    op.create_unique_constraint(
        "uq_detection_results_document_job",
        "detection_results",
        ["document_id", "job_id"],
    )
    _add_constraint(
        "ck_detection_segments_span",
        "detection_segments",
        "span_start >= 0 AND span_end >= span_start",
    )
    _add_constraint(
        "ck_detection_segments_confidence_range",
        "detection_segments",
        "confidence >= 0 AND confidence <= 1",
    )
    op.create_unique_constraint(
        "uq_detection_segments_result_segment",
        "detection_segments",
        ["detection_result_id", "segment_type", "segment_index"],
    )
    _add_constraint(
        "ck_evidence_nodes_confidence_range",
        "evidence_nodes",
        "confidence >= 0 AND confidence <= 1",
    )
    _add_constraint(
        "ck_evidence_nodes_span",
        "evidence_nodes",
        "span_start IS NULL OR (span_start >= 0 AND span_end >= span_start)",
    )

    # Evidence edges previously had no tenant key, which made it impossible to
    # enforce an independent database policy. Refuse to migrate ambiguous or
    # cross-organization historical edges instead of silently assigning them.
    op.add_column(
        "evidence_edges",
        sa.Column("organization_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        """
        UPDATE evidence_edges AS edge
           SET organization_id = document.organization_id
          FROM evidence_nodes AS source_node
          JOIN documents AS document ON document.id = source_node.document_id
         WHERE edge.source_node_id = source_node.node_id
    """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
              SELECT 1
                FROM evidence_edges AS edge
                LEFT JOIN evidence_nodes AS source_node ON source_node.node_id = edge.source_node_id
                LEFT JOIN evidence_nodes AS target_node ON target_node.node_id = edge.target_node_id
                LEFT JOIN documents AS source_document ON source_document.id = source_node.document_id
                LEFT JOIN documents AS target_document ON target_document.id = target_node.document_id
               WHERE edge.organization_id IS NULL
                  OR source_document.organization_id IS DISTINCT FROM target_document.organization_id
          ) THEN
            RAISE EXCEPTION 'evidence_edges contain unresolved or cross-organization references; remediate before migration';
          END IF;
        END $$;
    """
    )
    op.alter_column("evidence_edges", "organization_id", nullable=False)
    op.create_foreign_key(
        "fk_evidence_edges_organization",
        "evidence_edges",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_evidence_edges_organization_id", "evidence_edges", ["organization_id"]
    )

    # A submission is tenant-owned through its assignment. It must be subject
    # to the same RLS boundary as direct tenant tables.
    op.execute("ALTER TABLE submissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE submissions FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS submissions_tenant_isolation ON submissions")
    op.execute(
        """
        CREATE POLICY submissions_tenant_isolation ON submissions
        USING (
            EXISTS (
                SELECT 1 FROM assignments
                 WHERE assignments.id = submissions.assignment_id
                   AND assignments.organization_id = app.current_organization_id()
            )
        )
        WITH CHECK (
            EXISTS (
                SELECT 1 FROM assignments
                 WHERE assignments.id = submissions.assignment_id
                   AND assignments.organization_id = app.current_organization_id()
            )
        )
    """
    )

    op.execute("ALTER TABLE evidence_edges ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE evidence_edges FORCE ROW LEVEL SECURITY")
    op.execute(
        "DROP POLICY IF EXISTS evidence_edges_tenant_isolation ON evidence_edges"
    )
    op.execute(
        """
        CREATE POLICY evidence_edges_tenant_isolation ON evidence_edges
        USING (organization_id = app.current_organization_id())
        WITH CHECK (organization_id = app.current_organization_id())
    """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        "DROP POLICY IF EXISTS evidence_edges_tenant_isolation ON evidence_edges"
    )
    op.execute("DROP POLICY IF EXISTS submissions_tenant_isolation ON submissions")
    op.drop_index("ix_evidence_edges_organization_id", table_name="evidence_edges")
    op.drop_constraint(
        "fk_evidence_edges_organization", "evidence_edges", type_="foreignkey"
    )
    op.drop_column("evidence_edges", "organization_id")
    for name, table, kind in (
        ("ck_documents_file_size_positive", "documents", "check"),
        ("ck_documents_sha256_length", "documents", "check"),
        ("uq_documents_storage_path", "documents", "unique"),
        ("ck_document_versions_number_positive", "document_versions", "check"),
        ("uq_document_versions_document_number", "document_versions", "unique"),
        ("ck_jobs_progress_range", "jobs", "check"),
        ("ck_jobs_retry_count_nonnegative", "jobs", "check"),
        ("ck_jobs_max_retries_nonnegative", "jobs", "check"),
        ("ck_document_chunks_index_nonnegative", "document_chunks", "check"),
        ("ck_document_chunks_span", "document_chunks", "check"),
        ("uq_document_chunks_document_index", "document_chunks", "unique"),
        ("ck_similarity_matches_document_span", "similarity_matches", "check"),
        ("ck_similarity_matches_score_range", "similarity_matches", "check"),
        ("ck_similarity_matches_confidence_range", "similarity_matches", "check"),
        ("ck_detection_results_confidence_range", "detection_results", "check"),
        ("ck_detection_results_human_probability_range", "detection_results", "check"),
        ("ck_detection_results_ai_probability_range", "detection_results", "check"),
        ("ck_detection_results_mixed_probability_range", "detection_results", "check"),
        (
            "ck_detection_results_uncertain_probability_range",
            "detection_results",
            "check",
        ),
        ("uq_detection_results_document_job", "detection_results", "unique"),
        ("ck_detection_segments_span", "detection_segments", "check"),
        ("ck_detection_segments_confidence_range", "detection_segments", "check"),
        ("uq_detection_segments_result_segment", "detection_segments", "unique"),
        ("ck_evidence_nodes_confidence_range", "evidence_nodes", "check"),
        ("ck_evidence_nodes_span", "evidence_nodes", "check"),
    ):
        op.drop_constraint(name, table, type_=kind)
