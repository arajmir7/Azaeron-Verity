"""Immutable parser output and exact organization/document/version lineage.

Revision ID: 20260913_0024
Revises: 20260913_0023
"""

from alembic import op
import sqlalchemy as sa
import hashlib
import json
import uuid

revision = "20260913_0024"
down_revision = "20260913_0023"
branch_labels = None
depends_on = None

LINEAGE_TABLES = (
    "jobs",
    "analysis_runs",
    "processed_documents",
    "document_chunks",
    "similarity_index_entries",
    "similarity_analyses",
    "similarity_matches",
    "claims",
    "citations",
    "citation_references",
    "citation_sources",
    "citation_findings",
    "authorship_signals",
    "detection_results",
    "detection_segments",
    "evidence_nodes",
    "evidence_edges",
    "provenance_events",
    "provenance_reports",
    "provenance_exports",
    "integrity_reports",
    "aegis_edits",
)
RELATIONS = {
    "analysis_runs": ("job_id", "jobs"),
    "detection_results": ("job_id", "jobs", "analysis_run_id", "analysis_runs"),
    "detection_segments": ("detection_result_id", "detection_results"),
    "claims": ("evidence_id", "evidence_nodes"),
    "citations": (
        "claim_id",
        "claims",
        "reference_id",
        "citation_references",
        "source_id",
        "citation_sources",
        "evidence_id",
        "evidence_nodes",
    ),
    "citation_references": ("source_id", "citation_sources"),
    "citation_findings": (
        "claim_id",
        "claims",
        "citation_id",
        "citations",
        "reference_id",
        "citation_references",
        "source_id",
        "citation_sources",
        "evidence_id",
        "evidence_nodes",
    ),
    "similarity_matches": (
        "analysis_id",
        "similarity_analyses",
        "evidence_id",
        "evidence_nodes",
    ),
}


