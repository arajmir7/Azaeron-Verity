# AZAERON Verity scale gate

This gate used synthetic, tenant-isolated documents against the running Docker
Compose stack. Synthetic inputs are appropriate for controlled load testing;
the results below are measurements from this local run, not production SLOs.

## Workload

The operator harness is [backend/scripts/scale_gate.py](../backend/scripts/scale_gate.py).
The clean comparison used:

- 3 small uploads (`BASE_TEXT * 60`)
- 1 large upload (`BASE_TEXT * 600`, approximately 75 KB)
- 4 concurrent uploads
- 8 concurrent analyses
- 12-document similarity corpus, 60 repeats per corpus document
- real presigned MinIO uploads, API confirmation, Celery processing, PostgreSQL
  indexing, similarity verification, and match retrieval

Percentiles are order statistics. The small and large upload samples are too
small for capacity commitments; the analysis samples are the useful signal.

## Before and after

| Workload | Samples | Before p50 / p95 / p99 | After p50 / p95 / p99 | Before throughput | After throughput |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small upload | 3 | 67.896 / 67.896 / 67.896 ms | 63.364 / 63.364 / 63.364 ms | 1.650/s | 2.229/s |
| Large upload | 1 | 62.191 / 62.191 / 62.191 ms | 57.220 / 57.220 / 57.220 ms | 16.053/s | 17.461/s |
| Concurrent upload | 4 | 318.165 / 328.387 / 328.387 ms | 208.436 / 210.857 / 210.857 ms | 11.557/s | 18.842/s |
| Concurrent analysis | 8 | 26.185 / 62.345 / 62.345 s | 17.598 / 42.678 / 42.678 s | 0.095/s | 0.124/s |
| Corpus analysis | 12 | 44.307 / 83.449 / 83.449 s | 30.655 / 65.281 / 65.281 s | 0.128/s | 0.159/s |
| Corpus target analysis | 1 | 9.032 / 9.032 / 9.032 s | 9.057 / 9.057 / 9.057 s | — | — |
| Match-result read | 1 | 45.593 ms | 65.625 ms | — | — |

Both runs had zero failed workload samples. The after run returned 100
similarity matches for the target, with the same bounded evidence-producing
pipeline. The two runs were sequential on a growing local database, so this is
directional verification rather than a statistically controlled A/B benchmark.

## Resource measurements

Docker resource sampling ran once per second during each gate.

| Container | Before CPU peak / memory peak | After CPU peak / memory peak |
| --- | ---: | ---: |
| API | 77.42% / 394.0 MiB | 94.99% / 374.4 MiB |
| Celery worker | 211.72% / 801.2 MiB | 188.46% / 721.6 MiB |
| PostgreSQL | 131.72% / 293.2 MiB | 78.06% / 302.8 MiB |
| Redis | 14.34% / 19.02 MiB | 0.91% / 19.11 MiB |
| MinIO | 8.29% / 115.5 MiB | 1.34% / 113.5 MiB |

The worker still saturates the configured two-process CPU allocation during
analysis. The database was the first measured shared bottleneck: peak CPU,
round trips, and queue wait tracked similarity indexing work. The clean run
observed a document queue peak of 10 and up to 18 PostgreSQL sessions, with a
maximum of 2 active sessions in the sampler.

MinIO container network I/O during the after run increased by approximately
0.37 MB inbound and 0.63 MB outbound over 43 one-second samples, or roughly
8.6 KB/s inbound and 14.7 KB/s outbound. This is storage-service network
throughput only; disk IOPS and physical disk throughput were not instrumented,
so no disk-throughput claim is made.

## Optimization applied

`SimilarityService._store_chunks` previously performed a per-chunk lookup,
per-chunk index delete, and full term rewrite on every delivery. It now:

1. fetches all chunks for one organization/document/version in one query;
2. retains unchanged active index rows on redelivery;
3. deletes changed/stale index rows in one bounded statement; and
4. batches changed term rows before flushing.

The optimization does not alter normalization, candidate limits, tenant
predicates, match classification, evidence links, lineage, or abstention
behavior. Stale chunks are marked inactive and their terms are removed.

## Verification

```sh
docker compose exec -T backend python scripts/scale_gate.py \
  --small-samples 3 --large-samples 1 --concurrent 4 --corpus-documents 12
```

The gate must be run with one-second Docker stats sampling and PostgreSQL
active-session/queue sampling retained with the JSON output. Do not promote
capacity targets from this local run; repeat with production-like hardware,
network, corpus distribution, traffic duration, and representative documents.

Security and evidence integrity were preserved: tenant-scoped queries remain
in place, the bounded candidate limit remains 200, verification remains capped
at 25 candidates, and the target match response remained evidence-linked.
