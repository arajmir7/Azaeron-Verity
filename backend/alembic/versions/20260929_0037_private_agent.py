"""Private agent persistence, forced RLS, immutable evidence and erasure coverage.

DDL is frozen here; this migration never imports live application metadata.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260929_0037"
down_revision = "20260928_0036"
branch_labels = None
depends_on = None

TABLES = [
    "ai_conversations",
    "ai_action_receipts",
    "ai_document_attachments",
    "ai_messages",
    "ai_runs",
    "ai_events",
    "ai_tool_calls",
    "ai_tool_results",
]
DDL = [
    "\nCREATE TABLE ai_conversations (\n\ttitle VARCHAR(200) NOT NULL, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (organization_id, user_id, id), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_action_receipts (\n\trun_id VARCHAR(36), \n\toperation_id VARCHAR(36) NOT NULL, \n\tdocument_id VARCHAR(36) NOT NULL, \n\tsource_version_id VARCHAR(36) NOT NULL, \n\tinput_sha256 VARCHAR(64) NOT NULL, \n\tcandidate_sha256 VARCHAR(64) NOT NULL, \n\tcandidate_text TEXT NOT NULL, \n\tcandidate_diff TEXT NOT NULL, \n\tmodel_evidence JSON NOT NULL, \n\tpolicy_revision VARCHAR(80) NOT NULL, \n\ttool_calls JSON NOT NULL, \n\tprotected_spans JSON NOT NULL, \n\tverification JSON NOT NULL, \n\tdecision VARCHAR(16) NOT NULL, \n\tresult_version_id VARCHAR(36), \n\tresult_sha256 VARCHAR(64), \n\tdecided_at TIMESTAMP WITH TIME ZONE, \n\tsimilarity_before JSON, \n\tsimilarity_after JSON, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (organization_id, user_id, operation_id), \n\tCONSTRAINT ck_ai_receipt_decision CHECK (decision IN ('PENDING','ACCEPTED','REJECTED')), \n\tCONSTRAINT ck_ai_receipt_result CHECK ((decision='ACCEPTED' AND result_version_id IS NOT NULL AND result_sha256 IS NOT NULL) OR (decision<>'ACCEPTED' AND result_version_id IS NULL AND result_sha256 IS NULL)), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(source_version_id) REFERENCES document_versions (id) ON DELETE CASCADE, \n\tFOREIGN KEY(result_version_id) REFERENCES document_versions (id) ON DELETE CASCADE, \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_document_attachments (\n\tconversation_id VARCHAR(36) NOT NULL, \n\tdocument_id VARCHAR(36) NOT NULL, \n\tdocument_version_id VARCHAR(36) NOT NULL, \n\tinput_sha256 VARCHAR(64) NOT NULL, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, conversation_id) REFERENCES ai_conversations (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (conversation_id, document_version_id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(document_version_id) REFERENCES document_versions (id) ON DELETE CASCADE, \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_messages (\n\tconversation_id VARCHAR(36) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\trole VARCHAR(12) NOT NULL, \n\tcontent TEXT NOT NULL, \n\treplaces_message_id VARCHAR(36), \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, conversation_id) REFERENCES ai_conversations (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (organization_id, user_id, id), \n\tCONSTRAINT ck_ai_message_role CHECK (role IN ('user','assistant','tool')), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_runs (\n\tconversation_id VARCHAR(36) NOT NULL, \n\tmessage_id VARCHAR(36) NOT NULL, \n\toperation_id VARCHAR(36) NOT NULL, \n\tfingerprint VARCHAR(64) NOT NULL, \n\tstatus VARCHAR(16) NOT NULL, \n\terror_code VARCHAR(80), \n\trequest JSON NOT NULL, \n\tmodel_evidence JSON NOT NULL, \n\tusage_operation_id VARCHAR(36) NOT NULL, \n\tsession_family VARCHAR(36) NOT NULL, \n\tsession_version INTEGER NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcompleted_at TIMESTAMP WITH TIME ZONE, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, conversation_id) REFERENCES ai_conversations (organization_id, user_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(organization_id, user_id, message_id) REFERENCES ai_messages (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (organization_id, user_id, id), \n\tUNIQUE (organization_id, user_id, operation_id), \n\tCONSTRAINT ck_ai_run_status CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','UNAVAILABLE','CANCELLED')), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_events (\n\trun_id VARCHAR(36) NOT NULL, \n\tsequence INTEGER NOT NULL, \n\tkind VARCHAR(32) NOT NULL, \n\tpayload JSON NOT NULL, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, run_id) REFERENCES ai_runs (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (run_id, sequence), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_tool_calls (\n\trun_id VARCHAR(36) NOT NULL, \n\tname VARCHAR(48) NOT NULL, \n\targuments JSON NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, run_id) REFERENCES ai_runs (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (organization_id, user_id, id), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE ai_tool_results (\n\ttool_call_id VARCHAR(36) NOT NULL, \n\tcontent JSON NOT NULL, \n\torganization_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(organization_id, user_id, tool_call_id) REFERENCES ai_tool_calls (organization_id, user_id, id) ON DELETE CASCADE, \n\tUNIQUE (tool_call_id), \n\tFOREIGN KEY(organization_id) REFERENCES organizations (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "CREATE INDEX ix_ai_conversations_organization_id ON ai_conversations (organization_id)",
    "CREATE INDEX ix_ai_conversations_user_id ON ai_conversations (user_id)",
    "CREATE INDEX ix_ai_action_receipts_run_id ON ai_action_receipts (run_id)",
    "CREATE INDEX ix_ai_action_receipts_user_id ON ai_action_receipts (user_id)",
    "CREATE INDEX ix_ai_action_receipts_organization_id ON ai_action_receipts (organization_id)",
    "CREATE INDEX ix_ai_action_receipts_document_id ON ai_action_receipts (document_id)",
    "CREATE INDEX ix_ai_document_attachments_user_id ON ai_document_attachments (user_id)",
    "CREATE INDEX ix_ai_document_attachments_conversation_id ON ai_document_attachments (conversation_id)",
    "CREATE INDEX ix_ai_document_attachments_organization_id ON ai_document_attachments (organization_id)",
    "CREATE INDEX ix_ai_document_attachments_document_id ON ai_document_attachments (document_id)",
    "CREATE INDEX ix_ai_messages_conversation_id ON ai_messages (conversation_id)",
    "CREATE INDEX ix_ai_messages_user_id ON ai_messages (user_id)",
    "CREATE INDEX ix_ai_messages_organization_id ON ai_messages (organization_id)",
    "CREATE INDEX ix_ai_runs_organization_id ON ai_runs (organization_id)",
    "CREATE INDEX ix_ai_runs_user_id ON ai_runs (user_id)",
    "CREATE INDEX ix_ai_runs_conversation_id ON ai_runs (conversation_id)",
    "CREATE INDEX ix_ai_events_organization_id ON ai_events (organization_id)",
    "CREATE INDEX ix_ai_events_run_id ON ai_events (run_id)",
    "CREATE INDEX ix_ai_events_user_id ON ai_events (user_id)",
    "CREATE INDEX ix_ai_tool_calls_run_id ON ai_tool_calls (run_id)",
    "CREATE INDEX ix_ai_tool_calls_user_id ON ai_tool_calls (user_id)",
    "CREATE INDEX ix_ai_tool_calls_organization_id ON ai_tool_calls (organization_id)",
    "CREATE INDEX ix_ai_tool_results_user_id ON ai_tool_results (user_id)",
    "CREATE INDEX ix_ai_tool_results_organization_id ON ai_tool_results (organization_id)",
]

ERASE_AGENT = """
      DELETE FROM ai_action_receipts WHERE document_id=ANY(artifacts)
        OR organization_id=ANY(orgs) OR (r.scope='account' AND user_id=r.target_id)
        OR EXISTS (SELECT 1 FROM unnest(artifacts) d WHERE
          model_evidence::jsonb->'source_dependencies' ? d
          OR strpos(coalesce(similarity_before::text,''),d)>0
          OR strpos(coalesce(similarity_after::text,''),d)>0);
      DELETE FROM ai_conversations WHERE organization_id=ANY(orgs)
        OR (r.scope='account' AND user_id=r.target_id)
        OR id IN (SELECT conversation_id FROM ai_document_attachments WHERE document_id=ANY(artifacts));
