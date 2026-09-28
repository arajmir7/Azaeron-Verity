# Self-hosted observability

R9 evidence covers the isolated development deployment. It does **not** establish
production SLO compliance, production retention capacity, or model/GPU health.

A browser upload now produces one trace across FastAPI, SQLAlchemy, MinIO and the
Celery consumer. Request, trace, job, operation and release IDs link the work.
Request/correlation headers accept UUIDs; invalid values are replaced. The worker
propagates only W3C trace context and the UUID request ID, without baggage.
`RELEASE_ID` identifies the deployed source/artifact; set it to an immutable release
identifier in deployment. Sampling is configurable with `OTEL_TRACE_SAMPLE_RATIO`
(0–1), with parent sampling preserved. The correlation exercise uses 100% sampling.

## Data boundaries

- HTTP spans use registered route templates; unmatched requests have one fixed
  label. Raw URLs, query strings, cookies and authorization headers are excluded.
- Database spans contain the SQL operation class and database type, without SQL,
  parameters or result data. Error spans omit exception messages and stack events.
- Storage spans contain the HTTP operation only, without object names or content.
- Private inference spans contain task and operation identity. Model runtime/GPU
  measurements remain blocked until approved deployment assets exist.
- Browser reports accept only an event UUID, closed error category and closed page
  category. They never accept an Error object, message, stack, arbitrary URL or
  document. Reports require an authenticated session, use CSRF protection, are
  limited to 10/user/minute and are client-throttled to one per 10 seconds.
  Anonymous browser failures still show recovery UI but are not ingested.
- Render boundaries focus the recovery heading and offer a tested retry action.
  Global error/rejection listeners use the same restricted report path.
- API access logging is disabled to prevent raw URL logging. Structured application
  logs retain operational IDs and reviewed metadata. Telemetry identifiers can
  still be sensitive: restrict operator access and retention accordingly.

## Processes and collection

The API exposes `/metrics`, protected by `METRICS_TOKEN` whenever configured and
always in production. Prometheus reads the matching token from `METRICS_TOKEN_FILE`;
the checked-in empty `infrastructure/metrics-token.development` is for local use
without a token. Production startup rejects a missing/short application token.
Never store a production token in the development file.

Start Celery with `python -m app.workers.entrypoint` followed by its worker flags.
The entrypoint creates a container-local multiprocess metrics directory before
importing the client library. An internal HTTP exporter listens on port 9100;
this port is not published. Counters/histograms survive prefork child recycling.
Live gauges are removed on child shutdown and pruned after an ungraceful process
exit. Container restart resets its counters; Prometheus `rate`/`increase` handle
resets. Do not share that metrics directory between worker containers.

Worker OTLP exporters initialize after fork. Every registered task has outcome and
duration metrics. Document processing also has active/retry/dead-letter metrics.
Heartbeats include the actual consumed queues, including identity maintenance.
Queue depths sum the Redis transport's configured default priority buckets;
Redis failure reports an unknown depth rather than a false zero. Active dependency
probes cover the database, storage and all required worker queues.

Prometheus scrapes the API and worker separately. The collector forwards OTLP to
Jaeger, whose local Badger store survives container restart in `jaeger_data`.
Prometheus defaults to 15-day retention; configure retention and storage capacity
for deployment. Jaeger Badger is a local/staging topology, not a distributed
production storage certification. Back up telemetry separately from product data.
Grafana provisions the metrics/traces sources and the 13-panel operations dashboard.
Anonymous analytics, update checks and plugin preinstallation are disabled.

Collector and worker telemetry ports remain inside the trusted private network.
Bind dashboards to loopback or place them behind operator authentication/TLS.
Set a unique Grafana administrator credential on first deployment; changing its
environment value does not rotate an already initialized administrator password.

## Alerts and evidence

`infrastructure/prometheus-rules.yml` defines API error/latency, missing scrape,
dependency/queue, worker/dead-letter, database, storage, authorization, admission,
frontend and inference alerts. The existing 99.5% availability, 750ms latency and
queue thresholds are provisional alert settings. They are not measured SLOs or
production capacity claims. The availability calculation now handles low request
rates correctly. Notification routing to an operator remains deployment-specific;
no email/Slack/pager message is sent by the local exercise.

Executed evidence under [remediation/r9](evidence/remediation/r9):

| Check | Evidence |
| --- | --- |
| 247 backend regressions | [unit-full.log](evidence/remediation/r9/unit-full.log) |
| Final trace/privacy contracts | [trace-regressions.log](evidence/remediation/r9/trace-regressions.log) |
| Real browser upload and render-boundary retry | [browser-final.log](evidence/remediation/r9/browser-final.log) |
| Connected API/DB/storage/job trace with content canary | [browser-correlation.json](evidence/remediation/r9/browser-correlation.json) |
| Two live scrape targets, 13 alerts, dashboard, persistence and log privacy | [operational.json](evidence/remediation/r9/operational.json) |
| 120 actual task deliveries across both prefork children recycling | [worker-recycle.log](evidence/remediation/r9/worker-recycle.log) |

Reproduce after building and starting the isolated app and telemetry services:

```sh
cd frontend
RUN_LIVE_E2E=1 RUN_OBSERVABILITY_E2E=1 \
  PLAYWRIGHT_BASE_URL=http://localhost:4700 \
  npm test -- tests/observability-live.spec.ts tests/error-boundary.spec.ts --workers=1
cd ..
python3 scripts/verity_observability_gate.py \
  --compose .verity-local/identity-compose.json \
  --output docs/verity/evidence/remediation/r9
docker compose -f .verity-local/identity-compose.json run --rm --no-deps \
  verification python -m scripts.telemetry_drill
```

Implementation references: [OpenTelemetry Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/),
[Prometheus multiprocess collection](https://prometheus.github.io/client_python/multiprocess/),
and [Celery lifecycle signals](https://docs.celeryq.dev/en/stable/userguide/signals.html).
The [R13 image review](IMAGE_SECURITY.md) covers telemetry containers and fails
on their HIGH/CRITICAL findings. Final source and runtime checks are indexed in
[RELEASE_CERTIFICATION.md](RELEASE_CERTIFICATION.md).
