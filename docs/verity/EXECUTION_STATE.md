# Execution state

Updated 2026-09-30. Active directive: autonomous commercial production, frozen five products. Do not merge or approve models without the required evidence.

- Review branch: `codex/private-agent-core-20260929`, head `5f7d525f93253e250b8e3e94be84d1122a9677a0`; draft PR #1. The IDE checkout is `main` with preserved pre-existing work; branch snapshots use a separate Git index. No reset/stash/merge.
- Latest hosted run `36684766301`: all 11 repository gates PASS (292 backend, 34 PostgreSQL/RLS/storage, 29 browser), derivative mechanics PASS, dependency/SAST/secret gates PASS, 12 image SBOMs PASS. Image gate FAIL: backend and verification each 2 HIGH OpenSSL; PostgreSQL 104 HIGH / 16 CRITICAL.
- Production models/datasets: zero approved. Existing checkpoints are TEST_ONLY. No external AI inference; production fails closed. Candidate training and admission mechanics already implemented; no more toy training except required CI.
- New local work: stable OpenSSL overlay and guarded official PostgreSQL 16 + pinned pgvector 0.8.6 images scan PASS with SBOMs. Old-image logical backup → fresh volume restore/migrations PASS; 34 PostgreSQL/RLS/storage + 292 pre-hardening backend tests PASS; clean erasure replay and second restore PASS. Failed contaminated test trial retained; all existing user volumes preserved. Primary Compose now requires explicit bootstrap and uses a distinct physical volume.
- Rights research: 11 exact-revision metadata dossiers and conservative M4/CUDA compute plans saved. Zero admissions/approved datasets. Unsafe/noncommercial/unknown-rights assets rejected. New lineage/derivative-rights/near-duplicate dataset checks pass 21 policy tests. Accountable rights and human quality reviewers requested asynchronously; no answer/approval yet.
- Next gate: snapshot source onto the draft review branch, exact-head hosted AMD64 repository/security/all-image/SBOM CI. Preserve security thresholds. Severity definitions: P0 confirmed catastrophic issue; P1 mandatory launch gap; P2 operational/certification deficiency; P3 minor.

Evidence: [current work](evidence/commercial-production-20260930/), [prior exact-head report](evidence/model-bakeoff-20260930/FINAL_REPORT.md), [historical execution ledger](evidence/commercial-production-20260930/execution-state-before.md).