"""


def upgrade():
    for statement in DDL:
        op.execute(statement)
    op.create_unique_constraint(
        "uq_ai_message_sequence", "ai_messages", ["conversation_id", "sequence"]
    )
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = "organization_id=app.current_organization_id() AND user_id=app.current_user_id()"
        op.execute(
            f"CREATE POLICY ai_actor_tenant ON {table} USING ({predicate}) WITH CHECK ({predicate})"
        )
        op.execute(
            f"CREATE TRIGGER privacy_write_fence BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.privacy_write_fence()"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO azaeron_app")
    op.execute(
        """CREATE FUNCTION app.ai_lineage_guard() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public,app AS $$
      DECLARE data jsonb := to_jsonb(NEW); source_id text; parent_id text;
      BEGIN
        IF TG_TABLE_NAME IN ('ai_document_attachments','ai_action_receipts') THEN
          source_id := coalesce(data->>'document_version_id',data->>'source_version_id');
          IF NOT EXISTS(SELECT 1 FROM documents d JOIN document_versions v ON v.document_id=d.id
            WHERE d.id=NEW.document_id AND d.organization_id=NEW.organization_id AND v.id=source_id) THEN
            RAISE EXCEPTION 'invalid agent document lineage';
          END IF;
        END IF;
        IF TG_TABLE_NAME='ai_runs' THEN
          IF NOT EXISTS(SELECT 1 FROM ai_messages m WHERE m.id=NEW.message_id
            AND m.conversation_id=NEW.conversation_id AND m.organization_id=NEW.organization_id
            AND m.user_id=NEW.user_id AND m.role='user') THEN
            RAISE EXCEPTION 'invalid agent message lineage';
          END IF;
        END IF;
        IF TG_TABLE_NAME='ai_messages' AND data->>'replaces_message_id' IS NOT NULL THEN
          IF NOT EXISTS(SELECT 1 FROM ai_messages m WHERE m.id=NEW.replaces_message_id
            AND m.conversation_id=NEW.conversation_id AND m.organization_id=NEW.organization_id
            AND m.user_id=NEW.user_id AND m.role='user') THEN
            RAISE EXCEPTION 'invalid prompt replacement';
          END IF;
        END IF;
        RETURN NEW;
      END $$"""
    )
    for table in (
        "ai_document_attachments",
        "ai_action_receipts",
        "ai_runs",
        "ai_messages",
    ):
        op.execute(
            f"CREATE TRIGGER ai_lineage_guard BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.ai_lineage_guard()"
        )
    op.execute(
        """CREATE FUNCTION app.ai_evidence_guard() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public,app AS $$
      BEGIN
        IF TG_TABLE_NAME<>'ai_action_receipts' THEN
          RAISE EXCEPTION 'agent evidence is immutable';
        END IF;
        IF OLD.decision<>'PENDING' OR NEW.decision NOT IN ('ACCEPTED','REJECTED')
          OR (to_jsonb(NEW)-ARRAY['updated_at','decision','decided_at','result_version_id','result_sha256','similarity_after'])
          IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['updated_at','decision','decided_at','result_version_id','result_sha256','similarity_after']) THEN
          RAISE EXCEPTION 'receipt evidence is immutable';
        END IF;
        IF NEW.decided_at IS NULL THEN RAISE EXCEPTION 'receipt decision needs timestamp'; END IF;
        IF NEW.decision='ACCEPTED' AND NOT EXISTS(SELECT 1 FROM document_versions v
          WHERE v.id=NEW.result_version_id AND v.document_id=NEW.document_id
            AND v.previous_version_id=NEW.source_version_id AND v.created_by_id=NEW.user_id
            AND v.content_hash=NEW.candidate_sha256 AND v.content_hash=NEW.result_sha256) THEN
          RAISE EXCEPTION 'receipt result lineage mismatch';
        END IF;
        RETURN NEW;
      END $$"""
    )
    for table in (
        "ai_messages",
        "ai_events",
        "ai_document_attachments",
        "ai_tool_results",
        "ai_action_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER ai_evidence_guard BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.ai_evidence_guard()"
        )
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    marker = "DELETE FROM audit_logs WHERE"
    if definition.count(marker) != 1:
        raise RuntimeError("Unexpected privacy procedure")
    op.execute(sa.text(definition.replace(marker, ERASE_AGENT + "\n      " + marker)))


def downgrade():
    for table in TABLES:
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")):
            raise RuntimeError(
                "Cannot discard agent records; use a compatible application rollback"
            )
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    op.execute(sa.text(definition.replace(ERASE_AGENT, "")))
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute("DROP FUNCTION app.ai_evidence_guard()")
    op.execute("DROP FUNCTION app.ai_lineage_guard()")
