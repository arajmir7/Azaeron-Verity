"""Do not relocate objects while queued or running jobs still name them."""

from alembic import op
import sqlalchemy as sa

revision = "20260924_0033"
down_revision = "20260924_0032"
branch_labels = None
depends_on = None


def upgrade():
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.storage_legacy_candidates()'::regprocedure)"
        )
    )
    definition = definition.replace(
        "AND NOT d.erasure_pending ORDER BY",
        "AND NOT d.erasure_pending AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.document_version_id=v.id AND j.status IN ('PENDING','RUNNING','RETRYING')) ORDER BY",
    )
    op.execute(sa.text(definition))
    definition = op.get_bind().scalar(
        sa.text(
            "SELECT pg_get_functiondef('app.storage_relocate(text,text,text,text)'::regprocedure)"
        )
    )
    definition = definition.replace(
        "expected :=",
        "IF EXISTS (SELECT 1 FROM jobs WHERE document_version_id=p_version AND status IN ('PENDING','RUNNING','RETRYING')) THEN RAISE EXCEPTION 'legacy target has active jobs'; END IF;\n      expected :=",
    )
    op.execute(sa.text(definition))


def downgrade():
    # Application rollback retains the stronger relocation fence.
    pass
