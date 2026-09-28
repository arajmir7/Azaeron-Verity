# AZAERON WRITE

AZAERON WRITE is a responsible editorial assistant. It applies conservative,
deterministic rules for grammar, clarity, concision, fluency, structure,
coherence, and formal tone when the source text supports a safe change.

Each accepted suggestion contains:

- `original`: exact source span
- `revision`: proposed replacement
- `change_reason`: observable reason for the change
- `document_version_id`: immutable version lineage
- `preserve_voice`: whether conservative voice preservation was requested
- `engine_version`: reproducibility metadata

The service stores suggestions in the tenant-scoped `aegis_edits` ledger and
records accept/reject decisions in the audit log. `GET /api/v1/aegiswrite/history/{document_id}`
returns the optional revision history for the authorized workspace.

All writing endpoints require authentication and use the dedicated 30-request
per-minute Redis-backed limiter in addition to the global API limiter. Requests
are tenant-checked against the document and immutable document version.

The public landing page never performs a rewrite. It routes users to the
authenticated `/write` workspace, where revisions are observable and
reviewable before an accept/reject decision is recorded.

This module deliberately has no detector-specific modes and does not implement
detector bypass, “0% AI,” stealth rewriting, Unicode tricks, character
obfuscation, watermark removal, or provenance concealment.
