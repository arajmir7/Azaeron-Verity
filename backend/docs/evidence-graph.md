# Canonical evidence graph

AZAERON VERITY exposes one tenant-scoped evidence graph for analysis results.
The graph is materialized from immutable document-version records and the
analysis modules; it is not a second source of truth for model output.

## Node vocabulary

`DOCUMENT`, `DOCUMENT_VERSION`, `CLAIM`, `CITATION`, `SOURCE`,
`SIMILARITY_MATCH`, `AI_SIGNAL`, `AUTHORSHIP_SIGNAL`, `PROVENANCE_EVENT`,
`FINDING`, and `REPORT`.

Every node has an organization, document, immutable document version, stable
entity identity, explanation, confidence, creation timestamp, and—when
applicable—an exact span, source, model, model version, and pipeline version.
Empty explanations, invalid spans, invalid confidence, and missing entity
identities are rejected.

## Edge vocabulary

`CONTAINS`, `VERSION_OF`, `CITES`, `SUPPORTED_BY`, `SIMILAR_TO`, `HAS_SIGNAL`,
`DERIVED_FROM`, and `GENERATED_FINDING`.

Edges require existing nodes from the same organization. Database foreign keys
prevent dangling endpoints; service validation prevents cross-tenant edges.
Findings require at least one `GENERATED_FINDING` parent. A graph is incomplete
when any finding lacks that parent edge.

## Traceability

The authenticated endpoint
`GET /api/v1/evidence/documents/{document_id}/graph` idempotently materializes
and returns the graph for the latest or requested document version. Consumers
can navigate:

`FINDING -> GENERATED_FINDING -> signal/evidence -> exact span -> source`

The response includes `schema_version`, version identity, completeness,
orphan-finding IDs, limitations, exact span text and offsets, explanations,
lineage, and model/pipeline metadata. Similarity is represented as overlap
evidence and is never labeled as plagiarism by this layer.

Historical evidence nodes and edges are append-only from the graph service;
repeated materialization reuses stable `(document_version, canonical_type,
entity_id)` identities and does not mutate prior analysis records.
