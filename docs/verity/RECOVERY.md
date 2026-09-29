# Current clean recovery exercise — 2026-09-29

A fresh source fixture and distinct restore project with private volumes passed [restore and replay](evidence/final-blocker-burndown/recovery/recovery-result.json) at schema `20260928_0036`. Four MinIO objects were restored. A separately retained tombstone for one account erased after the database snapshot was replayed before serving; two target objects were removed and the erased login returned 401. One surviving immutable version's bytes and SHA-256 matched; [both surviving provenance event identities and payloads](evidence/final-blocker-burndown/recovery/provenance.json) matched the source. Non-owner RLS with no tenant context passed; API and frontend reached readiness after replay. Active restore plus replay took **18.718 seconds** on this local host. The represented snapshot-to-erasure interval was 651.041 seconds and is not a production RPO measurement.

An initial phase required a source-PostgreSQL access correction; one Docker CLI polling timeout was retried with the same erasure identity and original grace period. Failed attempts remain as evidence. This small same-host fixture does not certify offsite backups, versioned buckets and delete markers, restoration of every object at production scale, or production RPO/RTO. The source fixture did not retain a survivor's login credentials, so survivor login was not exercised; surviving version, object, provenance and readiness were checked independently.

## Procedure and historical exercises

# PostgreSQL and MinIO recovery procedure

The recoverable product state is the **database, every referenced customer
object, the bucket policy/lifecycle, required configuration and encryption
keys, the migration revision, and an independently retained erasure ledger**.
A database dump by itself can expose missing bytes or resurrect data erased
after the dump. The application must stay unavailable until the final privacy
replay and content verification pass.

## Backup boundary

1. Freeze application writes and let active workers settle. Record the UTC
   snapshot boundary. Keep the original stack available for recovery only; a
   backup copy must not share its volumes or container network with a restore.
2. Create a PostgreSQL custom-format dump including schema, RLS policies,
   functions, ownership, grants, data, and `alembic_version`. Back up role
   definitions or securely retain the runtime-role credential needed to
   provision them in a fresh PostgreSQL cluster. Capture object bytes and their
   SHA-256 values, the bucket/versioning/lifecycle settings, configuration
   metadata, deployment image identities, the policy files, and decryption keys.
   Keep customer bytes and secrets in encrypted private backup storage.
3. Write each completed erasure tombstone to an independent append-only store
   after the backup boundary. Keep its scope, target, object-key/prefix manifest,
   original grace deadline, and completion time. Do not rely on the restored
   database's own copy of the ledger to know what happened after its snapshot.
   Tombstone retention must outlast every older backup and its recovery margin.

The local exercise used a consistent snapshot of the isolated review project
and backed up a 23.5 MB PostgreSQL dump, 363 MinIO objects (1.06 MB), the
private Compose configuration, and MinIO policy files. The source bucket had
versioning disabled; a deployment with object versioning enabled must preserve
all object versions and delete markers. This script deliberately fails when it
finds delete markers so it cannot imply full coverage on a different bucket.
See [backup.json](evidence/remediation/r12/backup.json).

## Restore while serving is disabled

1. Allocate a fresh project with **distinct** PostgreSQL, Redis, and MinIO
   volumes and a distinct network. Confirm the actual Docker mounts before
   connecting. Provision the runtime database role, restore the custom dump,
   and verify the schema revision and RLS behavior for the non-owner role.
2. Create the bucket and policies, restore each object after checking its
   manifest hash, and verify the restored document/version references. Do not
   start the API, frontend, or workers yet.
3. Import the latest independent tombstones. For any erasure completed after
   the database snapshot, use the authorized privacy routines under a trusted
   operator transaction to remove restored database content. Apply the
   **original** upload-URL grace deadline only after it has elapsed. Delete
   every matching MinIO object version and multipart upload, then enumerate
   again. For tombstones already marked complete in the restored database,
   verify absence again; a completed status does not prove a separately
   restored object store is clean. Fail closed if a completed tombstone has
   contradictory live rows.
