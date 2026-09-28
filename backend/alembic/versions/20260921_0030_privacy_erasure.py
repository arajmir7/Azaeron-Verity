"""Authorized erasure, write fencing, durable tombstones and actor redaction.

The runtime cannot write the erasure ledger or bypass immutable triggers.
Only fixed, security-definer routines can enter the privacy mutation context.
"""

import re

from alembic import op
import sqlalchemy as sa

revision = "20260921_0030"
down_revision = "20260920_0029"
branch_labels = None
depends_on = None

IMMUTABLE_FUNCTIONS = (
    "prevent_document_version_mutation",
    "prevent_provenance_events_mutation",
    "prevent_provenance_exports_mutation",
    "prevent_provenance_reports_mutation",
    "freeze_processed_document",
    "freeze_similarity_snapshot",
    "validate_similarity_evidence",
)
PRIVACY_BRANCH = """
      IF app.privacy_internal() THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
      END IF;
"""
# Fixed dependency order: child/immutable evidence before its parent target.
ARTIFACT_TABLES = (
    "provenance_exports",
    "provenance_reports",
    "provenance_events",
    "integrity_reports",
    "evidence_edges",
    "detection_segments",
    "similarity_matches",
    "citation_findings",
    "citations",
    "claims",
    "citation_references",
    "citation_sources",
    "aegis_edits",
    "detection_results",
    "authorship_signals",
    "similarity_analyses",
    "analysis_runs",
    "jobs",
    "similarity_index_entries",
    "document_chunks",
    "processed_documents",
    "evidence_nodes",
)
ACTOR_COLUMNS = (
    ("document_versions", "created_by_id"),
    ("assignments", "created_by_id"),
    ("compliance_reports", "generated_by_id"),
    ("aegis_edits", "user_id"),
)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        raise RuntimeError("Authoritative privacy erasure requires PostgreSQL")
    op.create_table(
        "privacy_erasures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("requester_id", sa.String(36), nullable=False),
        sa.Column("organization_id", sa.String(36)),
        sa.Column("receipt_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *[
            sa.Column(name, sa.JSON(), nullable=False)
            for name in ("document_ids", "organization_ids", "object_keys", "prefixes")
        ],
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(40)),
        sa.Column("verification", sa.JSON()),
        sa.UniqueConstraint("scope", "target_id", name="uq_erasure_target"),
        sa.CheckConstraint(
            "scope IN ('account','organization','document')", name="ck_erasure_scope"
        ),
        sa.CheckConstraint(
            "status IN ('REQUESTED','ERASING_OBJECTS','VERIFYING','COMPLETED','FAILED')",
            name="ck_erasure_status",
        ),
    )
    op.create_index("ix_privacy_erasures_status", "privacy_erasures", ["status"])
    op.execute("REVOKE ALL ON privacy_erasures FROM azaeron_app, PUBLIC")
    op.execute("GRANT SELECT ON privacy_erasures TO azaeron_app")
    op.execute("ALTER TABLE privacy_erasures ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE privacy_erasures FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY privacy_requester ON privacy_erasures FOR SELECT
      USING (requester_id = app.current_user_id())"""
    )
    for table in ("users", "organizations", "documents"):
        op.add_column(
            table,
            sa.Column(
                "erasure_pending", sa.Boolean(), nullable=False, server_default="false"
            ),
        )
    for table, column in ACTOR_COLUMNS:
        op.alter_column(table, column, nullable=True)

    op.execute(
        """CREATE FUNCTION app.privacy_internal() RETURNS boolean LANGUAGE sql STABLE
      SET search_path = pg_catalog, public, app AS $$
      SELECT current_user = pg_get_userbyid(p.proowner)
        AND nullif(current_setting('app.privacy_request', true),'') IS NOT NULL
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE n.nspname='app' AND p.proname='privacy_erase_database';
    $$"""
    )
    for name in IMMUTABLE_FUNCTIONS:
        definition = bind.scalar(
            sa.text("SELECT pg_get_functiondef(to_regprocedure(:name))"),
            {"name": f"app.{name}()"},
        )
        if not definition:
            raise RuntimeError(f"Missing immutable guard: {name}")
        definition = re.sub(
            r"\bBEGIN\b",
            lambda _: "BEGIN" + PRIVACY_BRANCH,
            definition,
            count=1,
            flags=re.IGNORECASE,
        )
        op.execute(sa.text(definition))

    # This guard is intentionally INVOKER: a caller-set GUC cannot authorize it.
    # Share locks serialize child writes with request-time root row fencing.
    op.execute(
        """CREATE FUNCTION app.privacy_write_fence() RETURNS trigger LANGUAGE plpgsql
      SET search_path = pg_catalog, public, app AS $$
    DECLARE row_data jsonb; parent_id text; blocked boolean;
    BEGIN
      IF app.privacy_internal() THEN RETURN NEW; END IF;
      row_data := to_jsonb(NEW);
      IF TG_TABLE_NAME IN ('users','organizations','documents') THEN
        IF NEW.erasure_pending OR (TG_OP='UPDATE' AND OLD.erasure_pending) THEN
          RAISE EXCEPTION 'resource is unavailable during erasure';
        END IF;
        IF EXISTS (SELECT 1 FROM privacy_erasures WHERE
          (scope = CASE TG_TABLE_NAME WHEN 'users' THEN 'account' WHEN 'organizations' THEN 'organization' ELSE 'document' END AND target_id=NEW.id)
          OR (TG_TABLE_NAME='documents' AND document_ids::jsonb ? NEW.id)
          OR (TG_TABLE_NAME='organizations' AND organization_ids::jsonb ? NEW.id)) THEN
          RAISE EXCEPTION 'erased resource cannot be recreated';
        END IF;
      END IF;
      parent_id := row_data->>'organization_id';
      IF parent_id IS NOT NULL THEN
        SELECT erasure_pending INTO blocked FROM organizations WHERE id=parent_id FOR SHARE;
        IF blocked THEN RAISE EXCEPTION 'workspace is unavailable during erasure'; END IF;
      END IF;
      parent_id := row_data->>'document_id';
      IF parent_id IS NOT NULL THEN
        SELECT erasure_pending INTO blocked FROM documents WHERE id=parent_id FOR SHARE;
        IF blocked THEN RAISE EXCEPTION 'document is unavailable during erasure'; END IF;
      END IF;
      FOREACH parent_id IN ARRAY ARRAY[row_data->>'owner_id',row_data->>'user_id',row_data->>'created_by_id',row_data->>'student_id'] LOOP
        IF parent_id IS NOT NULL THEN
          SELECT erasure_pending INTO blocked FROM users WHERE id=parent_id FOR SHARE;
          IF blocked THEN RAISE EXCEPTION 'account is unavailable during erasure'; END IF;
        END IF;
      END LOOP;
      RETURN NEW;
    END $$"""
    )
    tables = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','privacy_erasures')"
            )
        )
    ]
    for table in tables:
        # Schema-discovered identifiers originate exclusively from migrated tables.
        op.execute(
            f'CREATE TRIGGER privacy_write_fence BEFORE INSERT OR UPDATE ON "{table}" FOR EACH ROW EXECUTE FUNCTION app.privacy_write_fence()'
        )
    op.execute(
        "CREATE POLICY privacy_hidden ON documents AS RESTRICTIVE FOR SELECT USING (NOT erasure_pending)"
    )
    for table in (*ARTIFACT_TABLES, "document_versions"):
        op.execute(
            f"""CREATE POLICY privacy_hidden ON "{table}" AS RESTRICTIVE FOR SELECT
          USING (EXISTS (SELECT 1 FROM documents d WHERE d.id="{table}".document_id AND NOT d.erasure_pending))"""
        )

    op.execute(
        """CREATE FUNCTION app.privacy_request(p_id text, p_scope text, p_target text, p_digest text)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
    DECLARE actor text := app.current_user_id(); tenant text := app.current_organization_id();
      docs text[] := '{}'; orgs text[] := '{}'; keys text[] := '{}'; paths text[] := '{}';
      found_id text; d record; owner_role text;
    BEGIN
      IF actor IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=actor AND is_active) THEN
        RAISE EXCEPTION 'privacy authorization denied' USING ERRCODE='42501';
      END IF;
      IF p_scope NOT IN ('account','organization','document') OR length(p_digest)<>64 THEN
        RAISE EXCEPTION 'invalid erasure request';
      END IF;
      -- Lock identity first, then organizations and documents in stable order.
      PERFORM 1 FROM users WHERE id=actor FOR UPDATE;
      SELECT id INTO found_id FROM privacy_erasures WHERE scope=p_scope AND target_id=p_target AND requester_id=actor;
      IF found_id IS NOT NULL THEN RETURN found_id; END IF;
      IF p_scope='account' THEN
        IF p_target<>actor THEN RAISE EXCEPTION 'privacy authorization denied' USING ERRCODE='42501'; END IF;
        IF EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=actor AND m.is_active AND m.role::text='OWNER'
          AND EXISTS(SELECT 1 FROM memberships x WHERE x.organization_id=m.organization_id AND x.user_id<>actor AND x.is_active)
          AND NOT EXISTS(SELECT 1 FROM memberships x WHERE x.organization_id=m.organization_id AND x.user_id<>actor AND x.is_active AND x.role::text='OWNER')) THEN
          RAISE EXCEPTION 'transfer workspace ownership or erase the workspace first' USING ERRCODE='P0002';
        END IF;
        SELECT coalesce(array_agg(o.id ORDER BY o.id),'{}') INTO orgs FROM organizations o
          JOIN memberships m ON m.organization_id=o.id WHERE m.user_id=actor AND m.role::text='OWNER'
          AND NOT EXISTS(SELECT 1 FROM memberships x WHERE x.organization_id=o.id AND x.user_id<>actor AND x.is_active);
        PERFORM 1 FROM organizations WHERE id IN (SELECT organization_id FROM memberships WHERE user_id=actor) ORDER BY id FOR UPDATE;
        FOR d IN SELECT DISTINCT organization_id FROM memberships WHERE user_id=actor LOOP
          paths := paths || ARRAY['uploads/'||d.organization_id||'/'||actor||'/', 'versions/uploads/'||d.organization_id||'/'||actor||'/'];
        END LOOP;
      ELSE
        SELECT role::text INTO owner_role FROM memberships WHERE organization_id=tenant AND user_id=actor AND is_active;
        IF p_scope='organization' THEN
          IF p_target IS DISTINCT FROM tenant OR owner_role IS DISTINCT FROM 'OWNER' THEN
            RAISE EXCEPTION 'privacy authorization denied' USING ERRCODE='42501';
          END IF;
          orgs := ARRAY[p_target];
        ELSE
          IF NOT EXISTS(SELECT 1 FROM documents WHERE id=p_target AND organization_id=tenant
            AND (owner_id=actor OR owner_role IN ('OWNER','ADMIN'))) THEN
            RAISE EXCEPTION 'privacy authorization denied' USING ERRCODE='42501';
          END IF;
        END IF;
        PERFORM 1 FROM organizations WHERE id=tenant FOR UPDATE;
      END IF;
      PERFORM 1 FROM documents WHERE (p_scope='document' AND id=p_target)
        OR organization_id=ANY(orgs) OR (p_scope='account' AND owner_id=actor) ORDER BY id FOR UPDATE;
      SELECT coalesce(array_agg(id ORDER BY id),'{}') INTO docs FROM documents WHERE
        (p_scope='document' AND id=p_target) OR organization_id=ANY(orgs) OR (p_scope='account' AND owner_id=actor);
      SELECT coalesce(array_agg(DISTINCT storage_path),'{}') INTO keys FROM (
        SELECT storage_path FROM document_versions WHERE document_id=ANY(docs)
        UNION SELECT storage_path FROM documents WHERE id=ANY(docs)) k;
      FOR d IN SELECT id,organization_id FROM documents WHERE id=ANY(docs) LOOP
        paths := paths || ARRAY['versions/'||d.organization_id||'/'||d.id||'/'];
      END LOOP;
      FOREACH found_id IN ARRAY orgs LOOP
        paths := paths || ARRAY['uploads/'||found_id||'/', 'versions/'||found_id||'/', 'versions/uploads/'||found_id||'/'];
      END LOOP;
      INSERT INTO privacy_erasures(id,scope,target_id,requester_id,organization_id,receipt_digest,status,
        document_ids,organization_ids,object_keys,prefixes,not_before)
      VALUES(p_id,p_scope,p_target,actor,tenant,p_digest,'REQUESTED',to_json(docs),to_json(orgs),to_json(keys),to_json(paths),clock_timestamp()+interval '8 minutes');
      PERFORM set_config('app.privacy_request',p_id,true);
      UPDATE documents SET erasure_pending=true WHERE id=ANY(docs);
      UPDATE organizations SET erasure_pending=true,is_active=false WHERE id=ANY(orgs);
      IF p_scope='account' THEN
        UPDATE users SET erasure_pending=true,is_active=false,session_version=session_version+1 WHERE id=actor;
        UPDATE refresh_tokens SET revoked_at=clock_timestamp() WHERE user_id=actor;
        UPDATE api_keys SET is_active=false,revoked_at=clock_timestamp() WHERE user_id=actor;
      END IF;
      UPDATE api_keys SET is_active=false,revoked_at=clock_timestamp() WHERE organization_id=ANY(orgs);
      PERFORM set_config('app.privacy_request','',true);
      RETURN p_id;
    END $$"""
    )

    delete_artifacts = "\n".join(
        f'DELETE FROM "{table}" WHERE document_id=ANY(artifacts);'
        for table in ARTIFACT_TABLES
    )
    op.execute(
        f"""CREATE FUNCTION app.privacy_erase_database(p_id text) RETURNS jsonb
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
    DECLARE r privacy_erasures%ROWTYPE; docs text[]; orgs text[]; artifacts text[];
    BEGIN
      SELECT * INTO r FROM privacy_erasures WHERE id=p_id FOR UPDATE;
      IF NOT FOUND THEN RAISE EXCEPTION 'erasure request missing'; END IF;
      IF r.status<>'REQUESTED' THEN RETURN to_jsonb(r); END IF;
      SELECT coalesce(array_agg(value),'{{}}') INTO docs FROM json_array_elements_text(r.document_ids);
      SELECT coalesce(array_agg(value),'{{}}') INTO orgs FROM json_array_elements_text(r.organization_ids);
      PERFORM set_config('app.privacy_request',p_id,true);
      -- Remove derivative evidence elsewhere in the same tenant that quotes an erased source.
      SELECT coalesce(array_agg(DISTINCT id),'{{}}') INTO artifacts FROM (
        SELECT unnest(docs) id UNION SELECT document_id FROM similarity_matches WHERE source_document_id=ANY(docs)
        UNION SELECT document_id FROM document_versions WHERE r.scope='account' AND (created_by_id=r.target_id OR uploaded_by_id=r.target_id)
        UNION SELECT document_id FROM provenance_events WHERE r.scope='account' AND user_id=r.target_id
        UNION SELECT document_id FROM provenance_exports WHERE r.scope='account' AND exported_by_id=r.target_id
      ) affected;
      PERFORM 1 FROM documents WHERE id=ANY(artifacts) ORDER BY id FOR UPDATE;
      {delete_artifacts}
      DELETE FROM audit_logs WHERE resource_id=ANY(docs) OR organization_id=ANY(orgs)
        OR (r.scope='account' AND (user_id=r.target_id OR resource_id=r.target_id));
      DELETE FROM submissions WHERE document_id=ANY(docs) OR (r.scope='account' AND student_id=r.target_id);
      DELETE FROM document_versions WHERE document_id=ANY(docs);
      DELETE FROM documents WHERE id=ANY(docs);
      DELETE FROM organizations WHERE id=ANY(orgs);
      IF r.scope='account' THEN
        UPDATE document_versions SET created_by_id=NULL WHERE created_by_id=r.target_id;
        UPDATE document_versions SET uploaded_by_id=NULL WHERE uploaded_by_id=r.target_id;
        UPDATE assignments SET created_by_id=NULL WHERE created_by_id=r.target_id;
        UPDATE submissions SET graded_by_id=NULL WHERE graded_by_id=r.target_id;
        UPDATE memberships SET invited_by_id=NULL WHERE invited_by_id=r.target_id;
        DELETE FROM compliance_reports WHERE generated_by_id=r.target_id;
        UPDATE aegis_edits SET user_id=NULL WHERE user_id=r.target_id;
        DELETE FROM users WHERE id=r.target_id;
      END IF;
      UPDATE privacy_erasures SET status='ERASING_OBJECTS',updated_at=clock_timestamp() WHERE id=p_id RETURNING * INTO r;
      PERFORM set_config('app.privacy_request','',true);
      RETURN to_jsonb(r);
    END $$"""
    )
    op.execute(
        """CREATE FUNCTION app.privacy_pending() RETURNS SETOF text LANGUAGE sql SECURITY DEFINER
      SET search_path=pg_catalog,public,app AS $$
      SELECT id::text FROM privacy_erasures WHERE status<>'COMPLETED' ORDER BY created_at LIMIT 25
    $$"""
    )
    op.execute(
        """CREATE FUNCTION app.privacy_result(p_id text, p_success boolean, p_count integer) RETURNS text
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
    DECLARE r privacy_erasures%ROWTYPE;
    BEGIN
      SELECT * INTO r FROM privacy_erasures WHERE id=p_id FOR UPDATE;
      IF NOT FOUND OR r.status='REQUESTED' THEN RAISE EXCEPTION 'database erasure has not completed'; END IF;
      IF r.status='COMPLETED' THEN RETURN r.status; END IF;
      IF EXISTS(SELECT 1 FROM documents WHERE id IN (SELECT json_array_elements_text(r.document_ids)))
        OR EXISTS(SELECT 1 FROM organizations WHERE id IN (SELECT json_array_elements_text(r.organization_ids)))
        OR (r.scope='account' AND EXISTS(SELECT 1 FROM users WHERE id=r.target_id)) THEN
        RAISE EXCEPTION 'database erasure verification failed';
      END IF;
      UPDATE privacy_erasures SET attempts=attempts+1,updated_at=clock_timestamp(),
        status=CASE WHEN NOT p_success THEN 'FAILED' WHEN clock_timestamp()<not_before THEN 'VERIFYING' ELSE 'COMPLETED' END,
        last_error=CASE WHEN p_success THEN NULL ELSE 'object_deletion_unverified' END,
        completed_at=CASE WHEN p_success AND clock_timestamp()>=not_before THEN clock_timestamp() ELSE NULL END,
        verification=json_build_object('database_absent',true,'objects_absent',p_success,'removed_versions',p_count)
      WHERE id=p_id RETURNING * INTO r;
      RETURN r.status;
    END $$"""
    )
    op.execute(
        """CREATE FUNCTION app.privacy_receipt(p_id text,p_digest text) RETURNS jsonb LANGUAGE sql SECURITY DEFINER
      SET search_path=pg_catalog,public,app AS $$
      SELECT jsonb_build_object('id',id,'scope',scope,'status',status,'created_at',created_at,'completed_at',completed_at,'last_error',last_error)
      FROM privacy_erasures WHERE id=p_id AND receipt_digest=p_digest
    $$"""
    )
    for signature in (
        "privacy_request(text,text,text,text)",
        "privacy_erase_database(text)",
        "privacy_pending()",
        "privacy_result(text,boolean,integer)",
        "privacy_receipt(text,text)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION app.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{signature} TO azaeron_app")


def downgrade():
    # Erasure cannot be undone; dropping tombstones would permit deleted data to reappear.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM privacy_erasures")):
        raise RuntimeError(
            "Cannot discard erasure tombstones; use a compatible application rollback"
        )
    for signature in (
        "privacy_receipt(text,text)",
        "privacy_result(text,boolean,integer)",
        "privacy_pending()",
        "privacy_erase_database(text)",
        "privacy_request(text,text,text,text)",
    ):
        op.execute(f"DROP FUNCTION app.{signature}")
    tables = [
        row[0]
        for row in op.get_bind().execute(
            sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename NOT IN ('alembic_version','privacy_erasures')"
            )
        )
    ]
    for table in tables:
        op.execute(f'DROP TRIGGER privacy_write_fence ON "{table}"')
    for table in (*ARTIFACT_TABLES, "document_versions", "documents"):
        op.execute(f'DROP POLICY privacy_hidden ON "{table}"')
    op.execute("DROP FUNCTION app.privacy_write_fence()")
    for name in IMMUTABLE_FUNCTIONS:
        definition = op.get_bind().scalar(
            sa.text("SELECT pg_get_functiondef(to_regprocedure(:name))"),
            {"name": f"app.{name}()"},
        )
        op.execute(sa.text(definition.replace(PRIVACY_BRANCH, "")))
    op.execute("DROP FUNCTION app.privacy_internal()")
    for table, column in ACTOR_COLUMNS:
        if op.get_bind().scalar(
            sa.text(f'SELECT count(*) FROM "{table}" WHERE "{column}" IS NULL')
        ):
            raise RuntimeError(
                "Cannot restore non-null attribution after privacy redaction"
            )
        op.alter_column(table, column, nullable=False)
    for table in ("users", "organizations", "documents"):
        op.drop_column(table, "erasure_pending")
    op.drop_table("privacy_erasures")
