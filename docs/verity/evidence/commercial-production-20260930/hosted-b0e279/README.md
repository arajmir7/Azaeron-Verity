# Hosted verification — b0e279b

GitHub Actions run [36755563468](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36755563468) completed successfully for commit `b0e279b74a8de4a4b1243c763ae8c22aa8c4e0a1` on 2026-09-30. The exact source-manifest SHA-256 was `eb4cf50a001ce83ae83764372805649f393de5becdb9975b6a9ad9443240a105`.

The repository job passed all 11 gates: formatting, lint, mypy, 298 backend/security/worker tests, 34 PostgreSQL/RLS/storage tests, frontend lint/build/typecheck, Compose validation, 30 live browser tests, and source stability. The Python dependency audits, npm audit, Bandit, source-secret scan, frontend SBOM, and all 12 image vulnerability scans plus 12 image SBOMs passed. The image vulnerability reports contain no findings.

The separate derivative-mechanics job passed hash-locked dependency install, full and LoRA smoke runs, and its isolated dependency audit. Those runs used `TEST_ONLY` synthetic fixtures (two optimizer steps each); the bakeoff has no winner, quality evidence is false, QLoRA is blocked without CUDA, and production approval is `NOT_APPROVED`. This is evidence that training mechanics execute, not evidence of useful or approved models.

`ci/` contains the exact hosted gate logs, source manifests, frontend and container SBOMs, Trivy JSON reports, and gate summaries. `secret-gate.json` records the hosted source scan. `derivative-mechanics-evidence/` contains the smoke result, bakeoff, manifests, and isolated audit. The original GitHub run remains the authoritative signed workflow record.
