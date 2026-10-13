#!/usr/bin/env python3
"""Independently check recorded technical evidence without model inference."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / "qwen-technical-32case-20261013"
PRIVATE = ROOT / ".verity-local/qwen-mixed-4-6-20261013"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip('"\'`').rstrip(". ")).casefold()


def score(case: dict, response: str) -> int:
    if case["kind"] == "exact":
        return int(norm(response) == norm(case["expected"]))
    return int(all(part in response for part in case["required"]) and all(part not in response for part in case["forbidden"]))


def verify_run(raw_path: Path, summary_path: Path, fixtures: dict) -> dict:
    summary = json.loads(summary_path.read_bytes())
    if sha(raw_path) != summary["private_raw_sha256"]:
        raise RuntimeError("private result hash mismatch: " + str(raw_path))
    raw = json.loads(raw_path.read_bytes())
    if [item["id"] for item in raw["records"]["tasks"]] != [case["id"] for case in fixtures["tasks"]]:
        raise RuntimeError("task order changed")
    if [item["id"] for item in raw["records"]["stopping"]] != [case["id"] for case in fixtures["stopping"]]:
        raise RuntimeError("stopping order changed")
    points = 0
    exact = 0
    for case, item in zip(fixtures["tasks"], raw["records"]["tasks"], strict=True):
        if hashlib.sha256(item["response"].encode()).hexdigest() != item["response_sha256"]:
            raise RuntimeError("response hash mismatch")
        actual = score(case, item["response"])
        if actual != item["score"]:
            raise RuntimeError("score differs from raw response")
        points += actual
    for case, item in zip(fixtures["stopping"], raw["records"]["stopping"], strict=True):
        actual = norm(item["response"]) == norm(case["expected"])
        if actual != item.get("exact", item.get("expected_exact_match")):
            raise RuntimeError("stop exactness differs from raw response")
        exact += actual
    if summary["task_score"] != points or summary["stopping_exact"] != exact:
        raise RuntimeError("summary differs from independent rescore")
    return raw


def main() -> None:
    for seal_name in ("conversion-seal.json", "diagnostic-seal.json", "diagnostic-v2-seal.json", "heldout-seal.json"):
        seal = json.loads((HERE / seal_name).read_bytes())
        for name, expected in seal["input_sha256"].items():
            if sha(HERE / name) != expected:
                raise RuntimeError("sealed file changed: " + name)
    conversion = json.loads((HERE / "conversion-result.json").read_bytes())
    for name, info in conversion["files"].items():
        if sha(ROOT / conversion["output_relative_path"] / name) != info["sha256"]:
            raise RuntimeError("candidate artifact changed: " + name)
    old_fixtures = json.loads((OLD / "fixtures.json").read_bytes())
    diagnostic_runs = [
        verify_run(PRIVATE / f"diagnostic-v2-{number}.json", HERE / f"diagnostic-v2-{number}.json", old_fixtures)
        for number in (1, 2)
    ]
    for group in ("tasks", "stopping", "resources"):
        for a, b in zip(diagnostic_runs[0]["records"][group], diagnostic_runs[1]["records"][group], strict=True):
            if a["response_sha256"] != b["response_sha256"]:
                raise RuntimeError("diagnostic response not reproducible")
    heldout = json.loads((HERE / "heldout-fixtures.json").read_bytes())
    verify_run(PRIVATE / "heldout-source.json", HERE / "heldout-source.json", heldout)
    if (HERE / "heldout-candidate.json").exists() or (HERE / "heldout-verdict.json").exists():
        raise RuntimeError("partial heldout unexpectedly claims candidate result")
    if json.loads((ROOT / "config/models/registry.json").read_bytes())["models"]:
        raise RuntimeError("production model registry is no longer empty")
    if json.loads((ROOT / "config/model-platform/datasets.json").read_bytes())["datasets"]:
        raise RuntimeError("production dataset registry is no longer empty")
    print(json.dumps({"status": "PASS", "sealed_protocols": 4, "diagnostic_repetitions": 2, "reproducible_responses": 41, "heldout_source_scored": 32, "heldout_candidate": "BLOCKED_BY_DISK_GUARD", "approved_models": 0, "approved_datasets": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
