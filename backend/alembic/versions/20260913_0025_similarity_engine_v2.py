"""Hybrid retrieval, structured chunk indexes and sealed run snapshots.

Revision ID: 20260913_0025
Revises: 20260913_0024
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "20260913_0025"
down_revision = "20260913_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.drop_constraint(
        "uq_document_chunks_version_index", "document_chunks", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_chunks_version_index",
        "document_chunks",
        ["document_id", "document_version_id", "index_version", "chunk_index"],
    )
    op.add_column(
        "document_chunks", sa.Column("structure_json", sa.JSON(), nullable=True)
    )
    op.add_column(
        "document_chunks", sa.Column("embedding_vector", Vector(384), nullable=True)
    )
    op.add_column(
        "document_chunks", sa.Column("embedding_model", sa.String(180), nullable=True)
    )
    op.execute(
        "CREATE INDEX ix_similarity_chunks_vector ON document_chunks USING hnsw (embedding_vector vector_cosine_ops) WHERE embedding_vector IS NOT NULL"
    )
    op.create_index(
        "ix_similarity_chunk_scope",
        "document_chunks",
        ["organization_id", "index_version", "index_status"],
    )
    op.drop_constraint(
        "ck_similarity_index_term_type", "similarity_index_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_similarity_index_term_type",
        "similarity_index_entries",
        "term_type IN ('token','ngram','fingerprint')",
    )
    op.add_column(
        "similarity_matches", sa.Column("group_id", sa.String(36), nullable=True)
    )
    op.create_index(
        "ix_similarity_matches_group_id", "similarity_matches", ["group_id"]
    )
    op.add_column(
        "similarity_analyses",
        sa.Column("analysis_run_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_similarity_snapshot_run",
        "similarity_analyses",
        "analysis_runs",
        ["analysis_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_similarity_analyses_analysis_run_id",
        "similarity_analyses",
        ["analysis_run_id"],
    )
    op.add_column(
        "similarity_analyses",
        sa.Column("run_key", sa.String(80), nullable=False, server_default="default"),
    )
    op.add_column(
        "similarity_analyses",
        sa.Column("snapshot_fingerprint", sa.String(64), nullable=True),
    )
    op.add_column(
        "similarity_analyses",
        sa.Column("sealed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint(
        "uq_similarity_analysis_version_pipeline", "similarity_analyses", type_="unique"
    )
    op.create_unique_constraint(
        "uq_similarity_analysis_version_pipeline",
        "similarity_analyses",
        ["document_version_id", "pipeline_version", "run_key"],
    )
    op.execute("UPDATE similarity_analyses SET sealed=true")
    op.execute(
        "CREATE TRIGGER similarity_snapshot_run_target BEFORE INSERT OR UPDATE ON similarity_analyses FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('analysis_run_id','analysis_runs')"
    )
    op.execute(
        "CREATE TRIGGER similarity_index_chunk_target BEFORE INSERT OR UPDATE ON similarity_index_entries FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target('chunk_id','document_chunks')"
    )
    op.execute(
        """CREATE FUNCTION app.freeze_similarity_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.sealed THEN
        IF TG_OP='DELETE' OR to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
          RAISE EXCEPTION 'completed similarity snapshots are immutable';
        END IF;
      END IF;
      RETURN OLD;
    END $$"""
    )
    # Return NEW for permitted updates; DELETE must return OLD.
    op.execute(
        """CREATE OR REPLACE FUNCTION app.freeze_similarity_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.sealed AND (TG_OP='DELETE' OR to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW)) THEN
        RAISE EXCEPTION 'completed similarity snapshots are immutable';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER similarity_snapshots_frozen BEFORE UPDATE OR DELETE ON similarity_analyses FOR EACH ROW EXECUTE FUNCTION app.freeze_similarity_snapshot()"
    )
    op.execute(
        """CREATE FUNCTION app.validate_similarity_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snapshot_id text; target_text text; source_text text;
    BEGIN
      IF TG_OP='DELETE' THEN snapshot_id=OLD.analysis_id; ELSE snapshot_id=NEW.analysis_id; END IF;
      IF EXISTS (SELECT 1 FROM similarity_analyses WHERE id=snapshot_id AND sealed) THEN
        IF TG_OP<>'UPDATE' OR to_jsonb(OLD) IS DISTINCT FROM to_jsonb(NEW) THEN
          RAISE EXCEPTION 'completed similarity evidence is immutable';
        END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      IF NEW.pipeline_version='similarity-engine-v2' THEN
        SELECT p.cleaned_text INTO target_text FROM processed_documents p WHERE p.document_version_id=NEW.document_version_id AND p.organization_id=NEW.organization_id;
        SELECT p.cleaned_text INTO source_text FROM processed_documents p JOIN document_versions v ON v.id=p.document_version_id
          WHERE v.id=NEW.source_document_version_id AND v.document_id=NEW.source_document_id AND p.organization_id=NEW.organization_id;
        IF target_text IS NULL OR source_text IS NULL OR NEW.target_document_id IS DISTINCT FROM NEW.document_id
          OR NEW.analysis_id IS NULL OR NEW.group_id IS NULL
          OR NEW.document_span_end>length(target_text) OR NEW.source_span_start<0 OR NEW.source_span_end>length(source_text)
          OR NEW.matched_text IS DISTINCT FROM substring(target_text FROM NEW.document_span_start+1 FOR NEW.document_span_end-NEW.document_span_start)
          OR NEW.source_text IS DISTINCT FROM substring(source_text FROM NEW.source_span_start+1 FOR NEW.source_span_end-NEW.source_span_start) THEN
          RAISE EXCEPTION 'similarity evidence must resolve to exact tenant/version source and target spans';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER similarity_exact_evidence BEFORE INSERT OR UPDATE OR DELETE ON similarity_matches FOR EACH ROW EXECUTE FUNCTION app.validate_similarity_evidence()"
    )


def downgrade():
    op.execute(
        """DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM document_chunks GROUP BY document_id,document_version_id,chunk_index HAVING count(*)>1)
        OR EXISTS (SELECT 1 FROM similarity_analyses GROUP BY document_version_id,pipeline_version HAVING count(*)>1) THEN
        RAISE EXCEPTION 'Cannot downgrade multiple retained indexes/runs without discarding immutable history';
      END IF;
    END $$"""
    )
    op.execute("DROP TRIGGER similarity_exact_evidence ON similarity_matches")
    op.execute("DROP FUNCTION app.validate_similarity_evidence()")
    op.execute("DROP TRIGGER similarity_snapshots_frozen ON similarity_analyses")
    op.execute("DROP FUNCTION app.freeze_similarity_snapshot()")
    op.execute("DROP TRIGGER similarity_snapshot_run_target ON similarity_analyses")
    op.execute("DROP TRIGGER similarity_index_chunk_target ON similarity_index_entries")
    op.drop_constraint(
        "uq_similarity_analysis_version_pipeline", "similarity_analyses", type_="unique"
    )
    op.create_unique_constraint(
        "uq_similarity_analysis_version_pipeline",
        "similarity_analyses",
        ["document_version_id", "pipeline_version"],
    )
    for column in ("analysis_run_id", "run_key", "snapshot_fingerprint", "sealed"):
        op.drop_column("similarity_analyses", column)
    op.drop_column("similarity_matches", "group_id")
    op.drop_index("ix_similarity_chunks_vector", table_name="document_chunks")
    op.drop_index("ix_similarity_chunk_scope", table_name="document_chunks")
    for column in ("structure_json", "embedding_vector", "embedding_model"):
        op.drop_column("document_chunks", column)
    op.drop_constraint(
        "uq_document_chunks_version_index", "document_chunks", type_="unique"
    )
    op.create_unique_constraint(
        "uq_document_chunks_version_index",
        "document_chunks",
        ["document_id", "document_version_id", "chunk_index"],
    )
    # Fingerprints cannot be converted into lexical terms. Refuse data loss.
    op.drop_constraint(
        "ck_similarity_index_term_type", "similarity_index_entries", type_="check"
    )
    op.create_check_constraint(
        "ck_similarity_index_term_type",
        "similarity_index_entries",
        "term_type IN ('token','ngram')",
    )
