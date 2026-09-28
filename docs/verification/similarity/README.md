# Similarity workflow verification

The Similarity workflow is implemented and available in the existing local app
at `http://localhost:3000`: open a document, then **Review similarity**. Older
versions without a workflow snapshot offer **Analyze similarity**. The existing
local database was backed up before migration `20260913_0023`; its data and
volumes were retained. Backend application hashes match the running container.

| Gate | Final result | Evidence |
| --- | --- | --- |
| Backend suite | 119 passed, no skips; includes 12 real PostgreSQL RLS tests | `backend-tests.log` |
| Browser suite | 15 passed, no skips; includes the new live similarity flow | `frontend-tests.log` |
| Backend static checks | Ruff passed; mypy passed across 124 files | `backend-lint.log`, `backend-typecheck.log` |
| Frontend static checks | TypeScript and ESLint passed | `frontend-typecheck.log`, `frontend-lint.log` |
| Production builds | Backend, worker, scheduler, migration and frontend images built | `local-build.log`, `final-isolated-build.log` |
| Local runtime | Healthy services, migration 0023, forced snapshot RLS and composite term index | `local-runtime.json`, `running-source-check.json` |

The new live browser flow uses actual registration/login, workspace creation,
presigned MinIO uploads, Celery processing and PostgreSQL. Two uploaded sources
exercise all four quotation/citation groups, duplicate-overlap coverage, source
ranking, exact source/target offsets, exclusions and reload reproducibility,
independent match/source pagination, a second target version, historical snapshot
stability and denial from another workspace. `browser/` contains the final
screenshots and recording. Both screenshots were visually inspected.

Focused backend tests also cover Unicode offsets, repeated target passages,
missing corpus versus zero overlap, all-word exclusions, canonical exclusion
fingerprints, source additions after a frozen result, bounded search disclosure,
idempotent analysis and read-only reviewer denial. The full suite reports 124
existing dependency deprecation warnings; these are not skipped or failed tests.

The isolated verification stack used project `azaeron-similarity-gate`, API port
8200, browser port 3200 and MinIO port 9200. It is stopped after verification with
its volumes retained. The original local app remains running on port 3000.

## Repeat the gates

Prepare/start the isolated stack using `backend/scripts/prepare_slice0_compose.py`
with `--project azaeron-similarity-gate --port-offset 200 --output
/tmp/azaeron-similarity-compose.json`, then build and start its frontend, backend,
Celery worker and beat services with Docker Compose. Its dependency graph runs
the migration service before the API and worker.

Run backend `pytest tests -q` in the backend container with
`POSTGRES_TEST_DATABASE_URL` set to that isolated runtime `DATABASE_URL`.
The final run mounted the current `backend` directory at `/app` and set
`CORS_ORIGINS=http://localhost:3000` for existing API test fixtures.

From `frontend`, run:

```sh
RUN_LIVE_E2E=1 PLAYWRIGHT_BASE_URL=http://localhost:3200 npm test -- --workers=1
npx tsc --noEmit
npm run lint
```

From the backend environment, run `python -m ruff check app tests` and
`python -m mypy app`.

## Scope and limits

This is a private workspace lexical evidence workflow. Public bibliographic
metadata is explicitly not searched as full text; an authorized external corpus
is unavailable. Quotation and nearby citation rules remain experimental and do
not verify attribution to the matched source. Search bounds are disclosed; no
accuracy, exhaustive recall, plagiarism determination or detector-evasion claims
are made. See `backend/docs/similarity-workflow.md` for the calculation, APIs,
offset basis, corpus states and work limits.

Earlier failed browser attempts are retained: attempt 1 omitted fixture login;
attempt 2 exposed the now-fixed checkbox state reset; attempt 3 started before
the restarting API was healthy. The final standalone flow and the complete
15-test suite passed. These failures are not counted as verification passes.

`verification.json` and `source-manifest.json` record this implementation.
`docs/product-contract.json` and its inspection artifacts remain the historical
pre-implementation audit, including unrelated workflow gaps.
