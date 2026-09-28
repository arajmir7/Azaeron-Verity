# Decisions

## ADR-001 — Preserve the existing platform (2026-09-19)

Keep FastAPI/SQLAlchemy/PostgreSQL/Celery/Next.js. Existing tenant isolation,
immutable analysis inputs and test coverage make a framework rewrite unjustified.

## ADR-002 — Fail closed without a production model

Do not choose or approve an open-weight model without licensing and measured
quality evidence. Deterministic editing remains explicitly labelled. Missing
model/hardware evidence blocks inference certification, never enables hosted AI.

## ADR-003 — Isolate verification

The checkout has no Git metadata and its original storage port conflicts with
another service. Record source hashes and use separate databases/volumes/ports
for destructive or migration verification. Do not reset existing customer data.

## ADR-004 — Separate runtime, verification and experimental ML (2026-09-20)

Application import inventory found no spaCy, NLTK, PyPDF2, Markdown, simhash,
Crossref client or BibTeX usage. Remove unused packages and the unpinned spaCy
model download. Keep existing textstat 0.7.4 with bundled Pyphen dictionaries
(no runtime corpus downloads). Move optional local embedding dependencies out
of the default runtime and test tooling into a verification build target.
Production inference remains unavailable, not silently replaced by a hosted API.
Use hashed transitive Python locks for Python 3.12 Linux arm64 (the verified host);
other platforms require their own verified resolution/build. Use PyJWT for HS256
sessions; asymmetric JOSE algorithms were unused. Pin supported container base
manifests; Next standalone output carries only traced runtime dependencies.

