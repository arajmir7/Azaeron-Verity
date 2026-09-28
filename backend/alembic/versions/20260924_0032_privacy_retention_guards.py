"""Bounded retention progress and required attribution on newly created content."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0032"
down_revision = "20260924_0031"
branch_labels = None
depends_on = None


def upgrade():
    # Erase a user's suggestions and derived reports instead of retaining
    # unattributed editable suggestions in shared documents.
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        "UNION SELECT document_id FROM provenance_events WHERE",
        "UNION SELECT document_id FROM aegis_edits WHERE r.scope='account' AND user_id=r.target_id UNION SELECT document_id FROM provenance_events WHERE",
    )
    definition = definition.replace(
        "UPDATE aegis_edits SET user_id=NULL WHERE user_id=r.target_id;",
        "DELETE FROM aegis_edits WHERE user_id=r.target_id;",
    )
    op.execute(sa.text(definition))
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM aegis_edits WHERE user_id IS NULL")
    ):
        raise RuntimeError(
            "Unattributed suggestions require an explicit privacy disposition"
        )
    op.alter_column("aegis_edits", "user_id", nullable=False)
    op.execute(
        """CREATE FUNCTION app.privacy_actor_guard() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public,app AS $$
    BEGIN
      IF app.privacy_internal() THEN RETURN NEW; END IF;
      IF to_jsonb(NEW)->>TG_ARGV[0] IS NULL AND (TG_OP='INSERT' OR to_jsonb(OLD)->>TG_ARGV[0] IS NOT NULL) THEN
        RAISE EXCEPTION 'new attribution is required; redaction requires authorized erasure';
      END IF;
      RETURN NEW;
    END $$"""
    )
    for table, column in (
        ("document_versions", "created_by_id"),
        ("assignments", "created_by_id"),
        ("compliance_reports", "generated_by_id"),
    ):
        op.execute(
            f"CREATE TRIGGER privacy_actor_guard BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.privacy_actor_guard('{column}')"
        )
    op.create_table(
        "storage_gc_progress",
        sa.Column("prefix", sa.String(30), primary_key=True),
        sa.Column("cursor", sa.String(500), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute("REVOKE ALL ON storage_gc_progress FROM PUBLIC, azaeron_app")
    op.execute(
        """CREATE FUNCTION app.storage_gc_cursor(p_prefix text,p_cursor text DEFAULT NULL) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
    DECLARE value text;
    BEGIN
      IF p_prefix NOT IN ('uploads/','versions/','temporary/') THEN RAISE EXCEPTION 'invalid retention prefix'; END IF;
      IF p_cursor IS NOT NULL THEN
        IF p_cursor<>'' AND p_cursor NOT LIKE p_prefix||'%' THEN RAISE EXCEPTION 'invalid retention cursor'; END IF;
        INSERT INTO storage_gc_progress(prefix,cursor) VALUES(p_prefix,p_cursor)
          ON CONFLICT(prefix) DO UPDATE SET cursor=excluded.cursor,updated_at=clock_timestamp();
      END IF;
      SELECT cursor INTO value FROM storage_gc_progress WHERE prefix=p_prefix;
      RETURN coalesce(value,'');
    END $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION app.storage_gc_cursor(text,text) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app.storage_gc_cursor(text,text) TO azaeron_app"
    )


def downgrade():
    op.execute("DROP FUNCTION app.storage_gc_cursor(text,text)")
    op.drop_table("storage_gc_progress")
    for table in ("document_versions", "assignments", "compliance_reports"):
        op.execute(f"DROP TRIGGER privacy_actor_guard ON {table}")
    op.execute("DROP FUNCTION app.privacy_actor_guard()")
    # Keep stronger attribution and broader derivative erasure on application rollback.
