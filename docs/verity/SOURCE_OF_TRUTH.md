# Repository truth

Updated 2026-09-25. The [release certification](RELEASE_CERTIFICATION.md) is
the decision record; the [remediation ledger](REMEDIATION_STATE.md) preserves
R1–R15 results. The September 20 [execution state](EXECUTION_STATE.md) is
historical and does not supersede either.

- The stack is Next.js, Python 3.12/FastAPI, PostgreSQL 16 with forced tenant
  RLS, Redis/Celery, MinIO, and self-hosted telemetry. Docker Compose pins
  observed infrastructure digests. The review stack is isolated from the
  primary project and is not a production deployment.
- Implemented workflows include private verified uploads, immutable versions,
  analysis/evidence, deterministic editorial suggestions, selective acceptance,
  conflict-safe editor revisions, history restoration, scoped API keys,
  identity/SMTP/MFA controls, quota accounting, and authorized privacy erasure.
- The local MiniLM asset and deterministic rules are not approved generative or
  independent semantic models. No calibrated production detector, complete
  Voice product, private model deployment, or model/GPU measurement exists.
  Missing AI features are explicit and never fall back to an external AI API.
- The backend and frontend runtime image scans pass. Verification and several
  infrastructure image scans fail; see [image inventory](IMAGE_SECURITY.md).
  A local performance profile missed its save latency target, and the
  complete-object recovery drill failed closed on missing synthetic objects.
- Local tests do not establish hosted CI, production load/soak, full assistive
  technology conformance, backup RPO/RTO, production SMTP delivery, or model
  quality. No paid billing or general developer SDK is claimed.

Keep secrets, customer bytes, model weights, and generated private recovery
artifacts out of Git. A checked-in workflow or an old PASS log is not a
substitute for a fresh executed gate on the recorded source snapshot.
