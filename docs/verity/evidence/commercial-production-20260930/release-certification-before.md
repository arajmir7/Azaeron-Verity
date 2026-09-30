# AZAERON VERITY — RELEASE CERTIFICATION

**2026-09-30 — NOT PRODUCTION READY.** The owned-model platform has executable training, evaluation, public API, private runtime and release-gate code. No production-approved Azaeron model is available. The [owned-model build report](OWN_MODEL_BUILD_REPORT.md) and [implementation/runbook](../../backend/docs/owned-model-platform.md) supersede earlier model-platform status statements.

The new training code produced four distinct original checkpoints from random initialization on program-generated **TEST_ONLY** numeric fixtures. Each has safe-tensor weights, a reproducible configuration, training manifest, hashes, tokenizer lineage, evaluation and model card. Independent seeded repeats on PyTorch 2.14 produce identical weights. These tiny models fail the quality/release gates and cannot be promoted; no production checkpoint, approved dataset, real benchmark result or commercial approval was invented. [Exact local paths and hashes](evidence/owned-model-platform-20260930/checkpoint-inventory.json).

The production registry is empty. Chat, Humaniser and detector inference fail closed if approved owned models are absent. Third-party Qwen/MiniLM files remain baselines. Unknown dataset rights block training. Separate model families, independent verification, immutable evidence binding and all eight release gates are enforced. Public document operations retain pinned versions, tenant access and erasure checks. Deterministic workspace overlap remains available with its stated limited coverage.

| Executed check | Result and scope |
| --- | --- |
| Backend contracts/security/workers | 277 tests PASS; final source recorded by the repository gate. |
| PostgreSQL/RLS/storage | 34 actual integration tests PASS. |
| Black, Ruff, mypy | PASS; 191 application modules type checked. |
| Frontend lint, build, TypeScript | PASS; all 29 browser tests and source stability PASS (11/11 repository gates). |
| Training/evaluation mechanics | Four families trained twice, 9 optimizer steps each, matching repeated checkpoint hashes. All four quality evaluations BLOCKED. |
| Training dependency audit | PyTorch 2.10 initially failed two advisories. Upgraded isolated environment and hashed lock to 2.14; final audit has no known findings. |
| SAST / reviewed secrets | Bandit zero findings; zero unreviewed secrets, existing 48 reviewed fingerprints preserved. |
| Current application images | Frontend PASS; backend FAIL: one HIGH OpenSSL finding. Both SBOMs PASS. |
| Prior hosted infrastructure scan | Grafana PASS at `9c730bb`; PostgreSQL remained 102 HIGH / 16 CRITICAL. That preceding scan does not certify this build or newer vulnerability databases. |

[Repository gate results](evidence/owned-model-platform-20260930/gates/results.json), [application image scans](evidence/owned-model-platform-20260930/application-images/results.json), [training dependency audit](evidence/owned-model-platform-20260930/training-dependency-audit-final.json), [Bandit](evidence/owned-model-platform-20260930/bandit.json), [secret gate](evidence/owned-model-platform-20260930/secret-gate.log).

The fresh backend scan identifies `CVE-2026-84782` in `libssl3t64 3.5.7-1~deb13u2`. Debian's tracker marks the current trixie/security package vulnerable and lists a fix in unstable `3.6.5-1`; no stable distribution upgrade or security waiver was fabricated. [Debian advisory state](https://security-tracker.debian.org/tracker/CVE-2026-84782). The API's production security gate remains FAIL.

The earlier core-platform load rerun passes 284 requests, zero HTTP errors, 56 completed jobs and all 25 unchanged latency cells. Clean-source recovery passes restore, post-backup erasure replay and survivor object/version hash verification. [Load budgets](evidence/core-intelligence-20260929/load-restarted/budgets.json), [recovery result](evidence/core-intelligence-20260929/recovery-clean/recovery-result.json). These are local non-model measurements from the preceding source, not production SLO, GPU, offsite recovery or model-quality evidence. Failed attempts remain retained. Recovery/smoke containers were stopped with their volumes preserved.

Release remains blocked by reviewed production data, useful trained checkpoints, independent blinded writer ratings, strong-baseline comparisons, approved private model/runtime deployment, production security/load/soak evidence, image vulnerabilities, offsite recovery and manual accessibility review. The native reference runtime has no certified KV/prefix cache or production batching implementation. Fine-tuning an approved third-party base is not implemented; any future result must be declared AZAERON_DERIVATIVE with proven lineage.

**Verdict: Model-platform engineering is implemented and tested within the linked scope. Azaeron's model family and production deployment are NOT APPROVED.** The [execution ledger](EXECUTION_STATE.md) preserves history; [previous certification](evidence/owned-model-platform-20260930/previous-release-certification.md) is historical.
