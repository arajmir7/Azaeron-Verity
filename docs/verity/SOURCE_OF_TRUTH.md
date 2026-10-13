# Repository truth

Updated 2026-10-11. The six [engineering specifications](specs/01-PRD.md)
define product acceptance, technical boundaries, journeys, design, schema and
implementation governance; [traceability](specs/traceability.json) connects
requirements to executable evidence. Current behavior is determined by source,
the running [OpenAPI capture](evidence/spec-driven-20261011/openapi.json),
[PostgreSQL catalog](evidence/spec-driven-20261011/schema-catalog.json) and
executed tests. The [release certification](RELEASE_CERTIFICATION.md) remains
the decision record; its older results do not certify later commits. The
[execution ledger](EXECUTION_STATE.md) retains chronological evidence and the
[remediation ledger](REMEDIATION_STATE.md) preserves earlier R1–R15 results.

- The stack is Next.js, Python 3.12/FastAPI, PostgreSQL 16 with forced tenant
  RLS, Redis/Celery, MinIO, and self-hosted telemetry. Docker Compose pins
  observed infrastructure digests. The review stack is isolated from the
  primary project and is not a production deployment.
- Implemented workflows include private verified uploads, immutable versions,
  analysis/evidence, deterministic editorial suggestions, selective acceptance,
  conflict-safe editor revisions, history restoration, scoped API keys,
  identity/SMTP/MFA controls, quota accounting, and authorized privacy erasure.
- The local Qwen3-4B MLX adapter is a working **DEV_ONLY third-party preview**.
  It serves local chat, stream, rewriting, summary and document Q&A with
  UNVERIFIED output; it is not an Azaeron-trained or approved model. The
  production model route registry is empty. Independent Verifier, calibrated
  Detector, approved Embed, rights-cleared production data and commercial
  model deployment remain blocked. No external AI inference fallback exists.
- The latest prior exact-commit workflow passed repository gates but failed
  frontend dependency audit (five development-chain HIGH findings); four
  infrastructure image families retained 28 HIGH findings. See the
  [2026-10-10 run](https://github.com/arajmir7/Azaeron-Verity/actions/runs/38078425983)
  and [image inventory](IMAGE_SECURITY.md). Older performance/recovery failures
  in this ledger are historical; later local fixes do not certify production.
- Local tests do not establish hosted CI, production load/soak, full assistive
  technology conformance, backup RPO/RTO, production SMTP delivery, or model
  quality. No paid billing or general developer SDK is claimed.

Keep secrets, customer bytes, model weights, and generated private recovery
artifacts out of Git. A checked-in workflow or an old PASS log is not a
substitute for a fresh executed gate on the recorded source snapshot.
