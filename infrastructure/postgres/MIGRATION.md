# PostgreSQL 16 image-family migration

The controlled image uses the pinned official PostgreSQL 16 Alpine base and
hash-verified pgvector source in `source.json`. It runs as `postgres`, has no
compiler, and removes the unused root privilege-switch executable. Never mount a
Debian/Ubuntu PGDATA volume into it. Same PostgreSQL major version is not proof
of libc, collation, locale or binary extension compatibility.

The primary Compose volume now has the distinct physical name
`azaeron_verity_postgres16_secure_data`. Legacy volumes are preserved. An empty
database refuses initialization unless `AZAERON_DATABASE_BOOTSTRAP` explicitly
selects `new-install` or `logical-restore`. A populated database without this
image family's initialization marker is rejected. Do not fabricate that marker.

For a genuinely new installation, set `AZAERON_DATABASE_BOOTSTRAP=new-install`.
Existing installations must use a logical migration; do not select `new-install`
to bypass it. Keep the source stack, source image ID, source volume names and
owner-only resolved Compose configuration available for rollback.

1. Quiesce application writes and workers. Export a custom-format `pg_dump` and
   matching MinIO objects with SHA-256 manifests. Export the latest erasure
   tombstones separately. Preserve role grants, configuration and encryption keys
   in protected backup storage; never put credentials in public evidence.
2. Create a distinct project/network and entirely NEW volumes. Select the tested
   image ID, set `AZAERON_DATABASE_BOOTSTRAP=logical-restore`, and start only storage.
3. Create the restricted application role, restore with `pg_restore --exit-on-error`,
   run migrations, restore objects, and verify row/relationship and object hashes.
   Rebuild indexes from the logical dump. Check application-specific collation
   behavior for production data; the local fixture does not certify every locale.
4. Run PostgreSQL/RLS/storage tests in a **separate test database** on that image.
   Some concurrency tests retain immutable records backed by in-memory objects;
   never insert those contract fixtures into a recovery dataset.
5. Replay all post-backup erasures before starting the restored API. Verify erased
   accounts cannot log in, survivors retain valid immutable versions, and the
   runtime role sees no tenant data without context.
6. Start the restored application, verify readiness and product flows, then take
   another backup and restore it into a second set of NEW volumes. Confirm
   tombstones, relationships and object hashes again before any cutover.

`scripts/verity_recovery_gate.py` provides an isolated exercise with phases
`prepare`, `agents`, `snapshot`, `restore`, `erase`, `replay`, `second`.
`VERITY_RECOVERY_POSTGRES_IMAGE` selects a locally inspected immutable image ID;
`VERITY_RECOVERY_TARGET` and the private source/output environment variables
select isolated resources. `restore` refuses pre-existing target volumes. Preserve
failed trial volumes and select a new target when retrying. Public evidence contains
only IDs, hashes and counts. This exercise does not automatically migrate customer
data or certify production RPO/RTO, offsite backups or all locale-sensitive queries.
