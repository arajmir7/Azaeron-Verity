"""Reference-aware retention and verified legacy-object relocation."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0031"
down_revision = "20260921_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "storage_relocations",
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("old_key", sa.String(500), nullable=False),
        sa.Column("new_key", sa.String(500), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "migrated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.execute("REVOKE ALL ON storage_relocations FROM PUBLIC, azaeron_app")
    op.execute("GRANT SELECT ON storage_relocations TO azaeron_app")
    op.execute("ALTER TABLE storage_relocations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE storage_relocations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY relocation_tenant ON storage_relocations USING (organization_id=app.current_organization_id())"
    )
    op.execute(
        """CREATE FUNCTION app.storage_referenced(p_key text) RETURNS boolean
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
      SELECT EXISTS(SELECT 1 FROM document_versions WHERE storage_path=p_key)
        OR EXISTS(SELECT 1 FROM documents WHERE storage_path=p_key)
    $$"""
    )
    op.execute(
        """CREATE FUNCTION app.storage_legacy_candidates() RETURNS TABLE(version_id text,document_id text,organization_id text)
      LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
      SELECT v.id::text,d.id::text,d.organization_id::text FROM document_versions v JOIN documents d ON d.id=v.document_id
      WHERE v.storage_path LIKE 'uploads/%' AND NOT d.erasure_pending ORDER BY v.id LIMIT 100
    $$"""
    )
    op.execute(
        """CREATE FUNCTION app.storage_relocate(p_version text,p_old text,p_new text,p_hash text) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
    DECLARE v document_versions%ROWTYPE; d documents%ROWTYPE; expected text;
    BEGIN
      SELECT documents.* INTO d FROM documents JOIN document_versions ON document_versions.document_id=documents.id
        WHERE document_versions.id=p_version AND documents.organization_id=app.current_organization_id() FOR UPDATE OF documents;
      IF NOT FOUND OR d.erasure_pending THEN RAISE EXCEPTION 'legacy target unavailable'; END IF;
      SELECT * INTO v FROM document_versions WHERE id=p_version FOR UPDATE;
      IF v.storage_path=p_new AND EXISTS(SELECT 1 FROM storage_relocations WHERE version_id=p_version AND new_key=p_new AND content_hash=p_hash) THEN RETURN false; END IF;
      expected := 'versions/legacy/'||d.organization_id||'/'||d.id||'/'||v.id||'/'||v.content_hash||'.'||lower(substring(p_old from '[.]([^.]+)$'));
      IF p_old NOT LIKE 'uploads/%' OR v.storage_path IS DISTINCT FROM p_old OR v.content_hash IS DISTINCT FROM p_hash
        OR p_new IS DISTINCT FROM expected THEN RAISE EXCEPTION 'legacy relocation identity mismatch'; END IF;
      PERFORM set_config('app.privacy_request','storage-relocation',true);
      INSERT INTO storage_relocations(version_id,organization_id,old_key,new_key,content_hash) VALUES(p_version,d.organization_id,p_old,p_new,p_hash);
      UPDATE document_versions SET storage_path=p_new WHERE id=p_version;
      UPDATE documents SET storage_path=p_new WHERE id=d.id AND storage_path=p_old;
      UPDATE jobs SET input_data=jsonb_set(input_data::jsonb,'{storage_key}',to_jsonb(p_new))::json
        WHERE document_version_id=p_version AND input_data->>'storage_key'=p_old;
      PERFORM set_config('app.privacy_request','',true);
      RETURN true;
    END $$"""
    )
    for signature in (
        "storage_referenced(text)",
        "storage_legacy_candidates()",
        "storage_relocate(text,text,text,text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION app.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{signature} TO azaeron_app")
    # Include legacy paths in erasure even after the version reference moves.
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_request(text,text,text,text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        "UNION SELECT storage_path FROM documents WHERE id=ANY(docs)) k;",
        "UNION SELECT storage_path FROM documents WHERE id=ANY(docs) UNION SELECT old_key FROM storage_relocations WHERE version_id IN (SELECT id FROM document_versions WHERE document_id=ANY(docs))) k;",
    )
    definition = definition.replace(
        "'versions/'||d.organization_id||'/'||d.id||'/'",
        "'versions/'||d.organization_id||'/'||d.id||'/', 'versions/legacy/'||d.organization_id||'/'||d.id||'/'",
    )
    definition = definition.replace(
        "'versions/uploads/'||found_id||'/'",
        "'versions/uploads/'||found_id||'/', 'versions/legacy/'||found_id||'/'",
    )
    op.execute(sa.text(definition))
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        "UNION SELECT document_id FROM provenance_exports WHERE",
        "UNION SELECT document_id FROM provenance_reports WHERE r.scope='account' AND signed_by_id=r.target_id UNION SELECT document_id FROM provenance_exports WHERE",
    )
    op.execute(sa.text(definition))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM storage_relocations")):
        raise RuntimeError(
            "Legacy objects have moved; use a compatible application rollback"
        )
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_request(text,text,text,text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        " UNION SELECT old_key FROM storage_relocations WHERE version_id IN (SELECT id FROM document_versions WHERE document_id=ANY(docs))",
        "",
    )
    op.execute(sa.text(definition))
    for signature in (
        "storage_relocate(text,text,text,text)",
        "storage_legacy_candidates()",
        "storage_referenced(text)",
    ):
        op.execute(f"DROP FUNCTION app.{signature}")
    op.drop_table("storage_relocations")
