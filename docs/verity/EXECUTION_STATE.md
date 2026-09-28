# Execution ledger

Updated 2026-09-28. The verified application schema is `20260924_0035`. The
current remediation source is not yet committed; local `main` remains at the
repository's existing initial commit until the verified changes are published.
**NOT PRODUCTION READY.** See the [release certification](RELEASE_CERTIFICATION.md)
and [remediation ledger](REMEDIATION_STATE.md).

## Current evidence

- The final source-stable repository gate passed backend formatting, lint, typing,
  250 unit/security/worker/contract tests, actual PostgreSQL RLS integration,
  frontend lint/build/types, 25 browser tests and source-stability checks. Its
  source-manifest digest is
  `c07012081cb3d4e22519637f93f02cf4037fde5245ff9a967c863e840e207ffc`.
- Dependency audits report no known Python or npm findings. Bandit reports no
  application findings; the reviewed-secret gate reports zero unreviewed
  findings and 48 exact reviewed fingerprints.
- The R15 outage drill returned readiness 503 and then 200 for Redis, MinIO and
  PostgreSQL. Authenticated metrics, Prometheus scraping, 13 alert rules,
  dashboard provisioning, trace persistence after Jaeger restart, and private
  log checks pass in the isolated telemetry stack.
- The R15 local application profile completed 284 requests and 56 processing
  jobs with no unexpected HTTP responses. It fails the proposed latency budget:
  save p95 is 6.712 seconds and revision-conflict p95 is 1.560 seconds at
  concurrency 4. These are local samples, not production SLOs.
- The clean R15 disaster-recovery control exercise restored a 360 KB database
  dump and four object-store objects to private volumes. It replayed a completed
  post-snapshot account erasure, removed two target objects, retained and
  hash-verified one independent immutable version, verified runtime RLS, and
  reached API/frontend readiness while rejecting the erased login. Measured
  same-host timing does not establish deployment RPO/RTO.
- The final all-image scan covers 15 distinct images and exports 15 SBOMs.
  Backend, worker, beat, migration, frontend and Mailpit pass. Verification and
  eight infrastructure images still have HIGH/CRITICAL findings. Redis was
  updated to the scanned 7.4.11 digest, reducing its findings to 2 HIGH and no
  CRITICAL; the full image gate still fails.

## Release blockers

1. No approved licensed production writing model or independent semantic
   verifier, evaluation corpus, or private serving-hardware measurements.
2. The detector is not production-calibrated; fairness and out-of-distribution
   evidence remain unavailable. Voice is not implemented.
3. Eight infrastructure images and the CI verification image fail the current
   image scan. The Redis finding improvement does not clear this gate.
4. Proposed save/conflict latency budgets fail under the measured local profile;
   production load, soak and service-level objectives are unverified.
5. Complete permission/quota review, tenant privacy erasure and retention
   coverage, legacy object migration, production SMTP, MFA/device operations,
   telemetry operations, and full accessibility review remain incomplete.
6. Hosted CI, additional architecture builds, deployment configuration, and
   offsite/geographic disaster recovery have not been certified.

These include internal implementation and evidence gaps as well as external
model and hardware dependencies. The verdict is **NOT PRODUCTION READY**, not
“blocked only by an external dependency.”
