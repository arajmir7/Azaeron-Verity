# Evidence-first report

AZAERON VERITY exposes the authenticated primary report at:

`GET /api/v1/reports/documents/{document_id}?document_version_id={version_id}`

The response is an evidence view over the canonical graph, not a new model or
a fabricated aggregate score. It always identifies the analyzed immutable
document version and returns these independent dimensions:

`ORIGINALITY`, `SIMILARITY`, `AI-WRITING SIGNALS`, `AUTHORSHIP CONSISTENCY`,
`CITATION INTEGRITY`, `SOURCE QUALITY`, and `PROVENANCE`.

## Availability states

- `PRODUCTION`: lineage or infrastructure evidence is implemented and verified
  for the stated scope.
- `EXPERIMENTAL`: evidence is present, but the capability is not approved as a
  validated production classifier.
- `INSUFFICIENT_EVIDENCE`: no qualifying evidence was recorded, or the analysis
  abstained. Confidence is returned as `null`.

Confidence is never presented as an objective authorship or plagiarism truth.
Experimental confidence is explicitly marked `review-only`; the report does
not produce a single AI percentage conclusion.

## Traceability

Each report evidence item preserves its canonical node identity, explanation,
optional exact span and offsets, and linked source, claim, and citation IDs.
The service follows only evidence-bearing `GENERATED_FINDING`, `SUPPORTED_BY`,
and `CITES` relationships, allowing a reviewer to navigate from a finding to
its text span and onward to source/citation/claim evidence without traversing
unrelated document containment edges.

The UI renders exact sentence/paragraph spans when they are available. Missing
spans are reported as unavailable rather than inferred. Similarity remains
overlap evidence and is never converted into a plagiarism determination.
