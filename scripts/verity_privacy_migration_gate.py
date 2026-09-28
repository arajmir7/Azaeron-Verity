"""Exercise privacy migration rollback in a new database on an isolated local stack."""

import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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
    if (
        config["name"] == primary["name"]
        or config["services"]["backend"]["environment"]["ENVIRONMENT"] != "development"
    ):
        parser.error("Use an isolated development verification stack")
    args.output.mkdir(parents=True, exist_ok=True)
    name = "verity_privacy_gate_" + uuid4().hex
    pg_user = config["services"]["postgres"]["environment"]["POSTGRES_USER"]
    psql = compose + [
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        pg_user,
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
    ]
    environment = dict(os.environ)
    for key, source in [
        ("DATABASE_URL", config["services"]["backend"]["environment"]["DATABASE_URL"]),
        (
            "MIGRATION_DATABASE_URL",
            config["services"]["migrate"]["environment"]["MIGRATION_DATABASE_URL"],
        ),
    ]:
        parsed = urlsplit(source)
        environment[key] = urlunsplit(parsed._replace(path="/" + name))
    environment["APP_DB_PASSWORD"] = config["services"]["migrate"]["environment"][
        "APP_DB_PASSWORD"
    ]
    command = compose + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{ROOT / 'backend'}:/app",
        "-e",
        "DATABASE_URL",
        "-e",
        "MIGRATION_DATABASE_URL",
        "-e",
        "APP_DB_PASSWORD",
        "verification",
    ]
    results = []

    def run(label, arguments, expected=0):
        with (args.output / (label + ".log")).open("w") as log:
            result = subprocess.run(
                arguments,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
        passed = (
            result.returncode == expected if expected == 0 else result.returncode != 0
        )
        results.append(
            {
                "gate": label,
                "exit_code": result.returncode,
                "expected": "zero" if expected == 0 else "rejection",
                "status": "PASS" if passed else "FAIL",
            }
        )
        if not passed:
            raise RuntimeError(label + " did not meet its expected result")

    created = False
    try:
        run("create-isolated-database", psql + ["-c", f'CREATE DATABASE "{name}"'])
        created = True
        run("fresh-to-privacy", command + ["alembic", "upgrade", "20260924_0033"])
        seed = """import asyncio
import app.models
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import User
async def main():
    async with AsyncSessionLocal.begin() as db:
        db.add(User(id='00000000-0000-4000-8000-000000000731', email='migration-fixture@example.com', hashed_password='fixture-only-no-login'))
asyncio.run(main())
"""
        run("seed-account", command + ["python", "-c", seed])
        run(
            "downgrade-to-identity", command + ["alembic", "downgrade", "20260920_0029"]
        )
        run("reupgrade-privacy", command + ["alembic", "upgrade", "20260924_0033"])
        check = """import asyncio
import app.models
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import User
async def main():
    async with AsyncSessionLocal.begin() as db:
        user = await db.get(User, '00000000-0000-4000-8000-000000000731')
        assert user is not None and user.hashed_password == 'fixture-only-no-login'
        assert user.mfa_last_counter == -1 and user.mfa_pending_secret is None
        from app.core.database import apply_tenant_context
        from sqlalchemy import text
        await apply_tenant_context(db, None, str(user.id))
        await db.execute(text("SELECT app.privacy_request(:id,'account',:target,:digest)"), {"id": "00000000-0000-4000-8000-000000000732", "target": str(user.id), "digest": "a"*64})
asyncio.run(main())
"""
        run("account-preserved-and-create-tombstone", command + ["python", "-c", check])
        run(
            "erasure-downgrade-rejected",
            command + ["alembic", "downgrade", "20260920_0029"],
            expected=1,
        )
        guard_log = (args.output / "erasure-downgrade-rejected.log").read_text()
        if "Cannot discard erasure tombstones" not in guard_log:
            raise RuntimeError("Downgrade failed for an unrelated reason")
    finally:
        if created:
            run("remove-isolated-database", psql + ["-c", f'DROP DATABASE "{name}"'])
        (args.output / "results.json").write_text(
            json.dumps({"results": results}, indent=2) + "\n"
        )
    print(
        "Privacy fresh migration, rollback, account preservation and tombstone guard: PASS"
    )


if __name__ == "__main__":
    main()
