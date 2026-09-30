# Execution ledger

## 2026-09-29: executor recovery and isolated candidate verification

The failing command runner was caused by a misspelled workspace path. The
actual repository is `/Users/ajmiraribam/Projects/azaeron_verity`; HEAD at
recovery was `69fc08d`. The pre-existing diff and untracked-file list were
saved under `/tmp/azaeron_unverified_recovery.patch` and
`/tmp/azaeron_untracked_recovery.txt` before further edits. Existing project
volumes and user-owned untracked evidence remain in place.

The isolated `verity-recover-0929` stack builds and runs the candidate backend,
verification, Jaeger and Grafana images. [All 11 repository gates](evidence/recovery-20260929/gates/results.json)
pass, including 251 unit/security/worker tests, 30 actual PostgreSQL/RLS tests
and 27 browser tests. The [full 15-image scan and SBOM inventory](evidence/recovery-20260929/images/results.json)
passes for 13 vulnerability scans and all 15 SBOMs. Grafana retains 12 HIGH
findings; the unchanged Debian PostgreSQL image retains 102 HIGH and 16
CRITICAL findings. No suppression was added. A disposable same-family Debian
PostgreSQL update candidate still has 99 HIGH and 16 CRITICAL findings, so no
data-layer image switch was made. Grafana's Jaeger v3 datasource health and
trace query pass, and a Jaeger trace survives restart ([smoke result](evidence/recovery-20260929/runtime-smoke.json)).

This candidate is **uncommitted and not production ready**. The required image
gate is red; no exact-commit hosted CI has tested it, and no push has occurred.

## 2026-09-29: hosted image-gate infrastructure correction

[Hosted run 36510870667](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36510870667)
at commit `73fb563` passed all 11 repository gates (251 backend, 30 real
PostgreSQL and 27 browser tests), dependency audits, Bandit and the source
secret gate. It then failed in image scanning: Linux container access to a
0700 host temporary directory was denied, followed by runner disk exhaustion
while saving a later image. The partial scanner exit codes are infrastructure
**ERRORS**, not vulnerability classifications. [Archived hosted results](evidence/final-blocker-burndown/hosted-73fb563/).

The scanner now makes only its ephemeral archive path readable to the isolated
container, captures JSON and CycloneDX output through stdout without a writable
repository mount, and distinguishes invalid reports from actual CVE failures.
The hosted workflow reclaims Docker build cache before pulling and scanning the
remaining images. Local smoke scans exercise both a clean image and one with
expected findings. The corrected scanner then completed all 15 local images
and 15 SBOMs with zero infrastructure errors; the same four image families
retain 411 HIGH / 20 CRITICAL findings. [Results](evidence/final-blocker-burndown/all-images-ci-scan-fix/results.json).
An exact-source hosted rerun remains required; these findings are still
release-blocking.

## 2026-09-29: editor, save latency, stale review build and recertification

**Source manifest:** `f366106d1773e91f7006d5c62e808503b5a2cce17896600eb5948b6cbee333e1`.
The [final local repository gate](evidence/final-blocker-burndown/repository-ci-scan-fix-final/results.json)
passes all 11 checks: 251 backend tests, 30 real PostgreSQL/RLS tests, 27 browser
tests, formatting, lint, types, production build, Compose and source stability.
Schema head is `20260928_0036`.

- **Screenshot fixed:** port 4900 was serving the previous four-workflow frontend.
  It now serves the existing five-product UI and current editor/backend. A private
  database backup preceded migration; all 11 accounts, 11 documents and 19 versions
  were preserved. [Runtime evidence](evidence/final-blocker-burndown/runtime-update.json),
  [visual capture](evidence/final-blocker-burndown/dashboard-4900.png) (synthetic API fixtures).
- **B1:** hosted run [36431472782](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36431472782)
  executed and passed all 11 repository gates at `33f1205`; it then failed when
  the source secret scan treated Git's `FETCH_HEAD` SHA as a secret. `.git/` is
  now excluded from the source scan; source files remain scanned and the local
  result is zero unreviewed findings. The new source still requires its own hosted
  run; the prior run is not certification of this manifest.
- **B2:** all 15 image identities scanned and all SBOMs generated. Eleven pass;
  Grafana, Jaeger, PostgreSQL and verification retain 411 HIGH / 20 CRITICAL
  findings. [Inventory and results](evidence/final-blocker-burndown/all-images-ci-scan-fix/results.json),
  [per-finding classification](evidence/final-blocker-burndown/all-images/classification.json).
  Reachability is unresolved; no finding is suppressed or waived.
- **B3:** debounced server saves, explicit save status, rename with stale-title
  rejection, undo/redo across saves, Unicode-correct selection suggestions and
  archive are implemented. Ordinary save retries survive a lost response and tab
  reload. Create/open, selective acceptance, version history, restore, download,
  offline recovery and conflict preservation pass live tests. Generative Humanise
  and Expand remain unavailable. Archive preserves history; permanent erasure is
  the separate privacy workflow.
- **B4:** privacy document fences now take KEY SHARE, while authorized erasure
  retains explicit FOR UPDATE. A partial unique index preserves storage-path
  uniqueness without treating the mutable path as a referenced key. Worker status
  writes no longer hold a document write lock across analysis; save and settlement
  use consistent usage-before-document ordering. Source similarity queries avoid
  eager loading unrelated document histories. Concurrency, uniqueness, erasure
  exclusion and migration upgrade/downgrade tests pass. The final profile completes
  284 requests and 56 jobs. Concurrency-8 p95 save **483.636 ms**, conflict **195.784 ms**;
  all unchanged proposed HTTP budgets pass. [Profile](evidence/final-blocker-burndown/load-final/profile.json),
  [budgets](evidence/final-blocker-burndown/load-final/budgets.json). Production
  capacity, isolated RLS cost and connection-pool wait remain unmeasured.
- **B5–B7:** the private registry/gateway and deterministic protected-text controls
  remain in place; no approved model/runtime or licensed calibration corpus exists.
  Inference-dependent tests remain blocked. Chat persistence/streaming/product
  lifecycle are still internal gaps. No external AI API or fake response was added.
- **B8:** 27 viewport checks and nine route-level axe checks pass, covering the five
  product paths, home, history and settings; keyboard navigation/focus restoration
  and reduced motion pass. Actual screen-reader speech and browser zoom remain
  unverified. [Structured result](evidence/final-blocker-burndown/accessibility/structured-review.json).
- **B9:** fresh recovery restores PostgreSQL and four MinIO objects, replays one
  post-backup erasure, removes two target objects, verifies one surviving immutable
  version and its provenance, and reaches readiness while rejecting erased login.
  Active restore/replay took **18.718 seconds** on this host. One Docker CLI polling
  timeout was retried with the same erasure identity; the grace period was retained.
  [Recovery result](evidence/final-blocker-burndown/recovery/recovery-result.json),
  [provenance comparison](evidence/final-blocker-burndown/recovery/provenance.json).
  Offsite recovery, versioned buckets and production RPO/RTO remain unverified.

**Next boundary:** require the pushed source's hosted result, remediate the four
remaining image families, finish core private-chat infrastructure and deployment
validation, obtain approved model/hardware/calibration assets, and complete human
accessibility and production recovery/load reviews. Internal blockers remain.
**Verdict: NOT PRODUCTION READY.**

Earlier evidence and failed experiments remain below and in the evidence directory;
they are not substituted for the final source-stable local gate.

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
