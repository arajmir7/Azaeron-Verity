# API contract

Existing base: `/api/v1`. FastAPI publishes OpenAPI 3.1 at
`/api/openapi.json`. Auth, organizations, documents, jobs, detection, similarity,
citations, authorship, editorial suggestions, evidence and provenance routes exist.
Health endpoints currently live at `/health/live` and `/health/ready`.

Existing public UUIDs and tenant checks are preserved. Document uploads use
request/confirm and private signed URLs. Version append uses `/documents/{id}/versions`.
DELETE archives documents; it does not implement privacy erasure. The legacy editorial `/apply` endpoint records a decision only.
`POST /documents/{id}/revisions` persists a working draft or an authenticated
subset of suggestions. Supply `operation_id`, `base_version_id`, `text`, and
`edit_ids`. Reusing an operation ID with the same payload returns its original
version; a changed payload or stale parent returns 409. Suggestions must match
actor, tenant, document, version, and source hash. The server reconstructs the
candidate and verifies protected text.
`POST /documents/{id}/versions/{version}/restore` takes `operation_id` and
`base_version_id`, verifies stored bytes, and appends a revision with lineage.
Both operations require current membership and document mutation permission.

Workspace owners and administrators can create, list, rotate, and revoke scoped
API keys at `/api/v1/api-keys`. Credentials are displayed once, stored only as
digests, and denied when revoked, expired, or detached from active membership.
The supported public routes declare `x-api-key-scopes` in OpenAPI. Request and
quota accounting appears at `/api/v1/usage`; inference token counts remain
unavailable until an approved model actually executes. Rate-limited requests
return `429` with `Retry-After`. See [API_KEYS.md](API_KEYS.md) and
[USAGE.md](USAGE.md).

Authorized document, account, and organization erasure requests use
`POST /api/v1/privacy/erasures` with password, optional MFA, and explicit
confirmation; status is available to the requester or by display-once receipt.
The recovery drill still fails its complete-object audit, so privacy erasure is
reported as a limited capability, not a production certification.

The API remains incomplete as a general developer platform: error envelopes,
pagination, and idempotency are not uniform across every mutation route, and
no SDK or deprecation schedule is promised. Private inference protocols are
implementation details and are not part of the public OpenAPI contract.
