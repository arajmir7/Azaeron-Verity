# Document intelligence core verification — September 13, 2026

**VERSION_INTEGRITY_GATE: PASS**

The current implementation makes immutable document versions and frozen parser
output authoritative for analysis. The implementation contract and extraction
limits are in [document-intelligence-core.md](../../../backend/docs/document-intelligence-core.md).
This gate validates version integrity; it makes no model-accuracy claim.

| Gate | Actual result | Evidence |
| --- | --- | --- |
| Backend suite | 130 passed, 0 skipped/failed; includes 14 PostgreSQL tests | `backend-postgres.log` |
| Backend lint | Ruff passed for app, tests and scripts | `backend-lint.log` |
| Backend typecheck | Mypy passed, 127 source files | `backend-typecheck.log` |
| Frontend typecheck | `npx tsc --noEmit`, exit 0 | `frontend-typecheck.log` |
| Frontend lint | `npm run lint`, exit 0 | `frontend-lint.log` |
| Production builds | Backend, migration, worker, beat and Next.js images built in both projects | `production-build.log`, `primary-build.log` |
| Browser suite | 16 passed, 0 skipped/failed | `browser-full.log` |
| Post-upgrade browser flow | 1 passed against the main local app | `browser-primary.log` |
| Fresh migration | All 24 migrations, then 0024 → 0023 → 0024, exit 0 | `fresh-migration-final.log` |
| Populated upgrade | Restored 0023 backup upgraded to 0024; historical digests unchanged | `populated-migration.log`, `historical-*.json` |
| Main local upgrade | 0024 applied, historical digests unchanged, services started | `primary-upgrade.log` |
| Runtime | API liveness/readiness HTTP 200; database, Redis, storage and worker ready; frontend HTTP 200 | `docker-health.json` |
| Running source | All 127 backend Python files match API and worker containers in both projects | `docker-health.json`, `source-manifest.json` |

The migration digest comparison covers 114 processed documents, 114 immutable
versions, 115 jobs, 114 detector results, 5,041 detector segments, 38,646 evidence
nodes, 76,684 edges, 9,899 citation findings, 8,900 similarity matches, 109
authorship signals, 112 analysis runs and the empty citation-source table. It
compares all pre-existing columns, in ID order, excluding only the newly added
columns. Existing text, segmentation and findings were not rewritten. All 114
old parser records received `legacy:document-processing-v2` / `LEGACY_TEXT_ONLY`
adapters with unavailable historical source/page mapping explicitly recorded.
Digests are MD5 change checks over complete JSON row values, not security or
provenance signatures; document and normalized-content identities use SHA-256.

`files-changed.json` lists 37 modified and 7 added implementation/documentation
files. Verification artifacts are additional files in this directory.
`before.json` is the initial application/test source snapshot; it did not cover
all documentation. `source-manifest.json` records the final source tree. The
original product contract and Similarity verification remain historical artifacts.

## Regression coverage

Nine focused document-core tests cover CRLF/Unicode exact source mapping,
paragraph and sentence boundaries including abbreviations/decimals, reference and
citation offsets, deterministic identities, DOCX heading/table order, actual PDF
physical pages/word locations, explicit page breaks, HTML tables/nested markup,
stored authorship boundaries, pending-version reads, cross-tenant/version denial,
worker argument validation, frozen parser reuse and version-specific Write history.
Two additional PostgreSQL tests cover raw SQL mutation/parent/edge rejection,
concurrent V1/V2 analysis in independent sessions, concurrent parse retries and
historical results after those operations.

The browser flow uses real signup, upload, storage and worker analysis. It checks
V1 and V2 across content, structure, detection, citations, authorship, similarity,
graph and report APIs, exact Unicode evidence offsets, job version IDs, unchanged
historical responses, UI switching through Review/Citations/Similarity/Graph,
version-preserving Write navigation and denial from another workspace.
`browser/` contains its final full-suite screenshots and video. Both screenshots
were visually inspected. Existing onboarding, persona, responsive navigation,
authorization and live Similarity tests also passed in the full suite.

## Repeat

From the repository root, prepare an isolated stack:

```sh
python3 backend/scripts/prepare_slice0_compose.py --project azaeron-document-core-gate --port-offset 300 --output /tmp/azaeron-document-core-compose.json
docker compose -f /tmp/azaeron-document-core-compose.json build backend migrate celery-worker celery-beat frontend
docker compose -f /tmp/azaeron-document-core-compose.json up -d --wait frontend backend celery-worker celery-beat
```

Run backend `pytest tests -q` inside that backend environment with
`POSTGRES_TEST_DATABASE_URL` set to its runtime `DATABASE_URL` and
`CORS_ORIGINS=http://localhost:3000` for the existing API fixtures. The logged final
run mounted current `backend` at `/app`. Run `ruff check app tests scripts` and
`mypy app` there. From `frontend`:

```sh
npx tsc --noEmit
npm run lint
RUN_LIVE_E2E=1 PLAYWRIGHT_BASE_URL=http://localhost:3300 npm test -- --workers=1
```

For migration replay, use an empty database on the isolated PostgreSQL instance
and point the migration service's `MIGRATION_DATABASE_URL` to it. For populated
verification, restore an owner-only backup into a separate isolated database,
record sorted historical row digests, upgrade, then compare the same columns.
Never run the destructive downgrade check against the primary database.

## Runtime and limits

The main local app remains running at http://localhost:3000 with API port 8000
and migration `20260913_0024`. The isolated project used ports 3300/8300/9300;
it is stopped after verification with its volumes retained. The main database
backup is outside the repository at
`/tmp/azaeron-before-document-core-20260913.dump`, mode 0600.
Services without configured Docker healthchecks are recorded as running, not
independently health-checked. The isolated core stack omitted telemetry services,
so its exporter logged unavailable-collector retries; primary telemetry services
remain running. Neither observation is represented as an analysis test failure.

Earlier failures are retained in `*-initial.log`, `browser-core-retry.log` and
`build-command-correction.log`: an initial parser argument-name collision,
fixtures that lacked mandatory versions, initial typing errors, ambiguous browser
locators, and a corrected Compose service-name typo. All final required gates
passed. The backend reports 124 existing dependency warnings (Pydantic protected
namespaces and JWT datetime deprecation); no warnings are counted as test passes.

No required version-integrity gate remains open. Legacy source geometry cannot
be recovered without changing historical extraction. OCR, DOCX physical layout,
semantic bibliography grouping and advanced table reconstruction remain outside
this delivery. Existing analysis signals retain their experimental/unavailable
states and make no detection, attribution or plagiarism guarantee.
