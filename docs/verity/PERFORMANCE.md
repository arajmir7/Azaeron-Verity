# Current application performance — 2026-09-30, after Docker restart

**PASS within this local scope:** [284 requests and 56 completed worker jobs](evidence/core-intelligence-20260929/load-restarted/profile.json), zero unexpected HTTP responses, and all 25 [unchanged latency budgets](evidence/core-intelligence-20260929/load-restarted/budgets.json) met. At concurrency eight, save p95 was **261.896 ms** and conflict p95 **135.083 ms**, against 1,000 ms limits. The run completed in about 52 seconds on Docker 29.8.1. The backend source is identical to the failed attempt below.

Older Verity test stacks were no longer running after Docker restarted. Only the current verification stack was started, including telemetry. This strongly supports host resource contention as a contributor to the earlier failures, while the small synthetic fixture cannot certify production capacity, soak, or behavior under sustained memory pressure. The original failures remain documented below. No latency target was changed.

## Earlier failed attempt on the contended host

# Current application performance — 2026-09-30

**FAIL.** The private-agent candidate's [local attempt](evidence/core-intelligence-20260929/load/budgets.json) recorded 284 requests on the shared Apple M4 / 7.75 GiB Linux ARM64 Docker VM. Docker resource sampling exceeded its 15-second timeout. Five revision saves returned HTTP 500; all 25 measured latency cells exceed the unchanged targets; the profiler did not establish completion of the worker backlog. No production capacity or soak result is available.

[VM pressure](evidence/core-intelligence-20260929/load/vm-pressure.txt) recorded memory `some avg60=76.84%` and `full avg60=43.75%`. Many other projects were running. Worker logs include processing timeouts and trace-export deadlines. This supports resource contention as a contributing factor, but does not isolate a source regression or establish a sole cause. Only this task's Grafana/Jaeger/Prometheus/collector were stopped after the sampler failure, at 264 samples. Other projects were untouched. The final 20 samples therefore follow that intervention; this entire attempt remains failed.

The [raw samples](evidence/core-intelligence-20260929/load/profile.samples.json), [resources](evidence/core-intelligence-20260929/load/resources.jsonl), [environment](evidence/core-intelligence-20260929/load/environment.json) and [attempt record](evidence/core-intelligence-20260929/load/attempt-status.json) are retained. All backend application sources match the current candidate; a later frontend ARIA role change does not alter this API workload. Historical passing profiles below cannot certify the expanded application or the current host state.

## Historical performance records

# Current application performance profile — 2026-09-29

The [final local profile](evidence/final-blocker-burndown/load-final/profile.json) sent 284 HTTP requests against eight synthetic documents (six 779-byte and two 7,691-byte inputs) and completed 56 real worker jobs. Its [unchanged proposed HTTP budgets](evidence/final-blocker-burndown/load-final/budgets.json) all pass. No unexpected HTTP status occurred; paired conflicting saves returned one success and one 409 as intended.

| Operation | Concurrency 1 p95 | Concurrency 4 p95 | Concurrency 8 p95 | Budget |
| --- | ---: | ---: | ---: | ---: |
| Revision save | 234.463 ms | 138.791 ms | 483.636 ms | 1,000 ms |
| Stale revision conflict | 99.826 ms | 206 ms | 195.784 ms | 1,000 ms |

The previous same-host baseline's save p95 was 6,712 ms and conflict p95 1,560 ms at concurrency 4. Investigation found long worker transactions holding parent-document locks, a privacy trigger requesting a stronger lock than necessary for a version append, a uniqueness constraint on mutable `storage_path` that changed PostgreSQL's row-lock mode, inconsistent usage/document lock order, and eager loading of unrelated version histories during similarity analysis. The current migration uses a partial unique index for non-null storage paths and a KEY SHARE document privacy fence. Authorized erasure still takes FOR UPDATE. The worker releases its document lock before long analysis; usage and document writes now follow one order, and source similarity loads only needed rows. [PostgreSQL concurrency tests](evidence/final-blocker-burndown/repository-final/postgres-rls.log) cover erasure exclusion, uniqueness and concurrent saves. See [PostgreSQL's row-level locking semantics](https://www.postgresql.org/docs/16/explicit-locking.html).

Intermediate profiles under `load-before`, `load-after`, `load-after-lock-order`, `load-lock-diagnostic`, `load-corrected-worker`, and `load-final-locks` are retained as investigation evidence. Some compared different worker images or failed to drain jobs, so only `load-final` is the current accepted profile. The local host was Apple M4/16 GiB with a Linux ARM64 Docker VM, not a representative production deployment. These small p95 samples do not establish capacity or production SLOs. Connection-pool wait, isolated RLS overhead, frontend waterfalls and model latency were not independently measured; the metrics token was absent for pool sampling. The previously proposed limits were not loosened.

## Historical profile (2026-09-28)

# Application performance evidence

This historical run is a reproducible **local application profile**, not a production capacity or
model-inference certification. Its then-final run is
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
published service budget; and no sustained connection-pool overflow. The 2026-09-28
local run met the read/admission targets but **failed the save/conflict target**.
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
