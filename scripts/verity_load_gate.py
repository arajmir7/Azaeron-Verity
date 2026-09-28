#!/usr/bin/env python3
"""Run a synthetic profile and sample actual isolated container resources."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def command(args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 8])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.compose.read_text())
    primary = json.loads(
        subprocess.check_output(["docker", "compose", "config", "--format", "json"])
    )
    assert config["name"] != primary["name"], "An isolated Compose project is required"
    env = dict(
        os.environ,
        METRICS_TOKEN=config["services"]["backend"]["environment"]["METRICS_TOKEN"],
    )
    origin = config["services"]["backend"]["environment"]["CORS_ORIGINS"].split(
        ","
    )[0].strip()
    prefix = ["docker", "compose", "-f", str(args.compose)]
    files = sorted(Path("backend/app").rglob("*.py"))
    source = hashlib.sha256(
        "".join(
            str(p) + hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        ).encode()
    ).hexdigest()
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cpu": command(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "host_memory_bytes": int(command(["sysctl", "-n", "hw.memsize"])),
        "os": command(["sw_vers"]),
        "docker": command(
            [
                "docker",
                "info",
                "--format",
                "{{.ServerVersion}} {{.OSType}} {{.Architecture}} {{.NCPU}} {{.MemTotal}}",
            ]
        ),
        "application_source_digest": source,
        "images": {
            name: command(
                [
                    "docker",
                    "image",
                    "inspect",
                    config["services"][name]["image"],
                    "--format",
                    "{{.Id}}",
                ]
            )
            for name in ["backend", "frontend"]
        },
    }
    (args.output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    containers = [
        command(["docker", "compose", "-f", str(args.compose), "ps", "-q", name])
        for name in ["backend", "celery-worker", "postgres", "redis", "minio"]
    ]
    if any(not container for container in containers):
        raise SystemExit("Every isolated application-load service must be running")
    with (args.output / "profile.log").open("w") as log, (
        args.output / "resources.jsonl"
    ).open("w") as resource:
        process = subprocess.Popen(
            [
                *prefix,
                "run",
                "--rm",
                "--no-deps",
                "-e",
                "METRICS_TOKEN",
                "-v",
                str(args.output.resolve()) + ":/evidence",
                "-T",
                "verification",
                "python",
                "-m",
                "scripts.application_load",
                "--requests",
                str(args.requests),
                "--origin",
                origin,
                "--concurrency",
                *[str(n) for n in args.concurrency],
                "--output",
                "/evidence/profile.json",
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        while process.poll() is None:
            sample = subprocess.run(
                [
                    "docker",
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{json .}}",
                    *containers,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            resource.write(
                json.dumps(
                    {
                        "time": time.time(),
                        "exit_code": sample.returncode,
                        "containers": [
                            json.loads(line)
                            for line in sample.stdout.splitlines()
                            if line.strip()
                        ],
                    }
                )
                + "\n"
            )
            resource.flush()
            time.sleep(0.2)
    metadata["completed_at"] = datetime.now(timezone.utc).isoformat()
    metadata["exit_code"] = process.returncode
    (args.output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Application load exit:", process.returncode)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
