# Citation intelligence

Citation analysis stores an auditable chain:

`CLAIM -> CITATION -> REFERENCE -> SOURCE -> supporting evidence`

## Stored contract

- `claims` preserve the exact document span and version lineage.
- `citations` preserve the in-text span, raw citation, parsed key, support
  status, retrieval timestamp, and evidence ID.
- `citation_references` preserve the bibliography line and parsed title,
  authors, year, publisher, DOI, and URL.
- `citation_sources` preserve the source identity and only metadata actually
  received from a resolver. Retrieved payloads are hashed; retrieval status and
  timestamp are explicit.
- `citation_findings` link claim, citation, reference, source, support status,
  explanation, evidence payload, and evidence node.

## Finding types

The analyzer emits `MISSING_CITATION`, `DUPLICATE_REFERENCE`,
`BROKEN_REFERENCE`, `INCORRECT_METADATA`, `CITATION_REFERENCE_MISMATCH`,
`UNSUPPORTED_CLAIM`, and `WEAK_SOURCE_SUPPORT`, plus a
`SOURCE_SUPPORT_ASSESSMENT` for each linked citation.

Support is one of `SUPPORTED`, `PARTIALLY_SUPPORTED`, `NOT_SUPPORTED`, or
`UNVERIFIABLE`. `UNVERIFIABLE` is the fail-closed state when source content was
not retrieved or could not be assessed.

The default resolver queries Crossref only for validated DOI identifiers. It
does not fetch arbitrary URLs. A source is never said to support a claim from
title, DOI, URL, or publisher metadata alone. When a DOI response contains an
abstract, the active assessment records the actual retrieved excerpt and
payload hash; the assessment remains lexical evidence, not semantic
entailment or proof of factual truth.

The tenant-scoped API is:

`GET /api/v1/citations/documents/{document_id}/analysis`
