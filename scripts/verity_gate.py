"""Re-run repository gates against a separately provisioned verification stack.

This is the executable repository gate, not model or production certification.
No skipped integration/browser suite is treated as a pass. See QUALITY_GATES.md.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def source_manifest() -> dict[str, str]:
    """Hash every release-relevant source file before and after the gates."""
    manifest = {}
    for folder in (
        "backend/app",
        "backend/tests",
        "backend/alembic",
        "backend/migration_snapshots",
        "backend/scripts",
        "frontend/src",
        "frontend/tests",
        "infrastructure",
        "config",
        "scripts",
        ".github/workflows",
    ):
        for file in sorted((ROOT / folder).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                manifest[str(file.relative_to(ROOT))] = hashlib.sha256(
                    file.read_bytes()
                ).hexdigest()
    for name in (
        "docker-compose.yml",
        ".nvmrc",
        "backend/pyproject.toml",
        "backend/pytest.ini",
        "backend/requirements.txt",
        "backend/requirements.lock",
        "backend/requirements-dev.txt",
        "backend/requirements-dev.lock",
        "frontend/next.config.ts",
        "backend/Dockerfile",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/Dockerfile",
    ):
        manifest[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--browser-url", required=True)
    parser.add_argument("--verification-service", default="verification")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/verity/evidence/final"
    )
    args = parser.parse_args()
    compose = ["docker", "compose", "-f", str(args.compose.resolve())]
    config = json.loads(
        subprocess.check_output(compose + ["config", "--format", "json"])
    )
    primary = json.loads(
        subprocess.check_output(
            ["docker", "compose", "config", "--format", "json"], cwd=ROOT
        )
    )
    if config["name"] == primary["name"]:
        parser.error("Use an isolated verification project, never the primary database")
    primary_volumes = {
        item.get("name", name) for name, item in primary.get("volumes", {}).items()
    }
    if any(
        item.get("external") or item.get("name", name) in primary_volumes
        for name, item in config.get("volumes", {}).items()
    ):
        parser.error("Verification volumes must be private to the isolated project")
    environment = config["services"]["backend"]["environment"]
    if environment.get("ENVIRONMENT") != "development":
        parser.error("Only an explicitly development verification stack is accepted")
    args.output.mkdir(parents=True, exist_ok=True)
    before = source_manifest()
    encoded = json.dumps(before, sort_keys=True, indent=2) + "\n"
    (args.output / "source.json").write_text(encoded)
    container = compose + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{ROOT / 'backend'}:/app",
    ]
    unit = container + [
        "-e",
        "CORS_ORIGINS=http://localhost:3000",
        args.verification_service,
        "pytest",
        "-p",
        "no:cacheprovider",
        "tests",
        "--ignore=tests/integration",
        "-q",
    ]
    postgres = container + [
        "-e",
        "POSTGRES_TEST_DATABASE_URL",
        "-e",
        "RUN_STORAGE_INTEGRATION=1",
        "-e",
        "PRIVACY_MINIO_ACCESS_KEY",
        "-e",
        "PRIVACY_MINIO_SECRET_KEY",
        args.verification_service,
        "pytest",
        "-p",
        "no:cacheprovider",
        "tests/integration",
        "-q",
    ]
    mail_ports = config["services"].get("mailpit", {}).get("ports", [])
    mail_port = next(
        (port["published"] for port in mail_ports if port["target"] == 8025), None
    )
    env = {
        **os.environ,
        "POSTGRES_TEST_DATABASE_URL": environment["DATABASE_URL"],
        "RUN_LIVE_E2E": "1",
        "RUN_OBSERVABILITY_E2E": "1",
        "PLAYWRIGHT_BASE_URL": args.browser_url,
        "MAILPIT_URL": f"http://localhost:{mail_port}" if mail_port else "",
        "OBSERVABILITY_EVIDENCE": str((args.output / "observability").resolve()),
    }
    for service, variable, target in (
        ("prometheus", "PROMETHEUS_URL", 9090),
        ("jaeger", "JAEGER_URL", 16686),
    ):
        published = next(
            port["published"]
            for port in config["services"][service].get("ports", [])
            if port["target"] == target
        )
        env[variable] = f"http://127.0.0.1:{published}"
    worker_environment = config["services"]["celery-worker"]["environment"]
    for key in ("PRIVACY_MINIO_ACCESS_KEY", "PRIVACY_MINIO_SECRET_KEY"):
        if not worker_environment.get(key):
            parser.error(
                "The storage integration gate requires worker maintenance credentials"
            )
        env[key] = worker_environment[key]

    def run(gate):
        name, command, cwd = gate
        started = time.monotonic()
        with (args.output / f"{name}.log").open("w") as log:
            try:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 124
            except FileNotFoundError as error:
                log.write(f"Required executable unavailable: {error.filename}\n")
                code = 127
        result = {
            "gate": name,
            "command": command,
            "status": "PASS" if code == 0 else "FAIL",
            "exit_code": code,
            "seconds": round(time.monotonic() - started, 2),
        }
        print(f"{name}: {result['status']} ({result['seconds']}s)", flush=True)
        return result

    gates = [
        (
            "backend-format",
            container + [args.verification_service, "black", "--check", "app", "tests"],
            ROOT,
        ),
        (
            "backend-lint",
            container + [args.verification_service, "ruff", "check", "app", "tests"],
            ROOT,
        ),
        (
            "backend-typecheck",
            container + [args.verification_service, "mypy", "app"],
            ROOT,
        ),
        ("unit-security-worker-contract", unit, ROOT),
        ("postgres-rls", postgres, ROOT),
        ("frontend-lint", ["npm", "run", "lint"], ROOT / "frontend"),
        ("compose", compose + ["config", "--quiet"], ROOT),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, gates))
    # Next regenerates TypeScript's generated route declarations during builds.
    for gate in [
        ("frontend-build", ["npm", "run", "build"], ROOT / "frontend"),
        ("frontend-typecheck", ["npx", "tsc", "--noEmit"], ROOT / "frontend"),
        ("browser", ["npm", "test", "--", "--workers=1"], ROOT / "frontend"),
    ]:
        results.append(run(gate))
    after = source_manifest()
    (args.output / "source-after.json").write_text(
        json.dumps(after, sort_keys=True, indent=2) + "\n"
    )
    results.append(
        {
            "gate": "source-stability",
            "status": "PASS" if before == after else "FAIL",
            "exit_code": 0 if before == after else 1,
            "changed_paths": sorted(
                path
                for path in before.keys() | after.keys()
                if before.get(path) != after.get(path)
            ),
        }
    )
    (args.output / "results.json").write_text(
        json.dumps(
            {
                "source_manifest_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
                "production_certified": False,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    return int(any(result["exit_code"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
