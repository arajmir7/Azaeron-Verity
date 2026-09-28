# Execution ledger

## 2026-09-28 final blocker burn-down: B1 and B2 in progress

The pinned upstream Quay MinIO server and client manifests return HTTP 401 to
anonymous pulls, and the authenticated hosted run failed before tests. Both
images now build from checksum-verified archives of immutable upstream Git
commits using digest-pinned builder/runtime bases. Local Linux ARM64 builds,
Compose validation, isolated server health, and client bucket/policy setup
pass. [Source and smoke-test evidence](evidence/final-blocker-burndown/minio-source.json).
The [first hosted run](evidence/final-blocker-burndown/hosted-b1.json) built
these images, migrated the database, and executed the real suite: 250 backend
and 30 live PostgreSQL tests passed; 25/26 browser tests passed. Ruff could not
write its cache to a bind-mounted directory, and the browser telemetry test
found that CI had not started Jaeger. Verification now places Ruff's cache in
`/tmp`; CI starts Jaeger, the collector and Prometheus. The exact hosted rerun
remains pending. The archived community MinIO source is now compiled with a
patched, digest-pinned Go builder and explicit fixed module versions; server
and client vulnerability scans/SBOMs pass locally. New digest-pinned Redis,
Prometheus and OpenTelemetry Collector candidates also pass their scans;
Grafana, PostgreSQL, Jaeger and the verification image remain unresolved.
Release verdict remains **NOT PRODUCTION READY**.

Updated 2026-09-28. The verified application schema is `20260924_0035`. The
baseline remediation, registry, and first product-intake work reached
`origin/main` at `3c7fc43`.
The focused-product source snapshot passes all 11 repository gates and
the rebuilt frontend image scan/SBOM. Both read-only Quay secret names are
configured in GitHub Actions; [the authenticated hosted rerun](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36400101044/attempts/2)
logged in successfully but still received `unauthorized` for the pinned MinIO
image before migrations and tests. Repository access or a validated image
distribution remains necessary. The repository remains
**NOT PRODUCTION READY**. See the
[release certification](RELEASE_CERTIFICATION.md)
and [remediation ledger](REMEDIATION_STATE.md).

## 2026-09-28 focused product rebuild

- **Task:** make Home, Azaeron AI, AI Humaniser, AI Detector, Plagiarism
  Checker, and the Document Editor the clear customer paths while retaining
  document history and advanced evidence review.
- **Change:** the primary navigation now contains Home, the five product paths
  (the editor is reached through Documents), Documents, and History. Settings,
  Help, and Account are secondary. Home has direct actions and actual recent
  documents/reports; chat history is explicitly unavailable. Report, graph,
  sources, citations, authorship, and provenance remain reachable inside a
  document's collapsed Advanced Analysis menu. The existing immutable editor,
  experimental detector, and workspace-scoped similarity analysis are exposed
  through named product routes. Text intake returns to the chosen workflow.
  Azaeron AI fails closed because no approved private model is deployed.
- **Gate:** [final source-stable results](evidence/focused-product-20260928-release/results.json)
  pass 11/11 checks: 250 backend unit/security/worker/contract tests, 30 live
  PostgreSQL/RLS tests, 26 browser tests including live editor, identity,
  document and similarity workflows, formatting, lint, types, production build,
  and Compose validation. The source-manifest digest is
  `cd21ad56c500ea9cfefe35bcab8f73aa1fbff5a5041908e500f5afaca5b72d6f`.
  The [rebuilt frontend image scan and SBOM](evidence/focused-product-20260928-release/frontend-image/results.json)
  pass, with zero HIGH/CRITICAL findings. `npm audit` reports zero findings in
  the [current audit](evidence/focused-product-20260928-release/npm-audit.json).
  The reviewed-secret gate reports zero unreviewed findings.
- **Result:** the focused paths work in the isolated development stack. The
  detector remains uncalibrated and abstains; the Humaniser offers only
  deterministic editorial suggestions, not generative rewriting. The Document
  Editor still lacks server-backed autosave, rename, and complete selection
  actions. Chat persistence and private generation are not implemented. The
  browser checks do not establish full WCAG conformance or production load.
- **Blocker:** production release remains blocked by the unapproved private
  model/verifier and detector calibration, prior failing infrastructure image
  scans and save/conflict latency budgets, incomplete product and permission
  coverage, and hosted CI's unauthorized pinned MinIO pull. The new frontend
  image's clean scan does not clear the other image findings.

## Current evidence

- The previous product-intake gate passed backend formatting, lint,
  typing, 250 unit/security/worker/contract tests, 30 PostgreSQL integration
  tests, frontend lint/build/types, 25 browser tests and source stability. The
  live browser tests verified that pasted text survives the private intake path
  as exact processed content and that a selected editorial focus reaches the
  refinement API. Its source-manifest digest is
  `934a1d4f375e516a44e9604368dba124cef215fc26ffb6f4e2825bd6f921c3ff`.
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
