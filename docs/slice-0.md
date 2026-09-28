# Slice 0 — foundation audit and workspace onboarding

Work performed September 12–13, 2026. Scope: the master prompt's architecture
audit and Prompt 01. Later prompts have not been declared complete or started as
new slices. The architecture and prioritized gaps are in
[ARCHITECTURE.md](../ARCHITECTURE.md).

## Implemented behavior

- Signup leads to the six-persona wizard. Submitting it creates and selects a
  free personal workspace, then offers an optional organization invitation.
  Student → `/check`; researcher → `/citations`; teacher, professor, reviewer
  and institution → `/documents`. Personas do not grant organization roles.
- Personal-workspace creation takes a PostgreSQL user-row lock and reloads the
  saved pointer after acquiring it. Simultaneous first-run requests create one
  workspace. Slugs use a random suffix so common display names do not race.
- The sidebar remembers workspace selection on the server and in per-user
  browser storage. Every selection is authorized by the server. Revoked
  memberships fall back to an authorized workspace. Failed switches hide
  tenant content and present a working retry.
- Workspace-free document routes offer inline creation. `/check` exposes the
  existing upload workflow; this alias does not implement Prompt 02's full
  primary-surface upgrade.
- Login and refresh restore an authorized recent workspace. Browser refresh
  sends the required JSON body and shares an in-flight rotation across parallel
  requests. Server rotation/reuse-detection tests remain green.
- Expiring invitation codes are restricted to the target email, can grant only
  non-administrator roles, and recheck the inviter's active authority. Replaying
  a code cannot restore a revoked membership. Issuing returns a code; it sends
  no email or other message.
- Server-owned entitlement checks use the persisted plan. Free defaults are
  20 new documents per UTC month, 10 MiB per upload and 60,000 characters per
  editorial request. Provisional paid-tier limits are 200 documents, 50 MiB
  and 200,000 characters; these are configuration limits, not marketed pricing.
  Expired subscriptions fall back to free. Upload confirmation serializes
  quota consumption under a workspace-row lock and rechecks upload identity.
  Existing-document access remains available after quota exhaustion.

## Foundation repairs

The baseline backend had **88 passing tests**, but all API fixtures used
SQLite. Backend Ruff passed; mypy reported **93 errors in 31 files**.
Frontend typecheck, lint, production build and the two public-page E2E tests
passed. These were measured results, not assumed from the prior documentation.

Clean Compose startup failed in migration 0003 because migration 0001 imported
live application metadata and had already created later constraints. Migration
0001 now uses frozen table definitions in
`backend/migration_snapshots/initial_20260826.py`. All later upgrades replay
normally; no migration was stamped or skipped. Existing databases that already
applied 0001 do not reexecute it.

Migration 0021 adds persona and workspace preferences. Migration 0022 adds a
database free-plan default and confines account audit rows to their owning user.
Tenant transaction settings explicitly clear missing context. Runtime
`azaeron_app` is neither owner, superuser nor BYPASSRLS. Tests check forced RLS
on all 30 tenant-resource tables, raw document/version/job reads without
application tenant filters, denied writes, account-audit isolation, and pooled
connection/context clearing. User, membership and organization directory
tables retain application authorization; they are not covered by tenant RLS.

Type repairs include SQLAlchemy forward-reference imports, accurate nullability
and response-schema conversion. They also exposed a real missing-document
error caused by a `status` parameter shadowing FastAPI's status module, and a
nonexistent password-change audit enum. Those paths now return/record their
intended results. PostgreSQL testing found and fixed timezone binding in the
quota query. The missing SQLite test driver is pinned in requirements.

## Verification evidence

Each linked log includes command output and exit status. Baseline failures are
retained alongside the repaired results.

| Gate | Result | Evidence |
| --- | --- | --- |
| Backend full suite | **111 passed**, no skips; 124 dependency/deprecation warnings | [Final backend tests](verification/slice-0/final-backend-tests.log) |
| PostgreSQL integration | **11 tests**, included in the full-suite result | [Test implementation](../backend/tests/integration/test_postgres_rls.py) |
| Backend typecheck | No issues in **122 source files** | [mypy](verification/slice-0/final-backend-typecheck.log) |
| Backend lint | Passed | [Ruff](verification/slice-0/final-backend-lint.log) |
| Frontend typecheck and lint | Passed | [Typecheck](verification/slice-0/final-frontend-typecheck.log), [lint](verification/slice-0/final-frontend-lint.log) |
| Frontend E2E | **14 passed** with live stack enabled | [Playwright](verification/slice-0/final-frontend-e2e.log) |
| Primary local E2E | **14 passed** against `http://localhost:3000` after applying the final build | [Local Playwright](verification/slice-0/final-local-frontend-e2e.log) |
| Production container builds | Passed | [Backend/worker/migration build](verification/slice-0/final-container-build.log), [frontend build](verification/slice-0/final-frontend-container-build.log) |
| Empty database migration replay | All **22 revisions** through `20260912_0022`, exit 0 | [Fresh replay](verification/slice-0/final-fresh-migrations.log) |
| Isolated Compose startup | `up --wait` exit 0 | [Compose startup](verification/slice-0/final-compose-up.log) |
| Primary local Compose startup | Updated application at `http://localhost:3000`, existing volumes retained | [Local startup](verification/slice-0/final-local-compose-up.log) |
| Local readiness | Database, Redis, storage and workers OK; schema at `20260912_0022` | [Health probes](verification/slice-0/final-local-health.log) |
| Compose configuration | Valid | [Configuration validation](verification/slice-0/final-compose-config.log) |

