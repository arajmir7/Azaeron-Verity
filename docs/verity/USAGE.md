# Usage, quotas and operation identities

The PostgreSQL ledger records operation and request IDs, tenant, user/API credential,
task, outcome, quota status and observed model usage. No price or billing integration
is enabled. Limits count operations; they do not pretend to count model tokens when
no model ran. Token fields stay null for deterministic work and unavailable inference.
Each successful private model call records its exact model/revision, input/output token
counts and duration from the validated adapter response. A writer and verifier are
recorded separately within their parent operation.

## Admission and retries

A transaction-scoped PostgreSQL advisory lock serializes each tenant's reservations
and settlements. Monthly counters include both reserved and committed operations.
A reservation commits before synchronous execution; no usage lock spans an inference
call. Completion commits the result receipt and quota settlement before HTTP delivery.
All database dependencies use FastAPI function scope, so transaction finalization
finishes before sending any endpoint response. A regression injects commit failure
and verifies that the client receives failure and no account row survives.
Failures release reserved capacity. The database uniqueness key is tenant, task and
operation ID, and replay additionally requires matching payload, user and API key.
Changed payloads or credentials return 409. Expiry never authorizes re-execution.

Receipts are encrypted with an independent `USAGE_ENCRYPTION_KEY` (Fernet), retained
for 24 hours, and served only by the original operation endpoint to the authenticated
caller. The usage endpoint never returns receipt text or request fingerprints.
Production startup requires this key. Development derives a separate purpose-specific
key from its existing development secret. Changing the key requires preserving the
old key until pending receipts expire, or explicitly accepting unavailable replays;
failed decryption returns 503 and never reruns work.

`POST /api/v1/text/analyze`, `/text/verify` and `/text/refine` require an operation UUID.
Analysis exposes deterministic text counts and an indeterminate authorship result.
The absence of an approved calibrated detector remains explicit. Editorial endpoints
accept operation IDs; older callers get a deterministic identity scoped to the exact
payload and immutable version. A new intentional operation must use a new UUID.
The editor retains its operation ID after a network error and clears it after success.

Document upload IDs identify upload consumption. Processing identities derive from
immutable version and job type. Job creation reserves capacity in the document
transaction; successful worker completion commits it in the result transaction.
Final failure or cancellation releases it. Terminal redelivery cannot consume again.
Delivery before an API commit retries rather than abandoning a newly queued job.
The reconciliation worker releases expired synchronous leases, rejects automatic
re-execution, removes expired text receipts and reconciles expired job reservations.
Active worker transactions are skipped with `SKIP LOCKED`.

## Current server-owned policy

| Operation | Free / month | Provisioned paid tier / month |
| --- | ---: | ---: |
| Document upload | 20 | 200 |
| Document processing | 200 | 2,000 |
| Text analysis | 200 | 2,000 |
| Text verification | 200 | 2,000 |
| Generative refinement | 200 | 2,000 |
| Editorial suggestions | 200 | 2,000 |

At most four text operations can be reserved concurrently across a tenant's keys and
users. Monthly limits return 402; concurrency limits return 429 with Retry-After.
UTC calendar months define periods; reservations settle against their original month.
These are product admission limits, not evidence of production capacity or an offer
of paid service. Expired paid plans fall back to free limits. Existing file-size and
text-length limits also apply. Reads and metadata changes are rate-limited, not charged
as analysis. Model unavailability releases the reservation and is never billed.

## Privacy and retention

Document/account erasure removes associated operation rows, encrypted results, hashes
and personal attribution, and releases pending reservations. It preserves nonpersonal
aggregate consumption for a surviving workspace so erasure cannot reset quota.
Workspace erasure removes its counters as well. Historical document consumption is
seeded during migration; token counts and earlier inference usage are not fabricated.

`GET /api/v1/usage` requires a session or the `usage:read` API-key scope. It returns
current tenant totals and at most 100 recent operations belonging to the caller; an
API key sees only its own records. Workspace settings display the same totals.
Operations remain as retry tombstones until privacy erasure; no silent expiration
allows an old ID to become a new operation. Encrypted cached text expires after 24h.

Migration, concurrency, live worker, and browser evidence is recorded under
[R8](evidence/remediation/r8/). Final source-wide recertification is indexed in
[RELEASE_CERTIFICATION.md](RELEASE_CERTIFICATION.md).
