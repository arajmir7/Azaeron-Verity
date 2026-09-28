# Application performance evidence

This is a reproducible **local application profile**, not a production capacity or
model-inference certification. The final current-source run is
[`load-final/profile.json`](evidence/final-production-certification/load-final/profile.json),
with its [platform snapshot](evidence/final-production-certification/load-final/environment.json),
[HTTP samples](evidence/final-production-certification/load-final/profile.samples.json),
and [container resource samples](evidence/final-production-certification/load-final/resources.jsonl).
Run it with `python3 scripts/verity_load_gate.py --compose
<isolated-compose.json> --output <new-evidence-directory>` against an
isolated development Compose project. The harness creates a new synthetic user and
eight documents, sends actual HTTP requests, writes objects to MinIO, and waits
for real PostgreSQL/Celery processing. It never invokes an unavailable model.

## Observed run, 2026-09-28

Apple M4, 16 GiB macOS 27 host; Docker Engine 29.8.0 Linux arm64 VM with 10 CPUs
and 7.75 GiB memory. API and worker limits were 2 CPU/2 GiB and 2 CPU/4 GiB.
Six initial texts were about 0.75 KiB and two about 7.5 KiB. The run sent 284
measured HTTP requests across concurrency 1, 4, and 8, created 56 processing
jobs, and finished in 136 seconds. Every job reached `completed`. There were
zero unexpected HTTP statuses. Paired stale revision saves produced exactly one
200 and one 409. At concurrency 8, four of twelve simultaneous deterministic
text analysis calls returned the documented 429 active-operation limit. Those
429s are policy responses, not service errors; they are shown in the raw data.

| Operation | Concurrency 1 p95 | Concurrency 4 p95 | Concurrency 8 p95 | Largest response |
| --- | ---: | ---: | ---: | ---: |
| Document read | 19 ms | 169 ms | 31 ms | 626 B |
| Document list, page size 5 | 6 ms | 22 ms | 38 ms | 3.2 KiB |
| Version history | 13 ms | 40 ms | 48 ms | 18.9 KiB |
| API-key document read | 7 ms | 29 ms | 116 ms | 626 B |
| Deterministic text analysis | 17 ms | 71 ms | 96 ms | 364 B |
| Document revision save | 852 ms | **6,712 ms** | 954 ms | 845 B |
| Concurrent revision conflict | 29 ms | **1,560 ms** | **1,477 ms** | 846 B |
| Job creation by upload confirmation | 199 ms | — | — | 599 B |
| Job list polling | 14 ms | 36 ms | 42 ms | 18.5 KiB |

The p95 and p99 are nearest-rank statistics on only 8–12 requests per cell.
They expose failures and lock contention; they cannot predict production tail
latency. The maximum sampled PostgreSQL connection count was 12, active count 6,
and lock waiters 4. The API pool reached 5 checked-out connections, with zero
overflow against a size of 10. The processing queue reached 32 pending jobs.
Sampled peak CPU was 65% for the API, 201% for the two-CPU worker, and 145% for
PostgreSQL; peak memory was 149 MiB, 1,079 MiB, and 452 MiB respectively. These
are point-in-time Docker samples, not integrated utilization. Redis and MinIO
peaked at 6%/16 MiB and 9%/183 MiB.

The high save/conflict tail occurs when a long document-analysis transaction holds a
privacy write-fence lock on that document while the editor tries to append a
revision. The 6.7-second sample is a real 200 response, not a timeout. Reducing
this lock lifetime safely requires a transaction redesign that preserves erasure
fences and immutable lineage; this remains a **release performance gap**.

The earlier runs in `r10/baseline`, `r10/optimized`, and `r10/verified` are
retained as failure evidence. They uncovered tenant-row contention, reciprocal
similarity foreign-key deadlocks, and API-key issuance contention. The corrected
source has real PostgreSQL lock regressions in
[`key-worker-lock-postgres-fixed.log`](evidence/remediation/r10/key-worker-lock-postgres-fixed.log)
and `postgres-locks.log`; the successful run above exercised all three fixes.
Materialization also uses an invocation-local evidence cache, avoiding the
previous lookup per node/edge; bounded-query and replay tests cover this change.

## Release budgets and limits

The following are **proposed release targets**, set after measuring the local
baseline. They are not an achieved production SLO. At concurrency 8 on a
representative approved deployment and dataset: p95 document read/list/history,
API-key read, analysis admission, and job polling ≤250 ms; p95 revision save and
conflict response ≤1,000 ms; p95 upload confirmation ≤500 ms; zero unexpected
5xx/timeout responses; every admitted job reaches a terminal state within its
published service budget; and no sustained connection-pool overflow. The current
local run meets the read/admission targets but **fails the save/conflict target**.
Production load, soak, tenant mix, retention growth, and SLOs are unverified.

The current timeline endpoint still returns every version, analysis run, and
provenance event for a document. Its 18.9 KiB maximum in this small fixture is
not a bound. This requires paged history and export-streaming design before a
large-history workload can be certified. Document and audit lists do use
database-side filtered totals and bounded pages. Existing indexes cover the
document, version, job, and provenance foreign keys used here; this eight-document
fixture is too small to prove index sufficiency or rule out future Redis hotspots.

No licensed production writing or detector model, evaluation corpus, or private
serving hardware was available. Model cold/warm/concurrent inference, GPU
utilization, tokens per second, and model tail latency remain **BLOCKED**.
