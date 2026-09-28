import pytest

from app.core.database import Base


@pytest.mark.parametrize(
    "table_name",
    [
        "processed_documents",
        "document_chunks",
        "similarity_matches",
        "similarity_index_entries",
        "citations",
        "claims",
        "citation_references",
        "citation_sources",
        "citation_findings",
        "authorship_signals",
        "provenance_events",
        "provenance_reports",
        "provenance_exports",
        "integrity_reports",
        "detection_results",
        "evidence_nodes",
    ],
)
def test_analysis_outputs_require_shared_lineage_contract(table_name: str):
    table = Base.metadata.tables[table_name]
    for field in (
        "organization_id",
        "document_version_id",
        "pipeline_version",
        "created_at",
    ):
        assert field in table.c, f"{table_name} is missing {field}"
        assert (
            table.c[field].nullable is False
        ), f"{table_name}.{field} must fail closed"


def test_analysis_run_is_versioned_and_tenant_scoped():
    table = Base.metadata.tables["analysis_runs"]
    assert table.c["organization_id"].nullable is False
    assert table.c["document_id"].nullable is False
    assert table.c["document_version_id"].nullable is False
    assert table.c["pipeline_version"].nullable is False


def test_evidence_graph_nodes_and_edges_are_canonical_and_tenant_scoped():
    node_table = Base.metadata.tables["evidence_nodes"]
    edge_table = Base.metadata.tables["evidence_edges"]
    for field in (
        "organization_id",
        "document_id",
        "document_version_id",
        "canonical_type",
        "entity_id",
        "created_at",
    ):
        assert field in node_table.c
        assert node_table.c[field].nullable is False
    for field in (
        "organization_id",
        "source_node_id",
        "target_node_id",
        "edge_type",
        "created_at",
    ):
        assert field in edge_table.c
        assert edge_table.c[field].nullable is False


def test_aegiswrite_edits_are_tenant_and_version_scoped():
    table = Base.metadata.tables["aegis_edits"]
    for field in (
        "organization_id",
        "document_id",
        "document_version_id",
        "user_id",
        "original_text",
        "suggested_text",
        "explanation",
        "created_at",
    ):
        assert field in table.c
        assert table.c[field].nullable is False
