"""User-approved voice statistics and source-dependent erasure."""

from alembic import op
import sqlalchemy as sa

revision = "20260929_0038"
down_revision = "20260929_0037"
branch_labels = None
depends_on = None

ERASE_VOICE = """
      DELETE FROM ai_voice_profiles WHERE organization_id=ANY(orgs)
        OR (r.scope='account' AND user_id=r.target_id)
        OR EXISTS(SELECT 1 FROM jsonb_array_elements(samples::jsonb) sample
          WHERE sample->>'document_id'=ANY(artifacts));
"""


def upgrade():
    op.create_table(
        "ai_voice_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("samples", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("policy_revision", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
    )
    for name in ("organization_id", "user_id"):
        op.create_index("ix_ai_voice_profiles_" + name, "ai_voice_profiles", [name])
    op.execute("ALTER TABLE ai_voice_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_voice_profiles FORCE ROW LEVEL SECURITY")
    scope = "organization_id=app.current_organization_id() AND user_id=app.current_user_id()"
    op.execute(
        f"CREATE POLICY ai_actor_tenant ON ai_voice_profiles USING ({scope}) WITH CHECK ({scope})"
    )
    op.execute(
        "CREATE TRIGGER privacy_write_fence BEFORE INSERT OR UPDATE ON ai_voice_profiles FOR EACH ROW EXECUTE FUNCTION app.privacy_write_fence()"
    )
    op.execute(
        "CREATE TRIGGER ai_evidence_guard BEFORE UPDATE ON ai_voice_profiles FOR EACH ROW EXECUTE FUNCTION app.ai_evidence_guard()"
    )
    op.execute(
        """CREATE FUNCTION app.ai_voice_lineage() RETURNS trigger LANGUAGE plpgsql
      SET search_path=pg_catalog,public,app AS $$
      DECLARE sample jsonb;
      BEGIN
        IF jsonb_typeof(NEW.samples::jsonb)<>'array' OR jsonb_array_length(NEW.samples::jsonb) NOT BETWEEN 1 AND 5 THEN
          RAISE EXCEPTION 'invalid voice samples';
        END IF;
        FOR sample IN SELECT * FROM jsonb_array_elements(NEW.samples::jsonb) LOOP
          IF NOT EXISTS(SELECT 1 FROM documents d JOIN document_versions v ON v.document_id=d.id
            WHERE d.id=sample->>'document_id' AND v.id=sample->>'document_version_id'
              AND d.organization_id=NEW.organization_id AND d.owner_id=NEW.user_id AND NOT d.erasure_pending
              AND sample->>'approved_by'=NEW.user_id) THEN
            RAISE EXCEPTION 'voice sample must be user owned and approved';
          END IF;
        END LOOP;
        RETURN NEW;
      END $$"""
    )
    op.execute(
        "CREATE TRIGGER ai_voice_lineage BEFORE INSERT ON ai_voice_profiles FOR EACH ROW EXECUTE FUNCTION app.ai_voice_lineage()"
    )
    op.execute("REVOKE ALL ON ai_voice_profiles FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT,DELETE ON ai_voice_profiles TO azaeron_app")
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    marker = "DELETE FROM ai_action_receipts WHERE"
    if definition.count(marker) != 1:
        raise RuntimeError("Unexpected agent privacy procedure")
    op.execute(sa.text(definition.replace(marker, ERASE_VOICE + "\n      " + marker)))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM ai_voice_profiles)")):
        raise RuntimeError("Cannot discard approved voice profiles")
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    op.execute(sa.text(definition.replace(ERASE_VOICE, "")))
    op.drop_table("ai_voice_profiles")
    op.execute("DROP FUNCTION app.ai_voice_lineage()")
