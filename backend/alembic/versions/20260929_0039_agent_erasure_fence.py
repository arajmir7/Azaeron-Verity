"""Hide source-derived chat evidence immediately when erasure is requested."""

from alembic import op

revision = "20260929_0039"
down_revision = "20260929_0038"
branch_labels = None
depends_on = None

PREDICATES = {
    "ai_conversations": "app.ai_conversation_visible(organization_id,user_id,id)",
    "ai_messages": "app.ai_conversation_visible(organization_id,user_id,conversation_id)",
    "ai_runs": "app.ai_conversation_visible(organization_id,user_id,conversation_id)",
    "ai_document_attachments": "app.ai_conversation_visible(organization_id,user_id,conversation_id)",
    "ai_events": "EXISTS(SELECT 1 FROM ai_runs r WHERE r.id=run_id)",
    "ai_tool_calls": "EXISTS(SELECT 1 FROM ai_runs r WHERE r.id=run_id)",
    "ai_tool_results": "EXISTS(SELECT 1 FROM ai_tool_calls c WHERE c.id=tool_call_id)",
    "ai_action_receipts": "app.ai_receipt_visible(organization_id,user_id,document_id,model_evidence::jsonb,similarity_before::jsonb,similarity_after::jsonb)",
    "ai_voice_profiles": "NOT EXISTS(SELECT 1 FROM jsonb_array_elements(samples::jsonb) sample WHERE NOT EXISTS(SELECT 1 FROM documents d WHERE d.id=sample->>'document_id' AND d.owner_id=user_id))",
}


def upgrade():
    # Boolean-only definer helpers avoid recursive policies through attachments.
    # Explicit context predicates prevent these helpers becoming tenant oracles.
    op.execute(
        """CREATE FUNCTION app.ai_conversation_visible(p_org text,p_user text,p_conversation text)
      RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
      SELECT p_org=app.current_organization_id() AND p_user=app.current_user_id()
        AND EXISTS(SELECT 1 FROM organizations WHERE id=p_org AND NOT erasure_pending)
        AND EXISTS(SELECT 1 FROM users WHERE id=p_user AND NOT erasure_pending)
        AND NOT EXISTS(SELECT 1 FROM ai_document_attachments a LEFT JOIN documents d ON d.id=a.document_id
          WHERE a.conversation_id=p_conversation AND a.organization_id=p_org AND a.user_id=p_user
            AND (d.id IS NULL OR d.erasure_pending));
      $$"""
    )
    op.execute(
        """CREATE FUNCTION app.ai_receipt_visible(p_org text,p_user text,p_document text,p_model jsonb,p_before jsonb,p_after jsonb)
      RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public,app AS $$
      SELECT p_org=app.current_organization_id() AND p_user=app.current_user_id()
        AND EXISTS(SELECT 1 FROM organizations WHERE id=p_org AND NOT erasure_pending)
        AND EXISTS(SELECT 1 FROM users WHERE id=p_user AND NOT erasure_pending)
        AND EXISTS(SELECT 1 FROM documents WHERE id=p_document AND organization_id=p_org AND NOT erasure_pending)
        AND NOT EXISTS(SELECT 1 FROM documents d WHERE d.organization_id=p_org AND d.erasure_pending
          AND (p_model->'source_dependencies' ? d.id OR strpos(coalesce(p_before::text,''),d.id)>0 OR strpos(coalesce(p_after::text,''),d.id)>0));
      $$"""
    )
    for signature in (
        "ai_conversation_visible(text,text,text)",
        "ai_receipt_visible(text,text,text,jsonb,jsonb,jsonb)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION app.{signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{signature} TO azaeron_app")
    for table, predicate in PREDICATES.items():
        op.execute(
            f"CREATE POLICY ai_privacy_hidden ON {table} AS RESTRICTIVE USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade():
    for table in PREDICATES:
        op.execute(f"DROP POLICY ai_privacy_hidden ON {table}")
    op.execute("DROP FUNCTION app.ai_receipt_visible(text,text,text,jsonb,jsonb,jsonb)")
    op.execute("DROP FUNCTION app.ai_conversation_visible(text,text,text)")
