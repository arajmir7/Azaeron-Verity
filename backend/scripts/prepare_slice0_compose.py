"""Resolve an isolated Compose project without touching the primary volumes.

Run from the repository root. The output includes development configuration and
is written with owner-only permissions; never commit the resolved file.
"""

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="azaeron-slice0-gate")
    parser.add_argument("--port-offset", type=int, default=100)
    parser.add_argument("--output", default="/tmp/azaeron-slice0-compose.json")
    parser.add_argument(
        "--identity-mail",
        action="store_true",
        help="Enable the isolated local SMTP sink and periodic sender",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", args.project):
        parser.error("Use a lowercase Compose project name")
    repository = Path(__file__).resolve().parents[2]
    config = json.loads(
        subprocess.check_output(
            ["docker", "compose", "--profile", "*", "config", "--format", "json"],
            cwd=repository,
        )
    )
    if args.project == config.get("name"):
        parser.error("The verification project must differ from the primary project")
    config["name"] = args.project
    for name, service in config["services"].items():
        service.pop("container_name", None)
        if service.get("build"):
            service["image"] = f"{args.project}-{name}"
        for port in service.get("ports", []):
            if port.get("published"):
                published = int(port["published"]) + args.port_offset
                if not 1024 <= published <= 65535:
                    parser.error("Published port is outside the allowed range")
                port["published"] = str(published)
                port["host_ip"] = "127.0.0.1"
    for section in ("volumes", "networks"):
        for name, resource in config.get(section, {}).items():
            if resource.get("external"):
                parser.error(
                    "External volumes/networks need an explicit isolated configuration"
                )
            resource["name"] = f"{args.project}_{name}"
    config["services"]["backend"]["environment"].update(
        {
            "CORS_ORIGINS": f"http://localhost:{3000 + args.port_offset}",
            "MINIO_PUBLIC_ENDPOINT": f"localhost:{9000 + args.port_offset}",
        }
    )
    if args.identity_mail:
        for service_name in ("backend", "celery-worker"):
            config["services"][service_name]["environment"].update(
                {
                    "EMAIL_ENABLED": "true",
                    "EMAIL_PUBLIC_URL": f"http://localhost:{3000 + args.port_offset}",
                    "SMTP_HOST": "mailpit",
                    "SMTP_PORT": "1025",
                    "SMTP_STARTTLS": "false",
                }
            )
            config["services"][service_name].setdefault("depends_on", {})["mailpit"] = {
                "condition": "service_started"
            }
        config["services"]["mailpit"].pop("profiles", None)
        config["services"]["backend"]["depends_on"]["celery-beat"] = {
            "condition": "service_started"
        }
    frontend = config["services"]["frontend"]
    frontend["environment"].update(
        {"API_URL": "http://backend:8000", "NEXT_PUBLIC_API_URL": ""}
    )
    frontend["build"].setdefault("args", {}).update(
        {"API_URL": "http://backend:8000", "NEXT_PUBLIC_API_URL": ""}
    )
    verification = deepcopy(config["services"]["backend"])
    verification["image"] = f"{args.project}-verification"
    verification["build"]["target"] = "verification"
    verification["profiles"] = ["verification"]
    for field in ("ports", "healthcheck", "depends_on"):
        verification.pop(field, None)
    config["services"]["verification"] = verification
    output = Path(args.output)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as destination:
        json.dump(config, destination, indent=2)
    os.chmod(output, 0o600)
    print(f"Wrote isolated project {args.project} to {output}")


if __name__ == "__main__":
    main()
