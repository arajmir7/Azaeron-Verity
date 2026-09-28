# Architecture baseline

Preserve Next.js → same-origin FastAPI `/api/v1` → PostgreSQL with a non-owner
runtime role, Redis/Celery workers and private MinIO. Migrations use a separate
owner. Document versions identify every analysis input; new accepted objects are stored as private snapshots; legacy upload paths need
migration review. Telemetry is self-hosted and must contain metadata, never document text.

The intended writing inference boundary is API → authorized/quota-checked
orchestrator → private router → approved local model runtime. There is currently
no approved generative model or live inference server. Do not substitute hosted
AI, synthetic output, or label deterministic rules as model inference.

See the root architecture map for existing module locations. Kubernetes and GPU
scaling are not justified until model/runtime/hardware benchmarks exist.