Upgrade decisions use retrieved PyPI metadata in evidence/package-candidates.json,
[FastAPI release notes](https://fastapi.tiangolo.com/release-notes/),
[PyJWT changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html), and
[Next standalone output documentation](https://nextjs.org/docs/app/api-reference/config/next-config-js/output).
Passing builds, regression tests and fresh scans are required before promoting these changes.

## ADR-005 — Explicit accepted revisions and browser recovery (2026-09-20)

Refinement produces suggestions. The editor selects suggestions locally; explicit
acceptance reconstructs and validates the chosen changes on the server, then
appends a UTF-8 text version under a server-only object namespace. Original
uploads and historical versions remain available. Restoration appends a new
version; it never rewrites history. A row lock, expected parent and per-document
operation identity prevent concurrent overwrites and duplicate accepted versions.
PostgreSQL freezes operation identities. A failed queue publication rolls back
the database transaction; unreferenced private objects still need retention cleanup.

Draft recovery uses sessionStorage scoped to user/workspace/document, with a
24-hour expiry checked at recovery. Explicit sign-out clears these drafts;
authentication expiry retains them for the same user's subsequent sign-in.
There is no automatic upload or overwrite of accepted work. Closing the tab or
browser storage eviction can remove recovery data; a downloadable text draft
and clear save/recovery status are provided. This is not an offline PWA.

## ADR-006 — Freeze verified upload bytes before acceptance (2026-09-20)

Presigned PUT URLs remain valid until expiry. Uploaded staging objects therefore
cannot be used as immutable version objects. Confirmation now persists verified
bytes under `versions/uploads/.../<sha256>.<extension>`, a namespace that upload
signing never addresses. Jobs, downloads and new version rows reference this
snapshot. Confirmation retries find the existing version before consulting
mutable staging, including after later revisions. A live regression overwrites
the original staging object and checks the accepted download and retry identity.
Historical paths are not silently rewritten; existing pre-change version objects
remain legacy storage and need an audited migration/backup review before production.

## ADR-007 — Minimal Debian 13 runtime, unchanged Python ABI (2026-09-20)

R1 requires removal of unused vulnerable operating-system packages, not scanner
exceptions. Build CPython 3.12 and hash-locked wheels in the official Debian 13
Python image, then assemble required native libraries onto matching distroless
Debian 13. Retain package records for copied native libraries so scanning remains
complete. Exclude shells, package managers, test tools, development headers and
unused interactive/SQLite extensions. SQLite remains in the separate verification
image. Worker startup and health checks use direct executables/Python, without
shell pipelines. Production remains non-root. Both base manifests are digest-pinned.

Upstream references: [official Python image manifest](https://github.com/docker-library/official-images/blob/master/library/python)
and [distroless supported images](https://github.com/GoogleContainerTools/distroless).
Promotion requires a clean build, final-filesystem vulnerability scan, native
PDF/DOCX/crypto/CA/timezone checks, actual worker readiness and the regression suite.

## ADR-008 — Approved private inference contracts (2026-09-20)

Introduce a registry/router/gateway boundary without selecting a production model.
Approvals require immutable model/tokenizer revisions, complete artifact hashes,
license/commercial-use review, evaluation digest and a pinned runtime image. Only
explicit approved task routes execute. The private transport uses verified mutual
TLS, internal addresses, no proxy inheritance, no redirects, bounded context/output,
concurrency limits and cancellation propagation. Runtime output is data, never tools
or executable instructions. Generated manifests deny runtime egress and public ingress,
verify read-only artifacts before boot, and disable remote code and content logging.
No model download or fabricated output is a deployment substitute. GPU execution and
runtime-image compatibility remain blocked until exact approved artifacts are supplied.

## ADR 009 — Scoped API credentials (2026-09-20)

Keep browser sessions and durable membership checks. Add a closed public-route
allowlist for `X-API-Key`; keys cannot administer accounts or credentials. A key
contains tenant/key locators plus 256 random bits; SHA-256 of the complete credential
is stored and compared in constant time. Locators only bootstrap tenant-scoped
credential lookup. Explicit invalid keys never fall back to cookies. Legacy key
records are disabled by credential version. Session-authenticated owners/admins
manage keys; rotation locks tenant then key, revokes and creates atomically. A
revocation blocks subsequent authentication; already admitted work may finish.
Redis limits aggregate by key and tenant; production fails closed on Redis failure.
Usage attribution uses the authenticated key ID; atomic accounting is completed in R8.
The UI keeps displayed secrets only in component memory and never browser storage.

## ADR 010 — Identity challenges and individual sessions (2026-09-21)

Extend existing authentication instead of replacing it. Random single-use email
challenges store SHA-256 digests. An encrypted transactional mail outbox separates
request responses from SMTP availability, supports retries, and clears delivered or
expired payloads. Delivery can repeat after a crash; the same Message-ID and single-use
challenge make repeats harmless. Production uses self-controlled SMTP with STARTTLS
and a dedicated Fernet key. Development can use the pinned, private local Mailpit sink.
Links put tokens in fragments; the browser removes them before submitting an explicit
confirmation, avoiding access-log/referrer leakage and automatic preview consumption.

Use cryptography's RFC 6238 TOTP primitive with encrypted 160-bit secrets, a 30-second
step, bounded clock skew, and a row-locked replay counter. Recovery codes have 128
random bits each and store only digests; use and replacement are single-use state
transitions. Password reset preserves MFA. MFA state changes require password/factor
proof and revoke other sessions. Access JWTs now carry the existing refresh-family
identity, which must have an active record at authentication. Individual family
revocation therefore also rejects its access tokens; at most 100 active sessions are
retained. Older access JWTs without a family must refresh or sign in again.

## ADR-011 — Durable erasure and reference-aware storage retention (2026-09-24)

Normal document/version/provenance mutation remains immutable. A PostgreSQL
security-definer workflow validates the requester, captures the erasure scope,
fences further writes, and removes only its recorded database graph. The runtime
role cannot write the ledger or activate its immutable-trigger exception by setting
a session variable. Account erasure preserves independently owned shared content
with redacted actor attribution and removes the erased account's suggestions and
attributed derivative evidence. New records still require attribution.

Database removal commits before object cleanup so crashes retain the object
manifest. A worker-only MinIO principal removes all matching object versions,
delete markers and incomplete multipart uploads, then verifies absence. Completion
waits eight minutes for seven-minute presigned URLs to expire. Failed storage
verification remains retryable and cannot become a successful erasure. Receipt
secrets are displayed once and stored only as digests. Tombstones must accompany
restores and outlive every backup containing erased data.

Legacy upload references move only after original and copied bytes match the
recorded fingerprint. Retention checks database references under the same object
lock used by writers; durable scan cursors prevent early live objects from starving
later orphans. This MinIO release rejects S3 multipart-expiration lifecycle rules,
so configure its native stale-upload expiry and explicitly abort multipart data
for scoped erasure. The pinned SDK adapter has a real MinIO regression test.
See [privacy policy and operations](PRIVACY.md) and the
[MinIO configuration source](https://github.com/minio/minio/blob/RELEASE.2025-09-07T16-13-09Z/docs/config/README.md).

## ADR-012 — Operation reservations and encrypted retry receipts (2026-09-24)

Preserve the existing PostgreSQL/Celery architecture. Add monthly tenant counters
and operation identities with atomic reserve/commit/release transitions. Hold a
transaction advisory lock only during admission and settlement, allowing bounded
concurrent inference without holding the tenant lock across runtime calls. Worker
usage commits with its result; delivery and HTTP retries reuse immutable identities.
No external billing provider or inferred token accounting is introduced.

Lost HTTP responses replay encrypted, authenticated receipts for 24 hours. Expired or
unknown outcomes retain their identity and never run again automatically. This avoids
claiming exactly-once model execution across a runtime/process crash. Private inference
can have performed work before a crash; such an unknown outcome is released without
billing and requires a new intentional operation. A separate Fernet key protects cached
text. Privacy erasure deletes receipts and personal metadata while preserving surviving
tenants' nonpersonal consumed-quota totals. See [usage contract](USAGE.md).
