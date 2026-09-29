# Release gates

PASS means executed successfully on the recorded source. FAIL means executed and
failed. BLOCKED names an unavailable dependency. A skipped test is not PASS.

Baseline: backend Black, Ruff, mypy, pytest; frontend ESLint, TypeScript, production
build; Compose validation. Integration: empty/latest and previous/latest migrations,
actual non-owner PostgreSQL RLS, worker/storage failures, real browser workflows.
Release additionally requires model contracts/benchmarks, accessibility and manual
keyboard smoke, secret/SAST/dependency/container scans, SBOM, immutable images,
backup restore and hostile security recertification. No failure suppression.

Logs and machine-readable command results belong in `evidence/`. Historical
evidence elsewhere must not be presented as current certification. The complete
product cannot pass while required capabilities and model approvals are missing.

## Reproduction

Use `backend/scripts/prepare_slice0_compose.py` to resolve a separate project,
build its `verification` target, and wait for backend, worker and frontend health.
Run `python scripts/verity_gate.py --compose /tmp/<isolated>.json
--browser-url http://localhost:4700 --output docs/verity/evidence/<run>`.
The helper retains real PostgreSQL RLS tests and all live browser tests, and
fails on backend application/test formatting drift. The
verification image carries test tools; production API/worker images do not.
Python 3.12 Linux arm64 and Node 22.23.2 container builds are locally executed;
host frontend checks also use Node 24.17.0. Hosted AMD64 run
[36510870667](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36510870667)
executed all 11 repository gates and later failed while exporting images for
the scanner. The corrected source still requires its own hosted result.

`python scripts/verity_secret_gate.py` uses exact reviewed fingerprints in
`secret-review.json`; new findings fail. Review scope and limitations are in
the gate report. `python scripts/verity_image_gate.py --compose
/tmp/<isolated>.json --output docs/verity/evidence/<run>/images` scans every
image across all Compose profiles, deduplicating identical image IDs. It scans
exported archives with pinned Trivy, without passing a Docker socket or
credentials to the scanner, and produces CycloneDX SBOMs. HIGH/CRITICAL
findings fail, including when no fix is listed. The
[image report](IMAGE_SECURITY.md) records current findings and digest policy.

`scripts/verity_gate.py` writes a source manifest before testing and compares
it with the source after testing; source drift fails its own gate. The manifest
hash covers application code, tests, migrations, scripts, infrastructure,
Compose, dependency locks, and workflow definitions. Release prose and
generated evidence are outside this hash and are reviewed separately.

The GitHub Actions workflow builds every Azaeron image, pulls pinned
infrastructure images and invokes the same all-image gate. The workflow
definition is not proof of a hosted run; hosted results must be inspected
after push. The current local results are indexed in
[RELEASE_CERTIFICATION.md](RELEASE_CERTIFICATION.md); September 20 evidence
is retained as history and is not current certification.
