# Document intelligence core

Every persisted analysis targets one `(organization_id, document_id,
document_version_id)`. `Document` remains a mutable workspace listing record;
its current status, storage pointer and counters are not analysis input.
`DocumentVersion` identifies immutable source bytes by SHA-256 and storage key.
The existing monotonic DRAFT → REVISION → FINAL lifecycle remains available.

## Authoritative representation

`modules/processing/extraction.py` contains format adapters;
`modules/processing/structure.py` builds `normalized-document-v1` with parser
`document-structure-v1`. `DocumentProcessingService` stores its first successful
output per version with pipeline `document-processing-v4`. Retries return that
record after checking the supplied bytes against the version fingerprint.

Normalization changes CRLF/CR to LF only. All normalized offsets are zero-based,
end-exclusive Unicode code point indices, not JavaScript UTF-16 indices, original
file byte positions or invented PDF glyph offsets. A compact source map relates
normalized ranges to extracted source text. Each element includes exact text and
ranges; UUID5 identifiers include the tenant, document, version, parser, element
kind, range and text hash. The canonical structure JSON has a SHA-256 fingerprint,
and the normalized text has its own SHA-256 hash. Extraction dependency versions
are recorded. Never change parser behavior under an already released parser tag.

Stored collections are pages, headings, sections, paragraphs, sentences, tables
and cells, references, citations, source locations and source-map segments.
Citation spans link to their containing sentence when identifiable. Paragraphs
link to sections. Table cells carry source paths and row/column positions.

| Format | Preserved structure | Explicit limits |
| --- | --- | --- |
| TXT / Markdown | Text order, blank-line paragraphs, headings by deterministic rules, sentences, bibliography lines, citation spans, explicit form-feed pages | No physical pagination, table geometry or semantic Markdown table recognition. |
| DOCX | Body XML paragraph order, heading styles, table cells, explicit page breaks | Physical pagination unavailable without a layout engine. Headers, footers, floating boxes and tracked-change layout are not extracted; complex/merged/nested tables may lose layout fidelity. |
| PDF | Extracted reading order, physical page ranges/dimensions, detected tables, unique exact word locations with bounding boxes | No OCR. Ambiguous or line-wrapped cells have unavailable offsets. Multi-column reading order depends on pdfplumber; no invented geometry. |
| HTML | DOM order, headings, paragraphs and table cells with declared row/column spans | No rendered pagination/geometry. Nested table text is flattened inside its parent cell. |

Sentence boundaries, text headings, reference entries and numeric/author-year
citation recognition are conservative deterministic rules, not validated semantic
parsing. Bibliography extraction currently preserves one entry per line; wrapped
entries are not claimed to be correctly merged. Limitations are stored in the
representation alongside available mappings.

## Ownership and consumers

- `modules/documents/target.py`: resolve and authorize the exact target, and fetch
  its processed representation. Omitted read version means latest *version*, even
  if that version has no completed analysis. It never means latest available result.
- `modules/jobs` and `workers/tasks.py`: persist mandatory version identity,
  validate worker arguments/object keys, record parser/hash metadata in analysis
  runs, and update document-list counters only for the current version.
- Detection consumes stored paragraph/sentence spans; citations consume stored
  sentence/citation spans and reference boundaries. Similarity consumes frozen
  normalized text with exact source/target offsets; its index and exclusions are
  unchanged by this core work.
- Authorship uses stored paragraph/sentence boundaries and frozen profile feature
  snapshots with baseline version IDs and structure fingerprints. New runs use
  `authorship-consistency-v3`; statistical algorithms remain unchanged. A baseline
  with incompatible boundary policy causes abstention, never silent rebuilding.
- Evidence nodes and edge endpoints belong to the same analysis target. Similarity
  source nodes are target-scoped proxies with the compared source version in
  provenance metadata. Historical cross-document graph edges remain stored but
  are excluded from version graph reads.
- Report, Review, Citations, Sources, Authorship, Similarity and Graph carry a
  selected version through existing navigation. Write preserves an incoming
  version; its history defaults to that version or latest when unspecified.
  Editorial suggestions still refer to submitted editor text; their ranges are
  not falsely advertised as offsets in immutable parsed document text.

## APIs

`GET /api/v1/documents/{id}/structure?document_version_id={version}` returns the
stored structure, target triple, parser version, normalized content hash,
structure fingerprint and mapping state. `GET .../{id}/content` exposes the same
parser and content identity alongside text. Both return 409 for an unprocessed
selected version and 404 for inaccessible/mismatched document versions.

Detection, citation analysis, authorship analysis, similarity analysis/matches,
evidence graph, reports, download and writing history accept
`document_version_id`. Upload confirmation and revision creation enqueue a job
bound to the newly created version. The existing provenance timeline deliberately
lists version history; selected-version views filter its analysis events/runs.

## Database and upgrade

Migration `20260913_0024` adds job version identity, lineage columns for detection
segments, citation sources and evidence edges, and frozen parser fields. Target
triggers validate organization/document/version relationships on 22 tables;
related-record and edge triggers reject mismatched parents/endpoints. Parsed
records cannot be rewritten or deleted. Existing document-version immutability
and forced tenant RLS remain in force. Document locking before version locking
serializes concurrent creation/analysis for one document without cross-version
result contamination. No infrastructure or document-to-document scan is added.

Historical jobs are mapped using recorded input, uniquely identifiable analysis
or object references, or a sole document version. Ambiguous history stops the
transaction; the migration never assigns latest speculatively. Legacy parser
records receive a frozen `LEGACY_TEXT_ONLY` adapter. Existing text, segmentation,
findings and identifiers are retained; absent historical source/page mappings
remain unavailable. Parser upgrades apply to new versions, not historical parses.

The downgrade removes these constraints/columns. Run it only for an intentional
rollback with a backup: it discards normalized structure metadata. Fresh replay,
an empty downgrade/upgrade roundtrip and a populated legacy upgrade are recorded
in `docs/verification/document-intelligence/`.

## Verification

`backend/tests/test_document_intelligence.py` covers format boundaries, Unicode,
references/citations, pages, tables, deterministic identity, all-module V1/V2 API
isolation, pending versions, parser upgrades, worker tuples and writing history.
`tests/integration/test_postgres_rls.py` adds real PostgreSQL concurrent analysis,
parse retries, cross-tenant visibility and raw SQL mutation/lineage rejection.
`frontend/tests/document-intelligence-live.spec.ts` uploads and analyzes both
versions through the real worker, switches existing views, checks exact evidence
spans and frozen historical responses, and verifies workspace denial.

These gates validate version integrity and implemented extraction behavior. They
do not measure detector accuracy, semantic similarity recall or citation truth.
