# AZAERON VERITY — RELEASE CERTIFICATION

**2026-09-30 — NOT PRODUCTION READY.** Current work closes the locally reproduced
container vulnerabilities and demonstrates a safe logical migration to a controlled
PostgreSQL 16 image. It does not approve models or certify production operation.

The backend and verification images contain Debian stable security OpenSSL
`3.5.7-1~deb13u3`, with actual package records and file hashes retained. A refreshed
Trivy database reports zero HIGH/CRITICAL findings. The PostgreSQL candidate uses
the pinned official 16.15 Alpine base and hash-verified pgvector 0.8.6 source, runs
non-root and excludes the unused vulnerable root privilege-switch utility.
Its scan and SBOM pass. No scanner threshold, CVE waiver, unstable package or fake
VEX was used. Initial failures are retained in the evidence directory.

The PostgreSQL image refuses implicit bootstrap and unrecognized PGDATA. Primary
Compose uses a distinct physical volume; existing data requires the
[logical migration procedure](../../infrastructure/postgres/MIGRATION.md).
No customer volume was switched, deleted or migrated automatically.

[Current evidence](evidence/commercial-production-20260930/) includes old-image
backup, new-volume restore, migrations, 34 PostgreSQL/RLS/storage tests, 292 backend
tests before subsequent dataset hardening, and a clean replay plus second recovery.
The representative fixture contains documents, versions, provenance, conversations,
messages, tool calls/results/events, an accepted receipt and a private voice profile.
Row hashes match after restore. One post-backup account erasure is replayed before
serving; seven objects are removed, the surviving version hash passes and the erased
account cannot log in. A second backup/restore preserves the tombstone and both
surviving object hashes. These are local measurements, not production RPO/RTO.
A failed replay contaminated by intentionally retained integration-test fixtures is
preserved and classified; the clean recovery was repeated in entirely new volumes.

Dataset hardening additionally requires derivative rights, permitted tasks and
source/author/document lineage, and rejects cross-split lexical near duplicates.
The narrow candidate-policy suite passes 21 tests. Exact-head hosted AMD64 run
[36755563468](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36755563468)
passed repository, image, security and derivative-mechanics checks for commit
`b0e279b74a8de4a4b1243c763ae8c22aa8c4e0a1`; the source-manifest hash and archived
results are in [hosted-b0e279](evidence/commercial-production-20260930/hosted-b0e279/).
Its training smoke used `TEST_ONLY` fixtures and does not approve a model or change
the production verdict. See [execution state](EXECUTION_STATE.md) for scope and
remaining gates.

[Rights and compute dossiers](evidence/commercial-production-20260930/RIGHTS_AND_COMPUTE.md)
cover three Writer candidates, two proposed independent baselines and specialist
initializations. No candidate is admitted: commercial review, verified payloads and
runtime evidence are missing; unsafe artifact forms are rejected. Four real dataset
sources were researched; none is approved. Noncommercial and unresolved mixed-source
rights are rejected. Original TEST_ONLY checkpoints remain smoke evidence only.
No new toy training, external AI inference, strong-baseline result, human rating or
production model approval was fabricated.

P0: no confirmed catastrophic issue in this exercised scope. P1: approved data,
capable production checkpoints, independent human/baseline evaluation, specialist
derivative/runtime implementation and private serving certification remain absent.
P2: production soak, GPU measurements, offsite recovery, locale-sensitive migration
validation and manual accessibility review remain unexecuted. Unexecuted is BLOCKED.

The five-product scope and existing architecture are retained. Required own API
routes exist; model-backed AI, Humaniser and calibrated Detector remain fail-closed.
Workspace similarity measures indexed overlap, and Documents retain immutable
versions. No merge or commercial launch is certified.

Historical reports: [previous certification](evidence/commercial-production-20260930/release-certification-before.md),
[prior hosted exact-head results](evidence/model-bakeoff-20260930/FINAL_REPORT.md).
