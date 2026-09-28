# Security boundary

Authenticate with server-validated cookies/bearer tokens; resolve membership for
every request. Client tenant IDs never grant access. Enforce explicit document
mutation permissions and PostgreSQL forced RLS as separate boundaries. SQLite
tests cannot certify RLS. Refresh-token replay revokes user sessions; access tokens also carry a server-checked session epoch.

Document/model text is untrusted data, never commands or authorization input.
Production must reject external AI configuration. Uploads need bounded parsing,
private storage and tenant-bound keys. Production secrets, TLS, metrics auth and
worker readiness are mandatory. Never record bodies, tokens or exception values
that can contain document text in logs or traces.

Known review gaps: production SMTP delivery, comprehensive permission and
ASVS review, complete backup/object-store recovery, and HIGH/CRITICAL findings
in the verification and infrastructure images. Local rate limits and privacy
erasure exist, but their deployment behavior is not a production guarantee.
No OWASP or security-level compliance certification is claimed.

Executed supply-chain checks are in the evidence directory. Runtime and test
Python audits, npm audit and Bandit pass on the remediated dependencies. The
source secret gate permits only exact reviewed fingerprints (synthetic test
values, explicit development defaults, public revision/enum values). This is
not a claim of complete secret absence. The latest distroless backend and
frontend scans pass, but the [all-image gate](IMAGE_SECURITY.md) fails. Model
artifacts have not been approved for production.

New upload snapshots and editor versions use server-owned `versions/` keys.
The app storage principal can read/write those keys; browser-signed PUT requests
are restricted to generated `uploads/` keys. Storage credentials remain server
side. Guarded orphan/staging cleanup and legacy-object migration are
implemented; the recovery audit exposed missing synthetic objects from earlier
test fixtures. Do not serve a restored database until its byte audit passes.