The live browser test uses a synthetic student account and a real text file.
It exercises signup → personal workspace → upload → PostgreSQL/MinIO/Celery
processing → document review, checks concurrent onboarding retries, switches to
another workspace and verifies a 404 for the first workspace's document, then
refreshes the session and restores the original workspace. Mocked boundary
tests separately cover all six landing workflows and network/revocation recovery.
The new PostgreSQL quota race proves exactly one of two simultaneous requests
can consume the last monthly slot.

[Recorded browser walkthrough](verification/slice-0/onboarding/video.webm):
[role choice](verification/slice-0/onboarding/01-role-choice.png),
[personal workspace](verification/slice-0/onboarding/02-personal-workspace.png),
[first processed document](verification/slice-0/onboarding/03-first-document.png),
[restored workspace](verification/slice-0/onboarding/04-restored-workspace.png).
The recording and screenshots retained here are from the final primary local
run. The corresponding role-choice and processed-document layouts were visually
inspected during isolated verification. Source checksums are retained in
[source-sha256.txt](verification/slice-0/source-sha256.txt).

For human manual acceptance, open `http://localhost:3000/register`, complete
the role wizard, skip or enter an invitation, upload a document, inspect its
processed result, switch workspaces and return. Record the operator, date,
recording location and pass/fail outcome here. No human acceptance entry exists
yet.

**Manual acceptance remains NOT VERIFIED.** The recording is a real automated
browser run; it is not evidence of a human-performed manual walkthrough. The
prompt's manual gate must be recorded separately before advancing to Prompt 02.
No production-readiness, paid-provider, validated-model or 72-hour-soak claim is
made by these short local tests.

## Reproduce

The primary Compose project's data volumes were preserved during isolated
verification. The temporary test stack was stopped afterward to release local
resources; its volumes and verification artifacts were retained. An isolated
configuration can be generated from the repository:

```sh
python3 backend/scripts/prepare_slice0_compose.py \
  --project azaeron-slice0-gate \
  --output /tmp/azaeron-slice0-compose.json
docker compose -f /tmp/azaeron-slice0-compose.json build
docker compose -f /tmp/azaeron-slice0-compose.json up --wait --wait-timeout 120
```

Use an unused project name and unused port offset for a fresh deployment. The
default offset publishes frontend 3100, API 8100, MinIO 9100/9101. Resolved
configuration may contain development credentials; it is written owner-only
outside the repository. It is not a release artifact.

```sh
docker compose -f /tmp/azaeron-slice0-compose.json run --rm --no-deps \
  -e CORS_ORIGINS=http://localhost:3000 backend \
  python -c 'import os,pytest; os.environ["POSTGRES_TEST_DATABASE_URL"] = os.environ["DATABASE_URL"]; raise SystemExit(pytest.main(["tests", "-q"]))'
docker compose -f /tmp/azaeron-slice0-compose.json run --rm --no-deps backend python -m mypy app
docker compose -f /tmp/azaeron-slice0-compose.json run --rm --no-deps backend python -m ruff check app tests migration_snapshots
```

The CORS override is for fixture tests whose explicit browser Origin is
`http://localhost:3000`; it does not change the running API configuration.
Without `POSTGRES_TEST_DATABASE_URL`, PostgreSQL tests explicitly skip and the
RLS gate has not been run. From `frontend/`:

```sh
npx tsc --noEmit
npm run lint
npm run build
RUN_LIVE_E2E=1 PLAYWRIGHT_BASE_URL=http://localhost:3100 npm test -- --workers=2
```

Without `RUN_LIVE_E2E=1`, the live integration browser test explicitly skips.
The API client uses the frontend's same-origin proxy by default. Next.js public
API URLs and proxy destinations are build-time settings; Compose passes them
as frontend build arguments instead of relying on runtime-only configuration.

## Remaining boundaries

Entitlements are a foundation stub: no billing provider, invoice view, signed
billing webhook, per-plan rate limiter, seats, word/storage usage ledger or
revision-count accounting has been implemented here. Invitations use expiring
codes and membership/issuer checks, without an invitation-management console.
Migration upgrade paths were verified; full historical downgrade/rollback and
production backup restoration were not certified. Prompt 02 and subsequent
slices retain their independent acceptance gates in the architecture gap list.
