# AZAERON Verity failure gate

This report records the failure-injection work completed against the local
Docker Compose deployment. A PASS here means the stated probe passed in this
environment; it is not a production availability or durability claim.

## Results

| Scenario | Detection and user impact | Recovery/data/retry/observability evidence | Status |
| --- | --- | --- | --- |
| PostgreSQL stopped | `/health/ready` returned 503 while `/health/live` remained 200; database-backed requests are unavailable | PostgreSQL restart restored readiness in ~2 s; no volume mutation was performed; readiness identified the database failure | PASS — local probe |
| Redis stopped | Readiness returned 503; basic API traffic remained available through the configured rate-limit fallback | Redis restart restored readiness in ~2 s; queue publication has bounded retries and fails closed with 503 rather than acknowledging an unqueued job; logs/metrics expose the dependency failure | PASS — local probe + regression test |
| MinIO stopped | Readiness returned 503 with a storage timeout; liveness remained available | MinIO restart restored readiness in ~6 s; storage failure stayed isolated from liveness; storage health latency was reported | PASS — local probe |
| Worker SIGKILL | Readiness changed to 503 after the heartbeat TTL (~35 s); accepted jobs can be delayed while no worker is healthy | Worker restart restored readiness; late ack/reject-on-loss settings and heartbeat metrics are enabled; no data was deleted | PASS — local probe |
| Worker timeout | A real Celery task on `document_processing` returned `SoftTimeLimitExceeded` under a 1 s soft/2 s hard limit | The probe task produced no document mutation; timeout settings and failure ack policy were verified; full production workload retry under timeout remains a separate load test | PASS — timeout probe |
| Duplicate job | Two concurrent deliveries used the same job key; one ran and the other was suppressed | Distributed lock returned one owner and one duplicate no-op; structured duplicate-delivery logging was observed | PASS — live probe |
| Corrupt document | Invalid PDF extraction raised a controlled processing error before persistence | Regression test confirms no processed content is written; error is observable and fail-closed | PASS — regression test |
| Oversized document | Processing limit rejected extracted text before database write | Regression test confirms the configured text limit is enforced; no fabricated analysis result is emitted | PASS — regression test |
| Expired session | Expired access token returned 401 | Auth regression test verifies rejection; no protected data is returned | PASS — regression test |
| Revoked session | Refresh after logout returned 401 | Refresh-token revocation regression test verifies rejection | PASS — regression test |
| Failed migration | Migration container pointed at an invalid PostgreSQL port and exited non-zero with `ConnectionRefusedError` | Existing stack remained intact and readiness was rechecked after the probe; no migration was applied. SQL-level failed-migration rollback and backup restore were not tested | PASS — connection-failure probe; SQL rollback incomplete |
| Partial deployment | Backend was stopped while the frontend stayed reachable with HTTP 200; backend liveness was unavailable | Backend restart restored readiness in ~5 s; frontend remained a degraded shell, not a claim of end-to-end functionality | PASS — local probe |

## Recovery boundaries

- The probes intentionally used service stop/restart and a bad migration
  connection; they did not simulate disk corruption, network partitions,
  replica promotion, a real deployment controller, or a backup restore.
- Queue publication retries are bounded. If Redis remains unavailable, the API
  fails closed and the caller must retry confirmation; it does not claim that a
  task was queued.
- Celery processing is at-least-once. Timeouts and worker loss can cause a
  redelivery. The job lock and immutable document-version identifiers protect
  against duplicate processing, but they do not guarantee recovery of an
  external dependency or an uncommitted result.
- No RPO is claimed for durable data until a backup/restore drill records
  before/after fingerprints and timestamps. See `docs/operations.md`.

## Reproduction outline

The local probes were run with service-scoped Compose operations:

```sh
docker compose stop postgres redis minio
docker compose kill -s SIGKILL celery-worker
docker compose stop backend
docker compose start postgres redis minio celery-worker backend
```

The application regression suite is the authoritative check for malformed and
oversized documents, sessions, queue publication, and Celery failure policy.
Expected failure injections must exit non-zero where noted; that non-zero exit
is the detection signal, not a release failure by itself.
