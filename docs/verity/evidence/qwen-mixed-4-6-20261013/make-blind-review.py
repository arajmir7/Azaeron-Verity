#!/usr/bin/env python3
"""Prepare a private randomized review packet; never invent reviewer ratings."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / "qwen-technical-32case-20261013"
PRIVATE = ROOT / ".verity-local/qwen-mixed-4-6-20261013"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
    if private:
        path.chmod(0o600)


def main() -> None:
    seal = json.loads((OLD / "seal.json").read_bytes())
    for name, expected in seal["input_sha256"].items():
        if sha(OLD / name) != expected:
            raise RuntimeError("old technical seal changed")
    runs = {}
    paths = {
        "bf16": ROOT / ".verity-local/qwen-technical-32case-20261013/raw-source.json",
        "4bit": ROOT / ".verity-local/qwen-technical-32case-20261013/raw-candidate.json",
        "mixed4-6": PRIVATE / "diagnostic-v2-1.json",
    }
    summaries = {
        "bf16": OLD / "run-source.json",
        "4bit": OLD / "run-candidate.json",
        "mixed4-6": HERE / "diagnostic-v2-1.json",
    }
    for name, path in paths.items():
        summary = json.loads(summaries[name].read_bytes())
        if sha(path) != summary["private_raw_sha256"]:
            raise RuntimeError("private response hash changed")
        runs[name] = json.loads(path.read_bytes())
    fixtures = json.loads((OLD / "fixtures.json").read_bytes())
    seed = int.from_bytes(hashlib.sha256(b"qwen-technical-blind-review-v1").digest()[:8], "big")
    rng = random.Random(seed)
    packet = {"classification": "TECHNICAL_REVIEW_ONLY_NOT_COMMERCIAL_QUALITY_CERTIFICATION", "minimum_independent_reviewers_per_item": 2, "ratings_received": 0, "items": []}
    key = {"classification": "PRIVATE_BLIND_KEY_DO_NOT_SHARE_WITH_REVIEWERS", "items": {}}
    for index, case in enumerate(fixtures["tasks"]):
        model_order = list(runs)
        rng.shuffle(model_order)
        item_id = f"BR-{index + 1:03d}"
        answers = []
        key["items"][item_id] = {}
        for label, model_name in zip("ABC", model_order, strict=True):
            record = runs[model_name]["records"]["tasks"][index]
            if record["reasoning_visible"]:
                raise RuntimeError("literal internal reasoning marker in review response")
            answers.append({"label": label, "response": record["response"]})
            key["items"][item_id][label] = {"model": model_name, "response_sha256": record["response_sha256"]}
        packet["items"].append({"id": item_id, "prompt": case["prompt"], "responses": answers, "reviewer_1": None, "reviewer_2": None})
    rng.shuffle(packet["items"])
    packet_path = PRIVATE / "blind-review-packet.json"
    key_path = PRIVATE / "blind-review-key.json"
    write_new(packet_path, packet, private=True)
    write_new(key_path, key, private=True)
    write_new(HERE / "blind-review-manifest.json", {
        "classification": "PREPARED_NOT_REVIEWED",
        "packet_sha256": sha(packet_path),
        "private_key_sha256": sha(key_path),
        "item_count": len(packet["items"]),
        "responses_per_item": 3,
        "minimum_independent_reviewers_per_item": 2,
        "ratings_received": 0,
        "evidence_set": "previously observed technical diagnostic probes",
        "limitation": "Strict format/fidelity review only; not a sealed real-world quality benchmark or independent commercial-quality certification",
    })


if __name__ == "__main__":
    main()
