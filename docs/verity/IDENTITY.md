# Identity security and delivery

Identity extends the existing cookie/session system. It does not require an external
identity provider or SaaS mail service. Current R6 execution is recorded in the
[remediation ledger](REMEDIATION_STATE.md); this document describes the contract.

## Email challenges

Authenticated users request verification at `/api/v1/auth/verification/request`.
The password-reset request endpoint returns the same message for existing and
unknown accounts. Both purposes use random 256-bit single-use challenges, store
only SHA-256 digests, enforce expiry, and rate-limit by a digest of the email address
as well as the authentication edge's per-IP limit. A newer challenge invalidates an
older challenge for the same purpose. Verification and reset tokens cannot substitute
for one another.

Verification expires after 60 minutes; password reset after 30 minutes. Completion
locks the account and token, records use, and writes an audit event. Password reset
invalidates all sessions and preserves any enabled MFA. Passwords cannot exceed
72 UTF-8 bytes, avoiding bcrypt's silent truncation boundary.

A token-bearing link lives in the email URL fragment. Fragments are not sent to the
HTTP server. The browser moves the token into component memory, removes the fragment,
and requires an explicit confirmation action. Reloading that page requires reopening
the email link. Tokens and setup/recovery secrets are not stored in browser storage.

## Self-controlled mail

Configure `EMAIL_ENABLED`, `EMAIL_PUBLIC_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`,
`SMTP_STARTTLS`, and optional SMTP username/password. Production requires a canonical
HTTPS origin, SMTP STARTTLS with certificate verification, and a dedicated
`IDENTITY_ENCRYPTION_KEY` in Fernet format. API and workers must use the same key.
Retain the key securely for authorized recovery; do not put it in the database or Git.
The development-only derived key is not accepted as a production substitute.

Requests commit an encrypted mail-outbox entry with the identity challenge. Celery
beat schedules delivery every 30 seconds to the worker's `identity` queue. The sender
locks pending records with `SKIP LOCKED`, retries failures with bounded backoff, and
clears encrypted payloads after sending or expiry. Error state contains a stable code,
not an SMTP exception, email body, or token. Monitor pending/failed/expired delivery;
a queued response does not guarantee arrival in an inbox.

SMTP cannot provide transactional exactly-once delivery with PostgreSQL. If a worker
crashes after SMTP accepts a message but before the transaction commits, the message
may be delivered again. The Message-ID stays stable and its link can be consumed only
once. Backups may retain old encrypted outbox records until retention expires.

For an isolated local sink, generate Compose with `--identity-mail`. This enables
the pinned Mailpit service and sender without publishing SMTP to the host. Its web
inbox is bound to localhost at `8025 + port offset`. The R6 review stack uses a
separate explicit inbox port. Mailpit is not a production outbound delivery service.

## TOTP and recovery

Enrollment requires the current password. A 160-bit random setup secret expires
in 10 minutes and is encrypted at rest. Confirmation uses the existing cryptography
library's RFC 6238 TOTP implementation: six digits, 30-second steps, and one step
of tolerated clock skew. An account row lock and persisted counter reject replay,
including concurrent attempts. There is a separate per-account MFA attempt limit.

Ten recovery codes, each with 128 random bits, are shown once. Only digests are
stored. Each code works once; replacing the set invalidates every previous code.
Enabling/disabling MFA revokes other sessions. Disabling or replacing recovery codes
requires the password and a current unused factor. A password-reset email alone
cannot disable MFA. Losing both the authenticator and recovery codes requires an
operator-reviewed recovery process; no bypass endpoint is exposed.

## Sessions

Access tokens carry their refresh-family identity. Authentication requires both a
valid access token/session epoch and a non-revoked, unexpired family record. A
workspace switch or refresh preserves the family. Revoking one family rejects its
access token on subsequent authentication, without signing out unrelated families.
There are at most 100 active sessions; admitting another retires the oldest active
records. Device descriptions are untrusted browser-supplied labels, not device proof.

- GET `/api/v1/auth/sessions` lists metadata, never raw tokens.
- DELETE `/api/v1/auth/sessions/{id}` revokes a session owned by the account.
- DELETE `/api/v1/auth/sessions/others` preserves the current session.
- Logout, password changes, and password reset invalidate all sessions.
- Refresh-token reuse retains the existing account-wide revocation behavior.

Session and MFA mutation endpoints reject API-key authentication. Expiry/revocation
blocks subsequent authentication; already admitted work may finish. Existing access
JWTs without a family must refresh or sign in again after this change.

## Migration rollback

The migration gate creates a new database on an explicitly isolated development
stack, migrates it from empty to 0029, seeds an account, downgrades to 0028, and
re-upgrades. Downgrade is rejected while any account has MFA enabled: removing
replay/recovery state would weaken authentication. Use an application rollback
that preserves the identity contract instead. This guard does not certify an
arbitrary older application build against a newer schema.
