"""Allow immutable analysis to coexist with saves without weakening erasure."""

from alembic import op
import sqlalchemy as sa

revision = "20260928_0036"
down_revision = "20260924_0035"
branch_labels = None
depends_on = None


def _fence(old, new):
    bind = op.get_bind()
    definition = bind.execute(
        sa.text("SELECT pg_get_functiondef('app.privacy_write_fence()'::regprocedure)")
    ).scalar_one()
    source = f"FROM documents WHERE id=parent_id FOR {old};"
    if definition.count(source) != 1:
        raise RuntimeError("Unexpected document privacy fence definition")
    op.execute(
        sa.text(
            definition.replace(source, f"FROM documents WHERE id=parent_id FOR {new};")
        )
    )


def upgrade():
    # storage_path is NOT NULL, so the predicate preserves exactly the existing
    # uniqueness guarantee. No foreign key references this mutable path. Unlike
    # a FK-eligible unique constraint, this index does not make a path change
    # acquire a FOR UPDATE lock on PostgreSQL 16.
    op.drop_constraint("uq_documents_storage_path", "documents", type_="unique")
    op.create_index(
        "uq_documents_storage_path",
        "documents",
        ["storage_path"],
        unique=True,
        postgresql_where=sa.text("storage_path IS NOT NULL"),
    )
    # privacy_request explicitly takes FOR UPDATE on every affected document
    # before marking it for erasure; KEY SHARE still conflicts with that fence
    # and with deletion, but permits ordinary revision metadata updates.
    _fence("SHARE", "KEY SHARE")


def downgrade():
    _fence("KEY SHARE", "SHARE")
    op.drop_index("uq_documents_storage_path", table_name="documents")
    op.create_unique_constraint(
        "uq_documents_storage_path", "documents", ["storage_path"]
    )
