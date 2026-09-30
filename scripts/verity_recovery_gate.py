#!/usr/bin/env python3
"""Exercise an isolated PostgreSQL/MinIO restore with post-backup erasure replay.

Private source credentials, dump, object bytes and tombstones live only under
.verity-local/recovery. Public evidence contains IDs/hashes/counts, never secrets.
Run prepare, snapshot, restore, erase, replay in that order. The source review
project is paused only during the cross-store snapshot; primary Compose is untouched.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from uuid import UUID, uuid4

import httpx
from minio import Minio
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(
    os.environ.get("VERITY_RECOVERY_PRIVATE", ROOT / ".verity-local/recovery")
).resolve()
PUBLIC = Path(
    os.environ.get(
        "VERITY_RECOVERY_OUTPUT", ROOT / "docs/verity/evidence/remediation/r12"
    )
).resolve()
SOURCE_CONFIG = Path(
    os.environ.get(
        "VERITY_RECOVERY_SOURCE_COMPOSE", ROOT / ".verity-local/identity-compose.json"
    )
).resolve()
BUCKET = "azaeron-documents"
TARGET = os.environ.get("VERITY_RECOVERY_TARGET", "azaeron-verity-dr")
POSTGRES_IMAGE = os.environ.get("VERITY_RECOVERY_POSTGRES_IMAGE")
CRITICAL_TABLES = (
    "documents",
    "document_versions",
    "provenance_events",
    "ai_conversations",
    "ai_messages",
    "ai_runs",
    "ai_tool_calls",
    "ai_tool_results",
    "ai_events",
    "ai_document_attachments",
    "ai_action_receipts",
    "ai_voice_profiles",
)


def relational_evidence(config, port):
    """Hash stored rows, including encrypted payloads, without publishing text."""
    result = {}
    with pg_conn(config, port) as db:
        for table in CRITICAL_TABLES:
            rows = db.execute(
                sql.SQL("SELECT row_to_json(t) FROM {} t ORDER BY id").format(
                    sql.Identifier(table)
                )
            ).fetchall()
            encoded = json.dumps(
                [row[0] for row in rows], sort_keys=True, separators=(",", ":")
            ).encode()
            result[table] = {"count": len(rows), "sha256": digest(encoded)}
    return result


def source_port(service: str, target: int) -> int:
    ports = load(SOURCE_CONFIG)["services"][service]["ports"]
    return int(next(port["published"] for port in ports if port["target"] == target))


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def load(path):
    return json.loads(path.read_text())


def compose(config, *args, **kwargs):
    return subprocess.run(
        ["docker", "compose", "-f", str(config), *args],
        check=True,
        stdout=kwargs.get("stdout", subprocess.DEVNULL),
        stderr=kwargs.get("stderr", subprocess.PIPE),
        stdin=kwargs.get("stdin"),
        timeout=kwargs.get("timeout", 180),
    )


def storage(config, port):
    env = load(config)["services"]["minio"]["environment"]
    return Minio(
        f"localhost:{port}",
        access_key=env["MINIO_ROOT_USER"],
        secret_key=env["MINIO_ROOT_PASSWORD"],
        secure=False,
    )


def pg_conn(config, port):
    env = load(config)["services"]["postgres"]["environment"]
    return psycopg.connect(
        host="127.0.0.1",
        port=port,
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
    )


def fixture():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    PRIVATE.chmod(0o700)
    password = uuid4().hex + "Aa1!"
    email = f"recovery-{uuid4().hex}@example.com"
    text = b"Isolated disaster recovery fixture with immutable version lineage."
    save(PRIVATE / "fixture-pending.json", {"email": email, "password": password})
    origin = {"Origin": f"http://localhost:{source_port('frontend', 3000)}"}
    with httpx.Client(
        base_url=f"http://localhost:{source_port('backend', 8000)}",
        headers=origin,
        timeout=45,
    ) as api:
        for route, payload, expected in (
            ("auth/register", {"email": email, "password": password}, 201),
            ("auth/login", {"email": email, "password": password}, 200),
            ("auth/onboarding", {"product_role": "researcher"}, 200),
        ):
            response = api.post("/api/v1/" + route, json=payload)
            assert response.status_code == expected, (route, response.status_code)
        user = api.get("/api/v1/auth/me").json()
        upload = api.post(
            "/api/v1/documents/upload-request",
            json={
                "filename": "recovery.txt",
                "content_type": "text/plain",
                "file_size": len(text),
            },
        )
        assert upload.status_code == 200, upload.status_code
        slot = upload.json()
        object_store = storage(SOURCE_CONFIG, source_port("minio", 9000))
        object_store.put_object(
            BUCKET,
            slot["storage_key"],
            io.BytesIO(text),
            len(text),
            content_type="text/plain",
        )
        confirmed = api.post(
            "/api/v1/documents/upload-confirm",
            json={
                "upload_id": slot["upload_id"],
                "storage_key": slot["storage_key"],
                "original_filename": "recovery.txt",
                "sha256_fingerprint": digest(text),
            },
        )
        assert confirmed.status_code == 200, confirmed.status_code
        document = confirmed.json()
        for _ in range(120):
            content = api.get(f"/api/v1/documents/{document['id']}/content")
            if content.status_code == 200:
                version = content.json()["document_version_id"]
                break
            time.sleep(1)
        else:
            raise RuntimeError("Recovery fixture processing did not complete")
        timeline = api.get(f"/api/v1/provenance/documents/{document['id']}/timeline")
        assert timeline.status_code == 200, timeline.status_code
        object_key = next(
            item["storage_object"]
            for item in timeline.json()["versions"]
            if item["id"] == version
        )
    # Keep a separate account/document in the restored database. Erasing only
    # the target account would otherwise leave no surviving version bytes to
    # verify after replay.
    survivor_email = f"recovery-survivor-{uuid4().hex}@example.com"
    survivor_password = uuid4().hex + "Bb2!"
    survivor_text = b"Independent retained recovery control with immutable lineage."
    with httpx.Client(
        base_url=f"http://localhost:{source_port('backend', 8000)}",
        headers=origin,
        timeout=45,
    ) as survivor_api:
        for route, payload, expected in (
            (
                "auth/register",
                {"email": survivor_email, "password": survivor_password},
                201,
            ),
            (
                "auth/login",
                {"email": survivor_email, "password": survivor_password},
                200,
            ),
            ("auth/onboarding", {"product_role": "researcher"}, 200),
        ):
            response = survivor_api.post("/api/v1/" + route, json=payload)
            assert response.status_code == expected, (route, response.status_code)
        survivor_user = survivor_api.get("/api/v1/auth/me").json()
        survivor_upload = survivor_api.post(
            "/api/v1/documents/upload-request",
            json={
                "filename": "recovery-survivor.txt",
                "content_type": "text/plain",
                "file_size": len(survivor_text),
            },
        )
        assert survivor_upload.status_code == 200, survivor_upload.status_code
        survivor_slot = survivor_upload.json()
        object_store = storage(SOURCE_CONFIG, source_port("minio", 9000))
        object_store.put_object(
            BUCKET,
            survivor_slot["storage_key"],
            io.BytesIO(survivor_text),
            len(survivor_text),
            content_type="text/plain",
        )
        survivor_confirmed = survivor_api.post(
            "/api/v1/documents/upload-confirm",
            json={
                "upload_id": survivor_slot["upload_id"],
                "storage_key": survivor_slot["storage_key"],
                "original_filename": "recovery-survivor.txt",
                "sha256_fingerprint": digest(survivor_text),
            },
        )
        assert survivor_confirmed.status_code == 200, survivor_confirmed.status_code
        survivor_document = survivor_confirmed.json()
        for _ in range(120):
            survivor_content = survivor_api.get(
                f"/api/v1/documents/{survivor_document['id']}/content"
            )
            if survivor_content.status_code == 200:
                survivor_version = survivor_content.json()["document_version_id"]
                break
            time.sleep(1)
        else:
            raise RuntimeError("Survivor recovery fixture processing did not complete")
    state = {
        "created_at": now(),
        "email": email,
        "password": password,
        "user_id": user["id"],
        "document_id": document["id"],
        "version_id": version,
        "object_key": object_key,
        "content_sha256": digest(text),
        "survivor_user_id": survivor_user["id"],
        "survivor_document_id": survivor_document["id"],
        "survivor_version_id": survivor_version,
        "survivor_content_sha256": digest(survivor_text),
    }
    save(PRIVATE / "fixture.json", state)
    save(
        PUBLIC / "fixture.json",
        {
            "created_at": state["created_at"],
            "document_id": state["document_id"],
            "version_id": version,
            "content_sha256": state["content_sha256"],
            "survivor_document_id": state["survivor_document_id"],
            "survivor_version_id": state["survivor_version_id"],
            "survivor_content_sha256": state["survivor_content_sha256"],
            "result": "PASS",
        },
    )


def agent_fixture():
    """Exercise real local tools and an explicit citation decision, without AI."""
    state = load(PRIVATE / "fixture.json")
    if "agent_fixture" in state:
        raise RuntimeError("Agent fixture already exists; do not seed twice")
    origin = {"Origin": f"http://localhost:{source_port('frontend', 3000)}"}
    with httpx.Client(
        base_url=f"http://localhost:{source_port('backend', 8000)}",
        headers=origin,
        timeout=45,
    ) as api:
        login = api.post(
            "/api/v1/auth/login",
            json={"email": state["email"], "password": state["password"]},
        )
        assert login.status_code == 200
        passage = (
            "The recovery team records each document version before taking a backup. "
            "An isolated database receives the logical archive on a new volume. "
            "The team compares content hashes and checks the relationships between records. "
            "A separate account retains its document after the first account is erased. "
            "This purpose written fixture supports an engineering test and makes no research claims. "
            "A citation decision creates an immutable result that remains linked to its source. "
            "Restoration includes the conversation, tool invocation, evidence and user decision. "
            "The checks run before serving begins so deleted data cannot reappear in the application. "
            "The exercise uses no customer documents and calls no external intelligence service."
        )

        def upload(name, text):
            body = text.encode()
            response = api.post(
                "/api/v1/documents/upload-request",
                json={
                    "filename": name,
                    "content_type": "text/plain",
                    "file_size": len(body),
                },
            )
            assert response.status_code == 200
            slot = response.json()
            storage(SOURCE_CONFIG, source_port("minio", 9000)).put_object(
                BUCKET,
                slot["storage_key"],
                io.BytesIO(body),
                len(body),
                content_type="text/plain",
            )
            response = api.post(
                "/api/v1/documents/upload-confirm",
                json={
                    "upload_id": slot["upload_id"],
                    "storage_key": slot["storage_key"],
                    "original_filename": name,
                    "sha256_fingerprint": digest(body),
                },
            )
            assert response.status_code == 200
            document = response.json()["id"]
            for _ in range(90):
                response = api.get(f"/api/v1/documents/{document}/content")
                if response.status_code == 200:
                    return {
                        "document_id": document,
                        "document_version_id": response.json()["document_version_id"],
                    }
                time.sleep(1)
            raise RuntimeError("Agent recovery document did not process")

        upload("recovery-citation-source.txt", passage + " Source fixture.")
        target = upload("recovery-citation-target.txt", passage + " Target fixture.")
        response = api.post(
            "/api/v1/ai/conversations", json={"title": "Recovery fixture"}
        )
        assert response.status_code == 201
        conversation = response.json()["id"]

        def run(tool):
            response = api.post(
                f"/api/v1/ai/conversations/{conversation}/messages",
                json={
                    "operation_id": str(uuid4()),
                    "content": "Run the selected recovery fixture tool.",
                    "attachments": [target],
                    "tool": tool,
                },
            )
            assert response.status_code == 202
            run_id = response.json()["run"]["id"]
            for _ in range(90):
                detail = api.get(f"/api/v1/ai/conversations/{conversation}").json()
                current = next(row for row in detail["runs"] if row["id"] == run_id)
                if current["status"] == "COMPLETED":
                    call = next(
                        row for row in detail["tool_calls"] if row["run_id"] == run_id
                    )
                    return next(
                        row["content"]
                        for row in detail["tool_results"]
                        if row["tool_call_id"] == call["id"]
                    )
                if current["status"] in ("FAILED", "UNAVAILABLE", "CANCELLED"):
                    raise RuntimeError(
                        "Recovery tool failed: " + str(current.get("error_code"))
                    )
                time.sleep(1)
            raise RuntimeError("Recovery tool timed out")

        run({"name": "document.read", **target})
        analysis = run({"name": "similarity.analyze", **target})
        match = analysis["analysis"]["matches"]["items"][0]
        proposal = run(
            {
                "name": "similarity.resolve",
                **target,
                "match_id": match["id"],
                "action": "add_citation",
                "citation": "(Recovery fixture source, 2026)",
                "rationale": "Record attribution in the isolated recovery test.",
            }
        )
        response = api.post(
            f"/api/v1/ai/receipts/{proposal['receipt_id']}/decision",
            json={
                "decision": "ACCEPTED",
                "candidate_sha256": proposal["candidate_sha256"],
            },
        )
        assert response.status_code == 200
        receipt = response.json()
        profile = api.post(
            "/api/v1/ai/voice-profiles",
            json={
                "name": "Recovery fixture style",
                "samples": [target],
                "approved": True,
            },
        )
        assert profile.status_code == 201
        evidence = {
            "conversation_id": conversation,
            "receipt_id": proposal["receipt_id"],
            "result_version_id": receipt["result_version_id"],
            "result_sha256": receipt["result_sha256"],
            "voice_profile_id": profile.json()["id"],
            "model_executed": False,
            "result": "PASS",
        }
        state["agent_fixture"] = evidence
        save(PRIVATE / "fixture.json", state)
        save(PUBLIC / "agent-fixture.json", evidence)


def snapshot():
    state = load(PRIVATE / "fixture.json")
    backup = PRIVATE / "backup"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_CONFIG, backup / "compose.json")
    (backup / "compose.json").chmod(0o600)
    for filename in ("minio-app-policy.json", "minio-maintenance-policy.json"):
        shutil.copy2(ROOT / "infrastructure" / filename, backup / filename)
    shutil.copytree(ROOT / "config/models", backup / "model-config", dirs_exist_ok=True)
    for path in (backup / "model-config").rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    for filename in ("minio-app-policy.json", "minio-maintenance-policy.json"):
        (backup / filename).chmod(0o600)
    start = time.monotonic()
    compose(
        SOURCE_CONFIG, "stop", "backend", "celery-worker", "celery-beat", timeout=180
    )
    try:
        with (backup / "postgres.dump").open("wb") as handle:
            compose(
                SOURCE_CONFIG,
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "azaeron",
                "-d",
                "azaeron",
                "-Fc",
                stdout=handle,
                timeout=300,
            )
        state["schema"] = (
            compose(
                SOURCE_CONFIG,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "azaeron",
                "-d",
                "azaeron",
                "-Atc",
                "SELECT version_num FROM alembic_version",
                stdout=subprocess.PIPE,
            )
            .stdout.decode()
            .strip()
        )
        state["relations"] = relational_evidence(
            SOURCE_CONFIG, source_port("postgres", 5432)
        )
        store = storage(SOURCE_CONFIG, source_port("minio", 9000))
        assert store.bucket_exists(BUCKET)
        # MinIO releases and SDKs report disabled versioning as either an
        # omitted status or the explicit S3-compatible value "Off".
        assert store.get_bucket_versioning(BUCKET).status in (None, "Off")
        objects = []
        all_items = list(
            store.list_objects(BUCKET, recursive=True, include_version=True)
        )
        for index, item in enumerate(all_items):
            if item.is_delete_marker:
                raise RuntimeError(
                    "Delete markers require the version-preserving recovery path"
                )
            response = store.get_object(
                BUCKET, item.object_name, version_id=item.version_id
            )
            try:
                body = response.read()
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )
            finally:
                response.close()
                response.release_conn()
            filename = f"{index:06d}.bin"
            (backup / filename).write_bytes(body)
            (backup / filename).chmod(0o600)
            objects.append(
                {
                    "key": item.object_name,
                    "file": filename,
                    "size": len(body),
                    "sha256": digest(body),
                    "content_type": content_type,
                }
            )
        save(backup / "objects.json", objects)
        state["snapshot_at"] = now()
        state["dump_sha256"] = digest((backup / "postgres.dump").read_bytes())
        state["objects_manifest_sha256"] = digest(
            (backup / "objects.json").read_bytes()
        )
        save(PRIVATE / "fixture.json", state)
        save(
            PUBLIC / "backup.json",
            {
                "snapshot_at": state["snapshot_at"],
                "postgres_dump_bytes": (backup / "postgres.dump").stat().st_size,
                "postgres_dump_sha256": state["dump_sha256"],
                "object_count": len(objects),
                "object_bytes": sum(x["size"] for x in objects),
                "object_manifest_sha256": state["objects_manifest_sha256"],
                "compose_sha256": digest((backup / "compose.json").read_bytes()),
                "policy_sha256": {
                    name: digest((backup / name).read_bytes())
                    for name in (
                        "minio-app-policy.json",
                        "minio-maintenance-policy.json",
                    )
                },
                "model_registry_sha256": digest(
                    (backup / "model-config/registry.json").read_bytes()
                ),
                "bucket_versioning": "disabled",
                "relations": state["relations"],
                "pause_seconds": round(time.monotonic() - start, 3),
                "result": "PASS",
            },
        )
    finally:
        compose(
            SOURCE_CONFIG,
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "backend",
            "celery-worker",
            "celery-beat",
            timeout=180,
        )


def target_config():
    config = load(PRIVATE / "backup/compose.json")
    config["name"] = TARGET
    services = config["services"]
    keep = {
        "postgres",
        "redis",
        "minio",
        "minio-init",
        "backend",
        "celery-worker",
        "frontend",
        "migrate",
        "celery-beat",
        "verification",
    }
    config["services"] = {
        name: value for name, value in services.items() if name in keep
    }
    config["volumes"] = {
        name: value
        for name, value in config["volumes"].items()
        if name in {"postgres_data", "redis_data", "minio_data"}
    }
    for name, value in config["volumes"].items():
        value["name"] = f"{TARGET}_{name}"
    for name, value in config["networks"].items():
        value["name"] = f"{TARGET}_{name}"
        # A host with exhausted automatic pools can assign an explicit private
        # subnet; Docker still rejects overlap with any existing network.
        subnet = os.environ.get("VERITY_RECOVERY_SUBNET")
        if subnet:
            network = ipaddress.ip_network(subnet)
            if not network.is_private:
                raise ValueError("Recovery subnet must be private")
            value["ipam"] = {"config": [{"subnet": str(network)}]}
    source = load(PRIVATE / "backup/compose.json")
    assert all(
        value["name"] not in {item["name"] for item in source["volumes"].values()}
        for value in config["volumes"].values()
    )
    assert all(
        value["name"] not in {item["name"] for item in source["networks"].values()}
        for value in config["networks"].values()
    )
    for service in config["services"].values():
        service.pop("depends_on", None)
    if POSTGRES_IMAGE:
        config["services"]["postgres"]["image"] = POSTGRES_IMAGE
        config["services"]["postgres"].pop("build", None)
        config["services"]["postgres"]["environment"][
            "AZAERON_DATABASE_BOOTSTRAP"
        ] = "logical-restore"
    for name in ("backend", "celery-worker"):
        for mount in config["services"][name].get("volumes", []):
            if mount.get("target") == "/etc/azaeron/models":
                mount["source"] = str(PRIVATE / "backup/model-config")
    for mount in config["services"]["minio-init"].get("volumes", []):
        if mount.get("target", "").startswith("/config/minio-"):
            mount["source"] = str(PRIVATE / "backup" / Path(mount["target"]).name)
    config["services"]["postgres"]["ports"] = [
        {
            "host_ip": "127.0.0.1",
            "target": 5432,
            "published": "15432",
            "protocol": "tcp",
        }
    ]
    config["services"]["minio"]["ports"] = [
        {
            "host_ip": "127.0.0.1",
            "target": 9000,
            "published": "19700",
            "protocol": "tcp",
        },
        {
            "host_ip": "127.0.0.1",
            "target": 9001,
            "published": "19701",
            "protocol": "tcp",
        },
    ]
    config["services"]["backend"]["ports"] = [
        {
            "host_ip": "127.0.0.1",
            "target": 8000,
            "published": "19710",
            "protocol": "tcp",
        }
    ]
    config["services"]["frontend"]["ports"] = [
        {
            "host_ip": "127.0.0.1",
            "target": 3000,
            "published": "14710",
            "protocol": "tcp",
        }
    ]
    env = config["services"]["backend"]["environment"]
    env["MINIO_PUBLIC_ENDPOINT"] = "localhost:19700"
    env["CORS_ORIGINS"] = "http://localhost:14710"
    env["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
    config["services"]["frontend"]["environment"]["API_URL"] = "http://backend:8000"
    for name in ("backend", "celery-worker"):
        config["services"][name]["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] = ""
    target = PRIVATE / "target-compose.json"
    save(target, config)
    return target


def restore():
    state = load(PRIVATE / "fixture.json")
    backup = PRIVATE / "backup"
    assert state["dump_sha256"] == digest((backup / "postgres.dump").read_bytes())
    assert state["objects_manifest_sha256"] == digest(
        (backup / "objects.json").read_bytes()
    )
    config = target_config()
    # Never restore into a pre-existing volume, including a prior failed trial.
    # Preserve it for diagnosis and select a new target project on retry.
    for volume in load(config)["volumes"].values():
        exists = (
            subprocess.run(
                ["docker", "volume", "inspect", volume["name"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if exists:
            raise RuntimeError("Recovery requires entirely new target volumes")
    start = time.monotonic()
    compose(
        config,
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "postgres",
        "redis",
        "minio",
        timeout=180,
    )
    for service, volume in (
        ("postgres", "postgres_data"),
        ("redis", "redis_data"),
        ("minio", "minio_data"),
    ):
        mounts = json.loads(
            subprocess.check_output(
                [
                    "docker",
                    "inspect",
                    f"{TARGET}-{service}-1",
                    "--format",
                    "{{json .Mounts}}",
                ]
            )
        )
        assert any(
            mount.get("Type") == "volume" and mount.get("Name") == f"{TARGET}_{volume}"
            for mount in mounts
        ), f"Unexpected shared recovery mount: {service}"
    for _ in range(60):
        try:
            with pg_conn(config, 15432) as db:
                db.execute("SELECT 1")
            break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Restored PostgreSQL did not start")
    with pg_conn(config, 15432) as db:
        db.execute(
            sql.SQL("CREATE ROLE azaeron_app LOGIN PASSWORD {}").format(
                sql.Literal(
                    load(backup / "compose.json")["services"]["migrate"]["environment"][
                        "APP_DB_PASSWORD"
                    ]
                )
            )
        )
    with (backup / "postgres.dump").open("rb") as handle:
        compose(
            config,
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "azaeron",
            "-d",
            "azaeron",
            "--exit-on-error",
            stdin=handle,
            timeout=360,
        )
    if "relations" in state:
        assert relational_evidence(config, 15432) == state["relations"]
    compose(config, "run", "--rm", "--no-deps", "-T", "migrate", timeout=180)
    compose(config, "run", "--rm", "--no-deps", "-T", "minio-init", timeout=120)
    target_store = storage(config, 19700)
    assert target_store.bucket_exists(BUCKET)
    objects = load(backup / "objects.json")
    for item in objects:
        body = (backup / item["file"]).read_bytes()
        assert len(body) == item["size"] and digest(body) == item["sha256"]
        target_store.put_object(
            BUCKET,
            item["key"],
            io.BytesIO(body),
            len(body),
            content_type=item["content_type"],
        )
    with pg_conn(config, 15432) as db:
        assert (
            db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            == state["schema"]
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s", (state["user_id"],)
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM document_versions WHERE id=%s",
                (state["version_id"],),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s", (state["survivor_user_id"],)
            ).fetchone()[0]
            == 1
        )
        survivor = db.execute(
            "SELECT content_hash FROM document_versions WHERE id=%s",
            (state["survivor_version_id"],),
        ).fetchone()
        assert survivor and survivor[0] == state["survivor_content_sha256"]
    state["restore_started_at"] = now()
    state["restore_pre_replay_seconds"] = round(time.monotonic() - start, 3)
    save(PRIVATE / "fixture.json", state)
    save(
        PUBLIC / "restore-pre-replay.json",
        {
            "restore_seconds": state["restore_pre_replay_seconds"],
            "restored_object_count": len(objects),
            "schema": state["schema"],
            "pre_replay_deleted_account_present": True,
            "api_exposed": False,
            "relations_verified": state.get("relations", {}),
            "migrations": "PASS",
            "postgres_image": load(config)["services"]["postgres"]["image"],
            "result": "PASS",
        },
    )


def erase():
    state = load(PRIVATE / "fixture.json")
    assert "snapshot_at" in state
    if "erasure_id" not in state:
        origin = {"Origin": f"http://localhost:{source_port('frontend', 3000)}"}
        with httpx.Client(
            base_url=f"http://localhost:{source_port('backend', 8000)}",
            headers=origin,
            timeout=45,
        ) as api:
            response = api.post(
                "/api/v1/auth/login",
                json={"email": state["email"], "password": state["password"]},
            )
            assert response.status_code == 200, response.status_code
            response = api.post(
                "/api/v1/privacy/erasures",
                json={
                    "scope": "account",
                    "target_id": state["user_id"],
                    "current_password": state["password"],
                    "confirmation": "ERASE",
                },
            )
            assert response.status_code == 202, response.status_code
            result = response.json()
            assert api.get("/api/v1/auth/me").status_code == 401
            state["erasure_id"] = result["id"]
            state["erasure_receipt"] = result["receipt"]
            state["erasure_requested_at"] = now()
            save(PRIVATE / "fixture.json", state)
    erasure_id = str(UUID(state["erasure_id"]))
    for _ in range(610):
        status = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(SOURCE_CONFIG),
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "azaeron",
                "-d",
                "azaeron",
                "-Atc",
                f"SELECT status FROM privacy_erasures WHERE id='{erasure_id}'",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status.returncode == 0 and status.stdout.strip() == "COMPLETED":
            break
        if status.returncode == 0 and status.stdout.strip() == "FAILED":
            raise RuntimeError("Live post-backup erasure failed")
        time.sleep(1)
    else:
        raise RuntimeError("Live post-backup erasure did not complete")
    with subprocess.Popen(
        [
            "docker",
            "compose",
            "-f",
            str(SOURCE_CONFIG),
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "azaeron",
            "-d",
            "azaeron",
            "-At",
            "-c",
            "SELECT row_to_json(p) FROM (SELECT id,scope,target_id,requester_id,organization_id,receipt_digest,status,document_ids,organization_ids,object_keys,prefixes,not_before,completed_at FROM privacy_erasures ORDER BY created_at) p",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ) as process:
        output, errors = process.communicate(timeout=60)
        if process.returncode:
            raise RuntimeError("Tombstone export failed") from None
    ledger = [json.loads(line) for line in output.decode().splitlines() if line]
    assert any(
        row["id"] == state["erasure_id"] and row["status"] == "COMPLETED"
        for row in ledger
    )
    save(PRIVATE / "latest-tombstones.json", ledger)
    state["erasure_completed_at"] = now()
    save(PRIVATE / "fixture.json", state)
    save(
        PUBLIC / "tombstone-export.json",
        {
            "exported_at": state["erasure_completed_at"],
            "count": len(ledger),
            "sha256": digest((PRIVATE / "latest-tombstones.json").read_bytes()),
            "post_backup_erasure_id": state["erasure_id"],
            "result": "PASS",
        },
    )


def replay():
    state = load(PRIVATE / "fixture.json")
    ledger = load(PRIVATE / "latest-tombstones.json")
    config = PRIVATE / "target-compose.json"
    target_store = storage(config, 19700)
    started = time.monotonic()
    replayed = 0
    removed = 0
    for item in ledger:
        assert item["status"] == "COMPLETED"
        with pg_conn(config, 15432) as db:
            prior = db.execute(
                "SELECT status FROM privacy_erasures WHERE id=%s", (item["id"],)
            ).fetchone()
            if prior is None:
                # This trusted operator step runs before the restored API is exposed.
                db.execute(
                    "SELECT set_config('app.current_user_id',%s,true)",
                    (item["requester_id"],),
                )
                db.execute(
                    "SELECT set_config('app.current_organization_id',%s,true)",
                    (item["organization_id"] or "",),
                )
                result = db.execute(
                    "SELECT app.privacy_request(%s,%s,%s,%s)",
                    (
                        item["id"],
                        item["scope"],
                        item["target_id"],
                        item["receipt_digest"],
                    ),
                ).fetchone()[0]
                assert result == item["id"]
                # The original eight-minute grace has elapsed; all source URLs
                # were issued before the backup and are expired now.
                db.execute(
                    "UPDATE privacy_erasures SET not_before=%s WHERE id=%s",
                    (item["not_before"], item["id"]),
                )
                db.execute("SELECT app.privacy_erase_database(%s)", (item["id"],))
                replayed += 1
            elif prior[0] != "COMPLETED":
                raise RuntimeError("Restored tombstone has an unresolved state")
        keys = set(item["object_keys"])
        prefixes = set(item["prefixes"])
        for key in list(keys):
            match = re.fullmatch(
                r"versions/uploads/(.+)/[0-9a-f]{64}\.([a-z0-9]+)", key
            )
            if match:
                keys.add(f"uploads/{match[1]}.{match[2]}")
        assert all(
            value and not value.startswith("/") and ".." not in value.split("/")
            for value in keys | prefixes
        )
        for object_item in list(
            target_store.list_objects(BUCKET, recursive=True, include_version=True)
        ):
            if object_item.object_name in keys or any(
                object_item.object_name.startswith(prefix) for prefix in prefixes
            ):
                target_store.remove_object(
                    BUCKET, object_item.object_name, version_id=object_item.version_id
                )
                removed += 1
        for object_item in target_store.list_objects(
            BUCKET, recursive=True, include_version=True
        ):
            assert object_item.object_name not in keys and not any(
                object_item.object_name.startswith(prefix) for prefix in prefixes
            )
        with pg_conn(config, 15432) as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM documents WHERE id=ANY(%s)",
                    (item["document_ids"],),
                ).fetchone()[0]
                == 0
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM organizations WHERE id=ANY(%s)",
                    (item["organization_ids"],),
                ).fetchone()[0]
                == 0
            )
            if item["scope"] == "account":
                assert (
                    db.execute(
                        "SELECT count(*) FROM users WHERE id=%s", (item["target_id"],)
                    ).fetchone()[0]
                    == 0
                )
            if prior is None:
                assert (
                    db.execute(
                        "SELECT app.privacy_result(%s,true,%s)", (item["id"], removed)
                    ).fetchone()[0]
                    == "COMPLETED"
                )
    # Verify every referenced immutable object and its SHA-256, not just the fixture.
    with pg_conn(config, 15432) as db:
        versions = db.execute(
            "SELECT id,document_id,previous_version_id,version_number,storage_path,content_hash FROM document_versions"
        ).fetchall()
        assert any(row[0] == state["survivor_version_id"] for row in versions)
        version_ids = {row[0]: (row[1], row[3]) for row in versions}
        for version_id, document_id, parent, number, key, content_hash in versions:
            if parent is not None:
                assert (
                    parent in version_ids
                    and version_ids[parent][0] == document_id
                    and version_ids[parent][1] < number
                )
            response = target_store.get_object(BUCKET, key)
            try:
                assert digest(response.read()) == content_hash, version_id
            finally:
                response.close()
                response.release_conn()
        schema = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert schema == state["schema"]
        assert db.execute("SELECT count(*) FROM privacy_erasures").fetchone()[0] == len(
            ledger
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s", (state["user_id"],)
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s",
                (state["survivor_user_id"],),
            ).fetchone()[0]
            == 1
        )
        assert (
            db.execute(
                "SELECT count(*) FROM documents WHERE id=%s",
                (state["survivor_document_id"],),
            ).fetchone()[0]
            == 1
        )
    app_password = load(PRIVATE / "backup/compose.json")["services"]["migrate"][
        "environment"
    ]["APP_DB_PASSWORD"]
    with psycopg.connect(
        host="127.0.0.1",
        port=15432,
        dbname="azaeron",
        user="azaeron_app",
        password=app_password,
    ) as app_db:
        assert app_db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
    # Only after tombstones and all content hashes pass can serving start.
    compose(
        config,
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "celery-worker",
        "backend",
        "frontend",
        timeout=180,
    )
    for _ in range(90):
        try:
            health = httpx.get("http://localhost:19710/health/ready", timeout=3)
            front = httpx.get("http://localhost:14710/login", timeout=3)
            if health.status_code == 200 and front.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Restored application readiness did not become healthy")
    with httpx.Client(base_url="http://localhost:19710", timeout=8) as api:
        assert api.get("/api/v1/auth/me").status_code == 401
        result = api.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://localhost:14710"},
            json={"email": state["email"], "password": state["password"]},
        )
        assert result.status_code == 401, result.status_code
    save(
        PUBLIC / "recovery-result.json",
        {
            "result": "PASS",
            "completed_at": now(),
            "active_restore_and_replay_seconds": round(
                state["restore_pre_replay_seconds"] + time.monotonic() - started, 3
            ),
            "replay_to_readiness_seconds": round(time.monotonic() - started, 3),
            "latest_tombstones": len(ledger),
            "post_backup_tombstones_replayed": replayed,
            "objects_removed_after_replay": removed,
            "verified_immutable_versions": len(versions),
            "survivor_version_present_and_hash_verified": True,
            "schema": schema,
            "runtime_rls_without_tenant": "PASS",
            "source_snapshot_at": state["snapshot_at"],
            "last_erasure_completed_at": state["erasure_completed_at"],
            "api_and_frontend_ready": True,
            "erased_account_login_rejected": True,
            "data_loss_window_seconds_represented": round(
                (
                    datetime.fromisoformat(state["erasure_completed_at"])
                    - datetime.fromisoformat(state["snapshot_at"])
                ).total_seconds(),
                3,
            ),
            "rpo_rto": "measured local exercise only; production targets unproven",
        },
    )


def second_restore():
    """Back up the restored candidate and prove another fresh-volume recovery."""
    first = PRIVATE / "target-compose.json"
    assert load(PUBLIC / "recovery-result.json")["result"] == "PASS"
    state = load(PRIVATE / "fixture.json")
    backup = PRIVATE / "second-backup"
    backup.mkdir(mode=0o700, exist_ok=False)
    started = time.monotonic()
    compose(first, "stop", "backend", "celery-worker", "frontend", timeout=180)
    expected = relational_evidence(first, 15432)
    with (backup / "postgres.dump").open("wb") as handle:
        compose(
            first,
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            "azaeron",
            "-d",
            "azaeron",
            "-Fc",
            stdout=handle,
            timeout=300,
        )
    (backup / "postgres.dump").chmod(0o600)
    store = storage(first, 19700)
    objects = []
    for i, item in enumerate(store.list_objects(BUCKET, recursive=True)):
        response = store.get_object(BUCKET, item.object_name)
        try:
            body = response.read()
            content_type = response.headers.get(
                "Content-Type", "application/octet-stream"
            )
        finally:
            response.close()
            response.release_conn()
        path = backup / f"{i}.bin"
        path.write_bytes(body)
        path.chmod(0o600)
        objects.append(
            {
                "key": item.object_name,
                "file": path.name,
                "sha256": digest(body),
                "content_type": content_type,
            }
        )
    save(backup / "objects.json", objects)
    with pg_conn(first, 15432) as db:
        tombstones = db.execute(
            "SELECT row_to_json(t) FROM privacy_erasures t ORDER BY id"
        ).fetchall()
    # Retain first volumes and containers; stopping releases only this test's ports.
    compose(first, "stop", timeout=180)
    config = load(first)
    name = config["name"] + "-second"
    config["name"] = name
    for key, value in config["volumes"].items():
        value["name"] = f"{name}_{key}"
        if (
            subprocess.run(
                ["docker", "volume", "inspect", value["name"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        ):
            raise RuntimeError("Second restore requires new volumes")
    for key, value in config["networks"].items():
        value["name"] = f"{name}_{key}"
        value["ipam"] = {
            "config": [
                {
                    "subnet": os.environ.get(
                        "VERITY_SECOND_RESTORE_SUBNET", "172.30.128.0/24"
                    )
                }
            ]
        }
    if POSTGRES_IMAGE:
        config["services"]["postgres"]["image"] = POSTGRES_IMAGE
    config["services"]["postgres"]["environment"][
        "AZAERON_DATABASE_BOOTSTRAP"
    ] = "logical-restore"
    second = PRIVATE / "second-compose.json"
    save(second, config)
    compose(second, "up", "-d", "--no-deps", "--no-build", "postgres", "redis", "minio")
    for _ in range(60):
        try:
            with pg_conn(second, 15432) as db:
                db.execute("SELECT 1")
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("Second PostgreSQL did not start")
    with pg_conn(second, 15432) as db:
        db.execute(
            sql.SQL("CREATE ROLE azaeron_app LOGIN PASSWORD {}").format(
                sql.Literal(
                    config["services"]["migrate"]["environment"]["APP_DB_PASSWORD"]
                )
            )
        )
    with (backup / "postgres.dump").open("rb") as handle:
        compose(
            second,
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "azaeron",
            "-d",
            "azaeron",
            "--exit-on-error",
            stdin=handle,
            timeout=360,
        )
    assert relational_evidence(second, 15432) == expected
    compose(second, "run", "--rm", "--no-deps", "-T", "migrate")
    compose(second, "run", "--rm", "--no-deps", "-T", "minio-init")
    restored = storage(second, 19700)
    for item in objects:
        body = (backup / item["file"]).read_bytes()
        assert digest(body) == item["sha256"]
        restored.put_object(
            BUCKET,
            item["key"],
            io.BytesIO(body),
            len(body),
            content_type=item["content_type"],
        )
        response = restored.get_object(BUCKET, item["key"])
        try:
            assert digest(response.read()) == item["sha256"]
        finally:
            response.close()
            response.release_conn()
    with pg_conn(second, 15432) as db:
        assert (
            db.execute(
                "SELECT row_to_json(t) FROM privacy_erasures t ORDER BY id"
            ).fetchall()
            == tombstones
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s", (state["user_id"],)
            ).fetchone()[0]
            == 0
        )
        assert (
            db.execute(
                "SELECT count(*) FROM users WHERE id=%s", (state["survivor_user_id"],)
            ).fetchone()[0]
            == 1
        )
    compose(
        second,
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "backend",
        "celery-worker",
        "frontend",
    )
    for _ in range(90):
        try:
            if (
                httpx.get("http://localhost:19710/health/ready", timeout=3).status_code
                == 200
            ):
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Second restored application did not become ready")
    save(
        PUBLIC / "second-restore.json",
        {
            "result": "PASS",
            "postgres_image": config["services"]["postgres"]["image"],
            "seconds": round(time.monotonic() - started, 3),
            "relations": expected,
            "dump_sha256": digest((backup / "postgres.dump").read_bytes()),
            "object_count": len(objects),
            "object_hashes_verified": True,
            "tombstones_preserved": len(tombstones),
            "erased_account_absent": True,
            "surviving_account_present": True,
            "api_ready": True,
            "volumes": [v["name"] for v in config["volumes"].values()],
            "production_rpo_rto_certified": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "phase",
        choices=[
            "prepare",
            "agents",
            "snapshot",
            "restore",
            "erase",
            "replay",
            "second",
        ],
    )
    phase = parser.parse_args().phase
    PUBLIC.mkdir(parents=True, exist_ok=True)
    {
        "prepare": fixture,
        "agents": agent_fixture,
        "snapshot": snapshot,
        "restore": restore,
        "erase": erase,
        "replay": replay,
        "second": second_restore,
    }[phase]()
    print(phase, "PASS")