def add_lineage_column(table, column, target):
    op.add_column(table, sa.Column(column, sa.String(36), nullable=True))
    op.create_foreign_key(
        f"fk_{table}_{column}_core",
        table,
        target,
        [column],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade():
    add_lineage_column("jobs", "document_version_id", "document_versions")
    # Use a recorded job input or uniquely identifiable historical analysis.
    # Never guess "latest" for a job whose target cannot be proven.
    op.execute(
        """
        UPDATE jobs j SET document_version_id = v.id FROM document_versions v, documents d
        WHERE v.id = j.input_data->>'document_version_id' AND v.document_id = j.document_id
          AND d.id = j.document_id AND d.organization_id = j.organization_id
    """
    )
    op.execute(
        """
        WITH targets AS (
          SELECT job_id, document_version_id FROM analysis_runs WHERE job_id IS NOT NULL
          UNION SELECT job_id, document_version_id FROM detection_results
          UNION SELECT j.id, v.id FROM jobs j JOIN document_versions v ON v.document_id = j.document_id
            WHERE v.storage_path = j.input_data->>'storage_key'
        ), resolved AS (SELECT job_id, min(document_version_id) version_id FROM targets GROUP BY job_id HAVING count(DISTINCT document_version_id) = 1)
        UPDATE jobs j SET document_version_id = r.version_id FROM resolved r WHERE j.id = r.job_id AND j.document_version_id IS NULL
    """
    )
    op.execute(
        """
        WITH sole AS (SELECT document_id, min(id) version_id FROM document_versions GROUP BY document_id HAVING count(*) = 1)
        UPDATE jobs j SET document_version_id = s.version_id FROM sole s WHERE j.document_id = s.document_id AND j.document_version_id IS NULL
    """
    )
    op.execute(
        """DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM jobs WHERE document_id IS NULL OR document_version_id IS NULL) THEN
        RAISE EXCEPTION 'Cannot prove immutable target for historical job; migration stopped without guessing or deleting history';
      END IF;
    END $$"""
    )
    op.alter_column("jobs", "document_id", nullable=False)
    op.alter_column("jobs", "document_version_id", nullable=False)
    for table, parent, key, parent_key in (
        ("detection_segments", "detection_results", "detection_result_id", "id"),
        ("evidence_edges", "evidence_nodes", "source_node_id", "node_id"),
    ):
        for column, target in (
            ("organization_id", "organizations"),
            ("document_id", "documents"),
            ("document_version_id", "document_versions"),
        ):
            if column == "organization_id" and table == "evidence_edges":
                continue
            add_lineage_column(table, column, target)
        op.execute(
            f"""UPDATE {table} t SET organization_id=p.organization_id, document_id=p.document_id,
                       document_version_id=p.document_version_id FROM {parent} p WHERE t.{key}=p.{parent_key}"""
        )
        for column in ("organization_id", "document_id", "document_version_id"):
            op.alter_column(table, column, nullable=False)
    add_lineage_column("citation_sources", "document_id", "documents")
    op.execute(
        "UPDATE citation_sources s SET document_id=v.document_id FROM document_versions v WHERE v.id=s.document_version_id"
    )
    op.alter_column("citation_sources", "document_id", nullable=False)

    op.add_column(
        "processed_documents",
        sa.Column(
            "parser_version",
            sa.String(80),
            nullable=False,
            server_default="legacy-unstructured",
        ),
    )
    for column in ("normalized_content_hash", "structure_fingerprint"):
        op.add_column(
            "processed_documents", sa.Column(column, sa.String(64), nullable=True)
        )
    op.add_column(
        "processed_documents", sa.Column("structure_json", sa.JSON(), nullable=True)
    )
    # Frozen legacy adapter: preserve existing text and segmentation exactly.
    # Lost source/page layout remains explicitly unavailable.
    bind = op.get_bind()
    for row in bind.execute(
        sa.text(
            "SELECT id, organization_id, document_id, document_version_id, pipeline_version, cleaned_text, paragraphs, sentences FROM processed_documents"
        )
    ).mappings():
        text = row["cleaned_text"] or ""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        parser = ("legacy:" + row["pipeline_version"])[:80]
        record = {
            "id": row["id"],
            "schema_version": "normalized-document-v1",
            "parser_version": parser,
            "organization_id": row["organization_id"],
            "document_id": row["document_id"],
            "document_version_id": row["document_version_id"],
            "normalized_content_hash": text_hash,
            "mapping_state": "LEGACY_TEXT_ONLY",
            "coordinate_system": "UNICODE_CODE_POINT_ZERO_BASED_END_EXCLUSIVE",
            "source_basis": "LEGACY_PROCESSED_TEXT",
            "page_mapping": "UNAVAILABLE",
            "pages": [],
            "headings": [],
            "sections": [],
            "tables": [],
            "references": [],
            "citations": [],
            "source_map": [],
            "source_locations": [],
            "limitations": [
                "Historical parser text and segmentation are retained; source/page mapping was not recorded."
            ],
        }
        for kind in ("paragraphs", "sentences"):
            items, cursor = [], 0
            for index, item in enumerate(row[kind] or []):
                value = item.get("text", "")
                start = text.find(value, cursor) if value else -1
                if start >= 0:
                    end = start + len(value)
                    items.append(
                        {
                            **item,
                            "id": str(
                                uuid.uuid5(
                                    uuid.NAMESPACE_URL,
                                    f"{row['id']}:{parser}:{kind}:{index}:{start}:{end}",
                                )
                            ),
                            "kind": kind[:-1],
                            "start": start,
                            "end": end,
                            "text": value,
                        }
                    )
                    cursor = end
            record[kind] = items
        fingerprint = hashlib.sha256(
            json.dumps(
                record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
        record["fingerprint"] = fingerprint
        bind.execute(
            sa.text(
                "UPDATE processed_documents SET parser_version=:parser, normalized_content_hash=:hash, structure_fingerprint=:fingerprint, structure_json=CAST(:record AS json) WHERE id=:id"
            ),
            {
                "id": row["id"],
                "parser": parser,
                "hash": text_hash,
                "fingerprint": fingerprint,
                "record": json.dumps(record),
            },
        )

    op.execute(
        """CREATE OR REPLACE FUNCTION app.enforce_analysis_target() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE row_doc text; row_org text; payload jsonb;
    BEGIN
      SELECT v.document_id, d.organization_id INTO row_doc, row_org
        FROM document_versions v JOIN documents d ON d.id=v.document_id WHERE v.id=NEW.document_version_id;
      IF row_doc IS NULL OR row_doc IS DISTINCT FROM NEW.document_id OR row_org IS DISTINCT FROM NEW.organization_id THEN
        RAISE EXCEPTION 'analysis organization/document/version target mismatch';
      END IF;
      IF TG_OP='UPDATE' AND (OLD.document_id IS DISTINCT FROM NEW.document_id OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
          OR OLD.document_version_id IS DISTINCT FROM NEW.document_version_id) THEN
        RAISE EXCEPTION 'analysis target lineage is immutable';
      END IF;
      IF TG_TABLE_NAME='processed_documents' AND TG_OP='INSERT' THEN
        payload := to_jsonb(NEW);
        IF payload->>'parser_version' IS NULL OR payload->>'parser_version'='legacy-unstructured'
          OR payload->>'normalized_content_hash' IS DISTINCT FROM encode(digest(convert_to(COALESCE(payload->>'cleaned_text',''), 'UTF8'), 'sha256'), 'hex')
          OR payload->'structure_json'->>'id' IS DISTINCT FROM NEW.id
          OR payload->'structure_json'->>'organization_id' IS DISTINCT FROM NEW.organization_id
          OR payload->'structure_json'->>'document_id' IS DISTINCT FROM NEW.document_id
          OR payload->'structure_json'->>'document_version_id' IS DISTINCT FROM NEW.document_version_id
          OR payload->'structure_json'->>'normalized_content_hash' IS DISTINCT FROM payload->>'normalized_content_hash'
          OR payload->'structure_json'->>'fingerprint' IS DISTINCT FROM payload->>'structure_fingerprint' THEN
          RAISE EXCEPTION 'normalized parser output must carry its exact target and content fingerprint';
        END IF;
      END IF;
      RETURN NEW;
    END $$"""
    )
    for table in LINEAGE_TABLES:
        op.execute(
            f"""DO $$ BEGIN IF EXISTS (SELECT 1 FROM {table} t JOIN document_versions v ON v.id=t.document_version_id
          JOIN documents d ON d.id=v.document_id WHERE t.document_id IS DISTINCT FROM v.document_id OR t.organization_id IS DISTINCT FROM d.organization_id)
          THEN RAISE EXCEPTION 'Existing {table} lineage is inconsistent; repair requires evidence'; END IF; END $$"""
        )
        op.execute(
            f"CREATE TRIGGER {table}_exact_target BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.enforce_analysis_target()"
        )
    op.execute(
        """CREATE OR REPLACE FUNCTION app.enforce_related_analysis_target() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent jsonb; child jsonb; ref text; i integer;
    BEGIN
      child := to_jsonb(NEW); i := 0;
      WHILE i < TG_NARGS LOOP
        ref := child->>TG_ARGV[i];
        IF ref IS NOT NULL THEN
          EXECUTE format('SELECT to_jsonb(p) FROM %I p WHERE id=$1', TG_ARGV[i+1]) INTO parent USING ref;
          IF parent IS NULL OR parent->>'organization_id' IS DISTINCT FROM NEW.organization_id
            OR parent->>'document_id' IS DISTINCT FROM NEW.document_id OR parent->>'document_version_id' IS DISTINCT FROM NEW.document_version_id THEN
            RAISE EXCEPTION 'related analysis records must share one immutable target';
          END IF;
        END IF;
        i := i + 2;
      END LOOP;
      RETURN NEW;
    END $$"""
    )
    for table, args in RELATIONS.items():
        arguments = ", ".join("'" + arg + "'" for arg in args)
        op.execute(
            f"CREATE TRIGGER {table}_related_target BEFORE INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION app.enforce_related_analysis_target({arguments})"
        )
    op.execute(
        """CREATE OR REPLACE FUNCTION app.freeze_processed_document() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'parsed document history is immutable'; END IF;
      IF (to_jsonb(OLD) - 'updated_at') IS DISTINCT FROM (to_jsonb(NEW) - 'updated_at') THEN
        RAISE EXCEPTION 'parsed text, structure and parser identity are immutable';
      END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER processed_documents_frozen BEFORE UPDATE OR DELETE ON processed_documents FOR EACH ROW EXECUTE FUNCTION app.freeze_processed_document()"
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION app.enforce_edge_target() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM evidence_nodes s, evidence_nodes t WHERE s.node_id=NEW.source_node_id AND t.node_id=NEW.target_node_id
        AND s.organization_id=NEW.organization_id AND t.organization_id=NEW.organization_id
        AND s.document_id=NEW.document_id AND t.document_id=NEW.document_id
        AND s.document_version_id=NEW.document_version_id AND t.document_version_id=NEW.document_version_id) THEN
        RAISE EXCEPTION 'evidence edge endpoints must share the analysis target';
      END IF;
      RETURN NEW;
    END $$"""
    )
    op.execute(
        "CREATE TRIGGER evidence_edges_version_boundary BEFORE INSERT OR UPDATE ON evidence_edges FOR EACH ROW EXECUTE FUNCTION app.enforce_edge_target()"
    )


def downgrade():
    op.execute("DROP TRIGGER processed_documents_frozen ON processed_documents")
    op.execute("DROP FUNCTION app.freeze_processed_document()")
    op.execute("DROP TRIGGER evidence_edges_version_boundary ON evidence_edges")
    op.execute("DROP FUNCTION app.enforce_edge_target()")
    for table in RELATIONS:
        op.execute(f"DROP TRIGGER {table}_related_target ON {table}")
    op.execute("DROP FUNCTION app.enforce_related_analysis_target()")
    for table in LINEAGE_TABLES:
        op.execute(f"DROP TRIGGER {table}_exact_target ON {table}")
    op.execute("DROP FUNCTION app.enforce_analysis_target()")
    for column in (
        "structure_json",
        "structure_fingerprint",
        "normalized_content_hash",
        "parser_version",
    ):
        op.drop_column("processed_documents", column)
    for table, columns in (
        ("citation_sources", ("document_id",)),
        (
            "detection_segments",
            ("organization_id", "document_id", "document_version_id"),
        ),
        ("evidence_edges", ("document_id", "document_version_id")),
        ("jobs", ("document_version_id",)),
    ):
        for column in columns:
            op.drop_index(f"ix_{table}_{column}", table_name=table)
            op.drop_constraint(f"fk_{table}_{column}_core", table, type_="foreignkey")
            op.drop_column(table, column)
    op.alter_column("jobs", "document_id", nullable=True)
