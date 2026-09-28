# Privacy and storage lifecycle

Status: implementation under R7 verification. This is the product's technical
retention policy, not a claim of legal compliance. Operators must document their
applicable retention obligations before deployment.

## Scope and authorization

`POST /api/v1/privacy/erasures` requires a browser/bearer session, the current
password, MFA when enabled, and the literal confirmation `ERASE`. API keys cannot
request erasure. A document owner or workspace owner/admin may erase a document;
only a workspace owner may erase that workspace. An account may erase itself.
Another tenant's identifiers never grant authority.

Account erasure removes owned documents, all versions and their derived analysis,
identity challenges/mail, sessions, API keys, memberships, authorship profiles,
personal audit records, and sole-member workspaces. Shared workspaces remain.
A sole owner of a workspace with other active members must transfer ownership or
explicitly erase the workspace first. Shared versions authored by the removed
account retain their content and lineage with null actor attribution. Writing
suggestions and derived evidence attributed to that account are removed. Names
inside independently owned shared document text are not automatically rewritten.

Document and workspace erasure remove related jobs, processing output, similarity
and detection results, citations, edits, evidence and provenance exports. Analysis
in other documents that quotes an erased similarity source is invalidated and
removed; its independently owned source document remains. Ordinary archive/delete
controls still archive a document; permanent erasure is an explicitly separate action.

## Durable execution

PostgreSQL validates scope, records the immutable erasure manifest, fences writes,
and hides affected document reads before asynchronous removal. Account sessions
and workspace API keys are revoked immediately as appropriate. Fixed
`SECURITY DEFINER` routines perform only the recorded operation; the runtime role
cannot write the erasure ledger. Caller-set session variables cannot bypass the
existing append-only triggers. New content still requires actor attribution.

The worker commits database erasure before removing storage objects, so a crash
retains enough information to resume. It aborts scoped incomplete multipart uploads, deletes every listed object version
and delete marker, then enumerates both interfaces again. Storage/listing/retention errors prevent
completion and are retried by the scheduled worker. `FAILED` means deletion is
unverified; it never means success. The database is checked again before completion.

The states are `REQUESTED → ERASING_OBJECTS → VERIFYING → COMPLETED`, with `FAILED`
available for retryable storage failures. Completion requires an eight-minute
grace period: presigned PUT/GET URLs last seven minutes, so an earlier browser
request cannot recreate staging content after the final verification. Tombstones
remain after completion and must accompany recovery. They contain UUIDs, storage
locators, scope, state and verification metadata, never customer document text,
passwords or email addresses.

The response displays a random receipt once. Its SHA-256 digest is stored. Supply
it in `X-Erasure-Receipt` to `GET /api/v1/privacy/erasures/{id}` after account removal.
The status response exposes no object keys or identity details. The UI keeps the
receipt in page memory, removes it from the URL fragment, and offers an explicit
download. Losing the receipt requires operator assistance; it is not recoverable
from the database. Signed-in requesters can also list their recent requests.

## Storage policy

The API principal can upload/read permitted namespaces and cannot delete objects.
Workers use independent `PRIVACY_MINIO_ACCESS_KEY` / `PRIVACY_MINIO_SECRET_KEY`
credentials with the scoped [maintenance policy](../../infrastructure/minio-maintenance-policy.json).
These credentials never enter the frontend. Production workers reject missing,
shared, or short maintenance credentials.

- Every hour, migrate at most 100 legacy `uploads/` version references. Read and
  verify the original SHA-256, write a private `versions/legacy/` snapshot, verify
  the copy, and atomically relocate matching version/document/job references.
  Changed legacy bytes fail closed; operators must recover the correct original
  from a trusted backup. An audit mapping preserves old/new keys and content hash.
- Referenced legacy originals remain compatible until migration succeeds.
  Unreferenced staging/private artifacts older than 24 hours are collected in
  bounded batches with durable cursors. The collector checks authoritative
  references under the same PostgreSQL object lock used by writers. It never
  blindly expires `versions/` or referenced legacy objects.
- Bucket lifecycle rules expire `temporary/` objects after one day. MinIO server
  settings expire abandoned multipart uploads after 24 hours, with an hourly
  cleanup interval. This runtime does not implement the S3 multipart lifecycle
  rule; erasure explicitly aborts matching uploads through a pinned SDK adapter. Existing operator rules are retained.
  Lifecycle execution is asynchronous in MinIO; its exact timing is not a deletion SLO.
- File parsing uses bounded in-memory input; no persistent customer temporary-file
  directory is introduced. Redis task envelopes retain identifiers, not document
  bodies; result records expire after one day. Operational logs need a deployment
  retention policy and must not contain document text or identity secrets.

## Backups and recovery

Erasure is not instantaneous deletion from existing backups. Target policy:
encrypted daily backups expire within 30 days; any required exception needs an
explicit operator policy. Keep the deletion ledger for at least the longest
backup/replica retention period plus recovery margin (target 37 days); the current
implementation retains tombstones indefinitely until an operator can prove that
all older recovery copies have expired. UUID/locator retention is deliberate and
must be reflected in the deployment's privacy notice.

Before activating a restored database or serving restored objects, apply the
latest independently retained tombstones, replay erasure against restored state,
and verify object absence. A restored `COMPLETED` status alone is insufficient:
the restore procedure must re-run deletion verification. Full recovery evidence
is a separate R12 gate; this document does not certify it.

Executed R7 evidence is in [evidence/remediation/r7](evidence/remediation/r7).

## Executed R7 evidence (2026-09-24)

The actual account erasure drill completed in 507.7 seconds with session revocation,
receipt rejection and verified object absence. The Celery maintenance worker migrated
45 legacy versions after verifying both byte fingerprints, rejected none, removed
45 old unreferenced objects and preserved 49 referenced objects. Active jobs now block
relocation; terminal worker redelivery does not reopen relocated objects. The 25
PostgreSQL/worker regression tests and fresh/rollback/re-upgrade migration drill passed.
See [remediation evidence](evidence/remediation/r7/). The earlier standalone retention
diagnostic omitted ORM registration and rejected 45 candidates; its result is superseded
by `retention-worker-final.log`, which executes the actual Celery task.