4. Check every surviving immutable version's stored bytes against its recorded
   SHA-256, its predecessor lineage, migration revision, and tenant isolation.
   Only then start workers, API, and frontend. Require readiness 200 and reject
   login for the erased fixture. Preserve logs, measured timing, and hashes.

`scripts/verity_recovery_gate.py` implements this as `prepare`, `snapshot`,
`restore`, `erase`, and `replay` phases against the private development Compose
file. Its private dump, object bytes, credentials, and complete tombstones stay
under ignored `.verity-local/recovery`; sanitized results are under
[r12 evidence](evidence/remediation/r12/). The first local restore attempt
exposed a shared-volume configuration error; the recovery containers were
removed before importing data, the source database was restarted and checked,
and the regenerated restore project passed an actual mount-isolation assertion.
The [incident record](evidence/remediation/r12/isolation-incident.json) is
retained. Do not use an old generated recovery Compose file.

**Executed outcome:** the latest independent ledger contained six completed
tombstones, including one account erased after the snapshot. The replay removed
that account and its object from the restored stack. The final byte audit then
found **64 document-version references across 32 documents with no corresponding
object in the original backup** (`tests/`: 36, `fixture/`: 14, `versions/`:
14). These are synthetic rows left by earlier local tests. Missing bytes cannot
be recreated from a database hash, so the gate failed and the recovered API was
never started. [Integrity result](evidence/remediation/r12/integrity-failure.json).
This proves the replay and fail-closed check, but **does not certify complete
product recovery or an RTO**. The valid snapshot-to-erasure interval represented
524 seconds; restoration before replay took 13.9 seconds. Neither is a
production RPO/RTO achievement. A clean, representative dataset and full
readiness exercise are still required.

## R15 clean control exercise, 2026-09-28

A fresh source project with new PostgreSQL, Redis, MinIO volumes, and a separate
network was created specifically to avoid the synthetic orphan rows above. The
snapshot contained two accounts and documents: the target account was erased
after backup, while an independent control account and version remained. The
custom-format database dump was 360,377 bytes; the object manifest contained four
objects (254 bytes total), and bucket versioning was disabled. Restore used
distinct PostgreSQL/MinIO volumes and kept the API unavailable until tombstone
replay and integrity checks completed.

The [R15 result](evidence/final-production-certification/recovery-r15-control/recovery-result.json)
passes: one post-backup tombstone was replayed, two target-account objects were
removed, the erased login was rejected, and the surviving immutable version's
stored bytes matched its SHA-256. Runtime RLS without tenant context passed; the
restored API and frontend then reached readiness. Pre-replay restore took 3.212
seconds; active restore plus replay took 7.687 seconds, with readiness reached
4.475 seconds after replay began. The represented snapshot-to-completed-erasure
window was 2,481.723 seconds. Sanitized dump/object manifests, restore checks and
tombstone export are in the linked evidence directory. The earlier R15 attempt
is retained with an explicit [scope assessment](evidence/final-production-certification/recovery-r15-no-survivor/assessment.json):
its erasure passed, but it left no surviving version to verify.

This remains a same-host synthetic drill, with only one surviving control
version and no offsite backup, key escrow, geographic failure, full retention
growth, or staffed incident process. These timings do not certify production
RPO/RTO or disaster-recovery readiness at deployment scale.

## Targets and limits

**Proposed targets:** RPO ≤24 hours for ordinary writes and zero erased-account
resurrection; RTO ≤4 hours from declared incident to verified application
readiness. Neither target is a production claim. The local exercise measures
only its actual snapshot/restore interval, represented post-backup change
window, and application readiness. It does not prove an encrypted offsite
backup, geographic failure recovery, scheduled backups, key escrow, or an
operational on-call process. Those require deployment-specific evidence.
