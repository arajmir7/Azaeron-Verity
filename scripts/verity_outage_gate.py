"""Exercise readiness failure and recovery for isolated stateful dependencies."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compose = ["docker", "compose", "-f", str(args.compose.resolve())]
    config = json.loads(
        subprocess.check_output(compose + ["config", "--format", "json"])
    )
    primary = json.loads(
        subprocess.check_output(["docker", "compose", "config", "--format", "json"])
    )
    primary_volumes = {
        item.get("name", name) for name, item in primary.get("volumes", {}).items()
    }
    if config["name"] == primary["name"] or any(
        item.get("external") or item.get("name", name) in primary_volumes
        for name, item in config.get("volumes", {}).items()
    ):
        parser.error("Use a project with private volumes, never the primary stack")
    port = next(
        item["published"]
        for item in config["services"]["backend"]["ports"]
        if item["target"] == 8000
    )
    url = f"http://127.0.0.1:{port}/health/ready"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results = []

    def status() -> int | None:
        try:
            # Readiness checks required services sequentially and may each
            # consume their bounded health timeout during an outage. Give the
            # endpoint enough time to return its deliberate 503 response.
            with urlopen(url, timeout=15) as response:
                return response.status
        except URLError as exc:
            if getattr(exc, "code", None) is not None:
                return int(exc.code)
            return None

    def await_status(expected: int, timeout: int) -> tuple[int | None, float]:
        start = time.monotonic()
        seen = None
        while time.monotonic() - start < timeout:
            seen = status()
            if seen == expected:
                break
            time.sleep(1)
        return seen, round(time.monotonic() - start, 3)

    if status() != 200:
        parser.error("Source readiness is not 200 before the outage drill")
    for service in ("redis", "minio", "postgres"):
        stopped = False
        try:
            subprocess.run(compose + ["stop", "-t", "10", service], check=True)
            stopped = True
            outage_status, outage_seconds = await_status(503, 20)
        finally:
            if stopped:
                subprocess.run(compose + ["start", service], check=True)
        recovered_status, recovery_seconds = await_status(200, 90)
        result = {
            "dependency": service,
            "outage_status": outage_status,
            "outage_seconds": outage_seconds,
            "recovered_status": recovered_status,
            "recovery_seconds": recovery_seconds,
            "status": (
                "PASS" if outage_status == 503 and recovered_status == 200 else "FAIL"
            ),
        }
        results.append(result)
        args.output.write_text(
            json.dumps(
                {
                    "executed_utc": datetime.now(timezone.utc).isoformat(),
                    "results": results,
                },
                indent=2,
            )
            + "\n"
        )
        print(
            f"{service}: {result['status']} ({outage_status} → {recovered_status})",
            flush=True,
        )
        if result["status"] != "PASS":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
