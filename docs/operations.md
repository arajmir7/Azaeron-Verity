# AZAERON Verity production operations

This runbook describes the controls shipped with the platform. Prometheus and
Jaeger are observability components, not evidence that a target has been met.
SLO compliance requires a real traffic window and retained measurements.

## Operational targets

These are initial service-level objectives, subject to review against measured
capacity. They are targets, not current claims:

| Service indicator | Target | Measurement |
| --- | ---: | --- |
| API availability | 99.5% monthly | `azaeron:api_availability:ratio5m` and monthly rollup |
| API latency | p95 < 750 ms, p99 < 2 s | `azaeron:api_latency:p95_5m`, `azaeron:api_latency:p99_5m` |
| Accepted analysis jobs completed or explicitly failed | 99% within 15 minutes | job duration, status, and dead-letter metrics |
| Terminal job retry rate | < 5% | `rate(azaeron_job_retries_total[1h])` compared with accepted jobs |
| Critical data loss | 0 | immutable document versions, fingerprints, and audit review |

Do not mark an SLO met until the Prometheus retention window contains the
required denominator and the report records exclusions and degraded periods.

## RPO and RTO

These are explicit targets and test boundaries, not claims that the local
Compose stack or a production deployment currently meets them.

| Recovery objective | Target | Current evidence |
| --- | ---: | --- |
| Committed PostgreSQL/MinIO data RPO | 0 for a durable, replicated production deployment | Backup/restore and replication have not been exercised in this gate; the production RPO is **UNKNOWN** until that drill is completed |
| In-flight analysis work RPO | At-least-once delivery; replay is allowed | Late acknowledgements, worker-loss rejection, idempotency lock, and dead-letter handling are implemented; loss/replay under a real outage needs a production-like drill |
| Dependency restart RTO | < 5 minutes | Local stop/start observations: PostgreSQL ~2 s, Redis ~2 s, MinIO ~6 s |
| Worker-loss detection and recovery RTO | < 5 minutes | Local SIGKILL probe: readiness failed after the heartbeat TTL (~35 s), then recovered after worker restart |
| Partial application deployment recovery RTO | < 15 minutes | Local backend stop/start probe restored readiness in ~5 s; rollback under a real deployment controller is not tested |

The failure gate verified that stop/start did not delete committed local data,
but it did not test backup restoration, replica promotion, disk failure, or
cross-region recovery. Therefore no durable-data RPO is approved yet. Record
the backup snapshot ID, restore timestamp, recovered record/fingerprint counts,
and measured RPO/RTO in the release evidence before changing UNKNOWN to a
measured value.

## First response

1. Confirm the incident with `/health/live`, `/health/ready`, Prometheus, and
   the Grafana dashboards. Keep the returned `X-Request-ID`,
   `X-Correlation-ID`, and `X-Trace-ID`.
2. Check the `AzaeronDependencyNotReady`, `AzaeronQueueBacklog`, and
   `AzaeronDeadLetterGrowth` alerts before changing application state.
3. Inspect the trace in Jaeger using the trace ID. Never paste document text,
   credentials, bearer tokens, or raw tenant identifiers into an incident
   channel.
4. Record start time, affected organization scope, observed metric values, and
   every mitigation.

## API latency or error spike

- Query request rate, 5xx rate, and p95/p99 by stable route.
- Compare DB query latency, pool checked-out, Redis health, and worker count.
- If the API is overloaded, keep liveness available, stop nonessential load,
  and scale the API/worker deployment within the declared resource limits.
- Do not disable authentication, tenant isolation, evidence lineage, or
  metrics authentication to recover traffic.

## Database or tenant-isolation incident

- Mark the service degraded and stop writes if cross-tenant access is suspected.
- Preserve the request/correlation IDs and database error class.
- Verify the runtime role is the non-owner `azaeron_app` role and that RLS is
  enabled/forced before restoring writes.
- Re-run the cross-tenant regression suite before reopening traffic.
- Historical document versions and analysis rows are append-only; do not mutate
  them as a repair shortcut.

## Queue backlog, worker failure, or dead letter

- Inspect `azaeron_queue_depth`, `azaeron_worker_count`, job duration, retries,
  and the dead-letter queue key configured by `DEAD_LETTER_QUEUE_KEY`.
- Verify Redis memory and connectivity, then inspect worker logs by task ID.
- Fix the underlying deterministic failure before replaying a dead-letter item.
- Replay only with the original organization/document/version identifiers and
  record the operator, timestamp, and outcome. The worker lock makes duplicate
  delivery safe, but it does not make a bad input safe.

## Storage or malicious-document incident

- Check storage operation latency/errors and the MinIO health endpoint.
- Quarantine the object key; do not download it to an analyst workstation.
- Preserve its SHA-256 fingerprint and processing error.
- Confirm page, text, archive expansion, and upload-size limits remain enabled.
- Re-run the document-processing security tests before restoring processing.

## Graceful deploy and rollback

- Drain ingress, wait for active requests and in-flight jobs, and observe the
  configured stop grace periods.
- Apply migrations before starting the new API/worker revision.
- Verify liveness, readiness, a real authenticated request, Prometheus scrape,
  and a trace export.
- Roll back the application image if error rate or latency breaches the target;
  do not roll back database migrations without an approved compatibility plan.

## Verification commands

```sh
docker compose config --quiet
docker compose ps
curl -fsS http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:16686/api/services
```

The local Compose stack exposes monitoring ports on loopback only. Production
must place these components behind the deployment's authenticated network and
set an external OTLP endpoint with TLS.

The scale-gate workload, measured before/after results, and optimization record
are maintained in [`docs/scale-gate.md`](scale-gate.md).
