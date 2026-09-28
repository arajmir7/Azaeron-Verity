# Release image inventory and security gate

The R13 scan covers the images in the isolated review deployment on Linux
arm64. [Inventory](evidence/remediation/r13/inventory.json) maps every Compose
service, including profile-only verification and Mailpit, to its exact local
image ID and registry digest. The [scanner results](evidence/remediation/r13/all-images/results.json)
and per-image CycloneDX SBOMs are retained under the same evidence directory.
The scanner is Trivy pinned by digest in `scripts/verity_image_gate.py`; it
examines an exported image archive without mounting the Docker socket.

| Image / services | HIGH | CRITICAL | Gate |
| --- | ---: | ---: | --- |
| Distroless backend / API, worker, beat, migrate | 0 | 0 | PASS |
| Frontend | 0 | 0 | PASS |
| Verification (CI-only, not deployed) | 44 | 0 | FAIL |
| pgvector/PostgreSQL 16 | 102 | 16 | FAIL |
| Redis 7.4.11 Alpine | 2 | 0 | FAIL |
| MinIO server | 110 | 9 | FAIL |
| MinIO client/init | 49 | 2 | FAIL |
| Prometheus | 6 | 0 | FAIL |
| Grafana | 198 | 0 | FAIL |
| Jaeger | 67 | 4 | FAIL |
| OpenTelemetry collector | 74 | 7 | FAIL |
| Mailpit (development only) | 0 | 0 | PASS |

The original R13 scan exported SBOMs for all twelve images in that inventory. Counts are scanner findings in the exact
images, not assertions that each advisory is exploitable in this deployment.
Many findings have fixed versions listed in the report; there is no risk
acceptance or silent suppression. The full-stack image gate **fails**.

The final certification scan covers 15 distinct local Compose images and
exports an SBOM for each. Its [results](evidence/final-production-certification/all-images/results.json)
show zero HIGH/CRITICAL findings for the backend, worker, beat, migration,
frontend, and Mailpit images. Verification and eight infrastructure images
still fail the gate. The pinned Redis 7.4.11 candidate reduced Redis from the
previous 65 HIGH/6 CRITICAL findings to 2 HIGH/0 CRITICAL; it is still blocked
because the scanner reports two OpenSSL Alpine package findings. The complete
current reports and SBOMs are retained alongside the gate results.

`docker-compose.yml` now pins each third-party service to the registry digest
seen in the running image. A `latest@sha256` reference is immutable because the
digest controls content; its human-readable tag is not an update channel.
These are *observed*, not security-approved, versions. The registry repository,
digest, architecture, creation time, and size are in the inventory. The
application Dockerfiles pin their base images; the application build and its
SBOM must be regenerated for a new source snapshot. The same backend artifact
serves the API, worker, beat, and migration commands in this deployment.

The hosted runner could not pull MinIO's `mc` image through Docker Hub. The
MinIO server and client references now use the upstream Quay.io names with the
same content digests. The upstream release build publishes the corresponding
MinIO image tags to both registries from the same multi-platform build
([client build](https://github.com/minio/mc/blob/master/docker-buildx.sh),
[server build](https://github.com/minio/minio/pull/21560/files)). Hosted pulls
must still succeed on the corrected workflow before this change is considered
CI-verified.

An inference router and generative/semantic model runtimes have no approved
model, build, or deployed image. They are explicitly **BLOCKED** in the
inventory, not marked scanned. Any release that adds one must add its image to
the Compose inventory, generate its SBOM, and pass this gate before activation.

For each dependency update, select a maintained upstream release, record its
registry digest and provenance, scan the candidate, verify the SBOM and runtime
compatibility, then replace the pinned digest in Compose. Run migrations,
PostgreSQL/RLS, browser, outage, and recovery checks against those exact images.
Repeat scans on each release and when the vulnerability database changes; do
not repoint mutable tags behind the recorded digest. The CI workflow now builds
all Azaeron images (including beat and verification), pulls the pinned
infrastructure images, and scans all Compose profiles. Hosted execution has not
yet occurred. Until findings are remediated and the gate passes, infrastructure
images are not approved for production.
