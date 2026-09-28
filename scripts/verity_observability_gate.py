#!/usr/bin/env python3
"""Verify an isolated Compose telemetry deployment without persisting credentials."""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get(url, headers=None):
    with urlopen(Request(url, headers=headers or {}), timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api", default="http://localhost:9700")
    parser.add_argument("--prometheus", default="http://localhost:10790")
    parser.add_argument("--grafana", default="http://localhost:4701")
    parser.add_argument("--jaeger", default="http://localhost:18386")
    args = parser.parse_args()
    config = json.loads(args.compose.read_text())
    primary = json.loads(
        subprocess.check_output(["docker", "compose", "config", "--format", "json"])
    )
    assert config["name"] != primary["name"], "Isolated project required"

    def endpoint(service, target, fallback):
        published = next(
            (
                port["published"]
                for port in config["services"][service].get("ports", [])
                if port["target"] == target
            ),
            None,
        )
        return f"http://127.0.0.1:{published}" if published else fallback

    args.api = endpoint("backend", 8000, args.api)
    args.prometheus = endpoint("prometheus", 9090, args.prometheus)
    args.grafana = endpoint("grafana", 3000, args.grafana)
    args.jaeger = endpoint("jaeger", 16686, args.jaeger)
    evidence = json.loads((args.output / "browser-correlation.json").read_text())
    checks = {}
    backend = config["services"]["backend"]["environment"]
    try:
        with urlopen(args.api + "/metrics", timeout=10):
            pass
        raise AssertionError("Unauthenticated metrics unexpectedly allowed")
    except HTTPError as error:
        assert error.code == 401
    checks["metrics_authentication"] = "PASS"
    targets = get(args.prometheus + "/api/v1/targets")["data"]["activeTargets"]
    assert {t["labels"]["job"] for t in targets if t["health"] == "up"} >= {
        "azaeron-backend",
        "azaeron-worker",
    }
    checks["scrape_targets"] = [
        {k: t["labels"][k] for k in ("job", "instance")} for t in targets
    ]
    rules = get(args.prometheus + "/api/v1/rules")["data"]["groups"]
    alert_names = [
        r["name"] for g in rules for r in g["rules"] if r["type"] == "alerting"
    ]
    assert len(alert_names) >= 13
    assert all(r["health"] == "ok" for g in rules for r in g["rules"])
    checks["loaded_alerts"] = alert_names
    password = config["services"]["grafana"]["environment"][
        "GF_SECURITY_ADMIN_PASSWORD"
    ]
    authorization = {
        "Authorization": "Basic "
        + base64.b64encode(("admin:" + password).encode()).decode()
    }
    dashboard = get(
        args.grafana + "/api/dashboards/uid/verity-operations", authorization
    )
    assert len(dashboard["dashboard"]["panels"]) >= 13
    checks["provisioned_dashboard"] = dashboard["dashboard"]["title"]
    trace_url = args.jaeger + "/api/traces/" + evidence["trace_id"]
    before = get(trace_url)["data"][0]
    assert evidence["canary"] not in json.dumps(before)
    subprocess.run(
        ["docker", "compose", "-f", str(args.compose), "restart", "jaeger"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    for attempt in range(30):
        try:
            after = get(trace_url)["data"][0]
            break
        except (OSError, IndexError):
            time.sleep(1)
    else:
        raise AssertionError("Trace store did not recover")
    assert {s["spanID"] for s in before["spans"]} <= {
        s["spanID"] for s in after["spans"]
    }
    checks["trace_persistence_after_restart"] = "PASS"
    logs = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(args.compose),
            "logs",
            "--no-color",
            "--since",
            "30m",
            "backend",
            "celery-worker",
            "frontend",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert evidence["canary"] not in logs
    assert backend["METRICS_TOKEN"] not in logs
    checks["content_and_metrics_secret_absent_from_logs"] = "PASS"
    query = urlencode({"query": 'min(azaeron_worker_health{job="azaeron-backend"})'})
    result = get(args.prometheus + "/api/v1/query?" + query)["data"]["result"]
    assert result and float(result[0]["value"][1]) >= 1
    checks["all_required_queues_have_consumers"] = "PASS"
    report = {
        "result": "PASS",
        "scope": "isolated self-hosted telemetry, not production SLO compliance",
        "checks": checks,
        "model_runtime": "BLOCKED: approved model and hardware unavailable",
    }
    (args.output / "operational.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
