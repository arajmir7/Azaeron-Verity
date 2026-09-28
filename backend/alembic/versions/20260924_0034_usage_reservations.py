"""Durable quota accounting survives retries and individual privacy erasure."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0034"
down_revision = "20260924_0033"
branch_labels = None
depends_on = None

ERASE_USAGE = """
      PERFORM pg_advisory_xact_lock(hashtextextended('usage:'||organization_id,0))
        FROM (SELECT DISTINCT organization_id FROM usage_operations WHERE document_id=ANY(artifacts)
          OR organization_id=ANY(orgs) OR (r.scope='account' AND user_id=r.target_id) ORDER BY organization_id) usage_orgs;
      UPDATE usage_buckets b SET reserved=b.reserved-x.n FROM (
        SELECT organization_id,period,task,count(*) n FROM usage_operations
        WHERE status='RESERVED' AND (document_id=ANY(artifacts) OR organization_id=ANY(orgs)
          OR (r.scope='account' AND user_id=r.target_id)) GROUP BY organization_id,period,task
      ) x WHERE b.organization_id=x.organization_id AND b.period=x.period AND b.task=x.task;
      DELETE FROM usage_operations WHERE document_id=ANY(artifacts) OR organization_id=ANY(orgs)
        OR (r.scope='account' AND user_id=r.target_id);
"""


def base_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("task", sa.String(40), nullable=False),
    ]


def upgrade():
    op.create_table(
        "usage_buckets",
        *base_columns(),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "organization_id", "period", "task", name="uq_usage_bucket"
        ),
        sa.CheckConstraint(
            "reserved >= 0 AND committed >= 0", name="ck_usage_bucket_counts"
        ),
    )
    op.create_table(
        "usage_operations",
        *base_columns(),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *[
            sa.Column(name, sa.String(36))
            for name in ("api_key_id", "document_id", "job_id")
        ],
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("outcome", sa.String(40)),
        sa.Column(
            "chargeable", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.false()),
        *[
            sa.Column(name, sa.Integer())
            for name in (
                "input_tokens",
                "output_tokens",
                "duration_ms",
                "response_status",
            )
        ],
        sa.Column("model_calls", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("response_ciphertext", sa.Text()),
        sa.Column("response_expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "organization_id", "task", "operation_id", name="uq_usage_operation"
        ),
        sa.CheckConstraint(
            "status IN ('RESERVED','COMMITTED','RELEASED')", name="ck_usage_status"
        ),
        *[
            sa.CheckConstraint(
                f"{name} IS NULL OR {name} >= 0", name="ck_usage_" + suffix
            )
            for name, suffix in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("duration_ms", "duration"),
            )
        ],
    )
    for table in ("usage_buckets", "usage_operations"):
        op.create_index("ix_" + table + "_organization_id", table, ["organization_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY usage_tenant ON {table} USING (organization_id=app.current_organization_id()) WITH CHECK (organization_id=app.current_organization_id())"
        )
        op.execute(
            f"CREATE TRIGGER privacy_write_fence BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.privacy_write_fence()"
        )
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO azaeron_app")
    for column in ("user_id", "document_id", "job_id", "expires_at"):
        op.create_index("ix_usage_operations_" + column, "usage_operations", [column])
    # Seed historical upload consumption, including archived documents. Later
    # erasure does not refund this nonpersonal tenant aggregate.
    op.execute(
        """INSERT INTO usage_buckets(id,organization_id,period,task,reserved,committed)
      SELECT md5(organization_id||to_char(created_at,'YYYY-MM'))::uuid::text,
        organization_id,to_char(created_at,'YYYY-MM'),'document_upload',0,count(*)
      FROM documents GROUP BY organization_id,to_char(created_at,'YYYY-MM')"""
    )
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        "DELETE FROM audit_logs WHERE",
        ERASE_USAGE + "\n      DELETE FROM audit_logs WHERE",
    )
    op.execute(sa.text(definition))


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM usage_operations) OR EXISTS(SELECT 1 FROM usage_buckets WHERE committed>0 OR reserved>0)"
        )
    ):
        raise RuntimeError(
            "Cannot discard usage operation identities; use a compatible application rollback"
        )
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.privacy_erase_database(text)'::regprocedure)"
        )
    )
    op.execute(sa.text(definition.replace(ERASE_USAGE, "")))
    op.drop_table("usage_operations")
    op.drop_table("usage_buckets")
