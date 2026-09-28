# Authorship consistency

Authorship consistency compares a target document with a historical writing
baseline. It is a statistical style comparison, not identity attribution.

## Quality gate

A baseline must contain at least three processed documents, 500 total words,
and at least 80 words per document. Target documents also require 80 words.
When the gate is not met, the result is `INSUFFICIENT_DATA` and no conclusion
is forced.

## Signals

The versioned feature extractor measures lexical distribution, function-word
distribution, sentence structure, conservative syntax proxies, punctuation,
vocabulary richness, discourse markers, and phrase patterns. Scalar features
use baseline-relative standardized deviation; distributions use deterministic
distance functions. These measurements are stored as auditable evidence.

## Separation of conclusions

Every result keeps three fields separate:

- `stylistic_deviation`: measured distance from the supplied baseline.
- `ai_writing_signal`: `NOT_TESTED` unless a separately validated AI-writing
  classifier is invoked. Style deviation is never converted into this field.
- `verdict`: `CONSISTENT`, `DEVIATION`, `STRONG_DEVIATION`, or
  `INSUFFICIENT_DATA` for the style comparison only.

The reported confidence is explicitly `data_adequacy_not_identity_probability`.
It is not the probability that a person authored the document.

## API

- `POST /api/v1/authorship/profiles` builds a tenant-scoped user baseline from
  owned, processed documents.
- `POST /api/v1/authorship/documents/{document_id}/analysis` runs a comparison
  with an optional baseline profile.
- `GET /api/v1/authorship/documents/{document_id}/analysis` returns the latest
  versioned result.

Each signal stores organization, document version, pipeline/model versions,
and an evidence node ID. No identity claim is emitted.
