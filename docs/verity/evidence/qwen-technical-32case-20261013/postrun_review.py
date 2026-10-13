#!/usr/bin/env python3
"""Postrun, non-gating audit of the sealed comparison's visible model responses."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / ".verity-local/qwen-technical-32case-20261013"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip('"\'`').rstrip(". ")).casefold()


def score(case: dict, response: str) -> int:
    if case["kind"] == "exact":
        return int(normalize(response) == normalize(case["expected"]))
    return int(
        all(marker in response for marker in case["required"])
        and all(marker not in response for marker in case["forbidden"])
    )


def main() -> None:
    seal = json.loads((HERE / "seal.json").read_text())
    for name, expected in seal["input_sha256"].items():
        if sha(HERE / name) != expected:
            raise RuntimeError("sealed input differs: " + name)
    fixture = json.loads((HERE / "fixtures.json").read_text())
    source = json.loads((PRIVATE / "raw-source.json").read_text())
    candidate = json.loads((PRIVATE / "raw-candidate.json").read_text())
    raw = json.loads((HERE / "raw-results.json").read_text())
    for stage, payload in (("source", source), ("candidate", candidate)):
        run = json.loads((HERE / f"run-{stage}.json").read_text())
        if sha(PRIVATE / f"raw-{stage}.json") != run["private_raw_sha256"]:
            raise RuntimeError("private raw digest changed")
        if payload["protocol_sha256"] != seal["input_sha256"]["protocol.json"]:
            raise RuntimeError("protocol mismatch")
    packet = {
        "classification": "POSTRUN_VISIBLE_RESPONSE_AUDIT_NOT_TECHNICAL_ACCEPTANCE",
        "seal_sha256": sha(HERE / "seal.json"),
        "protocol_sha256": sha(HERE / "protocol.json"),
        "fixtures_sha256": sha(HERE / "fixtures.json"),
        "private_raw_sha256": {
            "source": sha(PRIVATE / "raw-source.json"),
            "candidate": sha(PRIVATE / "raw-candidate.json"),
        },
        "all_responses_scanned_for_literal_reasoning_markers": True,
        "tasks": [],
        "stopping": [],
        "resources": [],
    }
    for i, case in enumerate(fixture["tasks"]):
        pair = {}
        for stage, payload in (("source", source), ("candidate", candidate)):
            item = payload["records"]["tasks"][i]
            if item["id"] != case["id"] or text_sha(item["response"]) != item["response_sha256"]:
                raise RuntimeError("task response mismatch")
            recomputed = score(case, item["response"])
            if recomputed != item["score"] or recomputed != raw["tasks"][i]["baseline_score" if stage == "source" else "candidate_score"]:
                raise RuntimeError("task score mismatch")
            if item["reasoning_visible"]:
                raise RuntimeError("refusing to publish visible reasoning marker")
            pair[stage] = {"visible_response": item["response"], "response_sha256": item["response_sha256"], "recomputed_score": recomputed, "finish_reason": item["finish_reason"], "literal_reasoning_marker": False}
        packet["tasks"].append({"id": case["id"], "kind": case["kind"], "prompt_sha256": text_sha(case["prompt"]), "scorer_inputs": {key: case[key] for key in ("expected", "required", "forbidden") if key in case}, **pair})
    for i, case in enumerate(fixture["stopping"]):
        pair = {}
        for stage, payload in (("source", source), ("candidate", candidate)):
            item = payload["records"]["stopping"][i]
            if item["id"] != case["id"] or text_sha(item["response"]) != item["response_sha256"]:
                raise RuntimeError("stopping response mismatch")
            exact = normalize(item["response"]) == normalize(case["expected"])
            if exact != item["expected_exact_match"] or item["reasoning_visible"]:
                raise RuntimeError("stopping match or visible reasoning discrepancy")
            pair[stage] = {"visible_response": item["response"], "response_sha256": item["response_sha256"], "exact_expected_match": exact, "finish_reason": item["finish_reason"], "literal_reasoning_marker": False}
        packet["stopping"].append({"id": case["id"], "prompt_sha256": text_sha(case["prompt"]), "expected": case["expected"], **pair})
    for i, case in enumerate(fixture["resources"]):
        pair = {}
        for stage, payload in (("source", source), ("candidate", candidate)):
            item = payload["records"]["resources"][i]
            if item["id"] != case["id"] or text_sha(item["response"]) != item["response_sha256"] or item["reasoning_visible"]:
                raise RuntimeError("resource response mismatch")
            pair[stage] = {"visible_response": item["response"], "response_sha256": item["response_sha256"], "input_tokens": item["input_tokens"], "peak_memory_gib": item["peak_memory_gib"], "finish_reason": item["finish_reason"], "success": item["success"], "literal_reasoning_marker": False}
        packet["resources"].append({"id": case["id"], "prompt_sha256": text_sha(case["prompt"]), **pair})
    target = HERE / "review-packet.json"
    with target.open("x") as handle:
        json.dump(packet, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print("review_packet_sha256", sha(target))


if __name__ == "__main__":
    main()
