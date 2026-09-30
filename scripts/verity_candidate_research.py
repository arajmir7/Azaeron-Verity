"""Capture public primary-source metadata for review; never admit or run a model.

Only cards, license notices and JSON configuration are downloaded. Weight hashes
are publisher declarations until a later reviewed acquisition verifies the bytes.
No authentication, inference, remote Python or customer content is involved.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

MODELS = {
    "Qwen/Qwen3-4B-Instruct-2507": "writer_candidate",
    "Qwen/Qwen3.5-4B": "writer_candidate",
    "HuggingFaceTB/SmolLM3-3B": "writer_candidate",
    "microsoft/Phi-4-mini-instruct": "independent_baseline_candidate",
    "mistralai/Ministral-3-8B-Instruct-2512-BF16": "independent_baseline_candidate",
    "Qwen/Qwen3-Embedding-0.6B": "embed_initialization_candidate",
    "microsoft/deberta-v3-base": "verifier_detector_initialization_candidate",
}
DATASETS = {
    "databricks/databricks-dolly-15k": "human_instruction_candidate",
    "OpenAssistant/oasst1": "human_conversation_candidate",
    "HuggingFaceH4/no_robots": "noncommercial_exclusion_check",
    "allenai/Dolci-Instruct-SFT": "mixed_source_rights_exclusion_check",
}


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "Azaeron-rights-research/1"}
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(2 * 1024**2 + 1)
    if len(body) > 2 * 1024**2:
        raise ValueError("Metadata download exceeds the bounded review limit")
    return body


def capture(root, repository, role, kind):
    api = f"https://huggingface.co/api/{kind}/{repository}?blobs=true"
    raw = fetch(api)
    metadata = json.loads(raw)
    revision = metadata["sha"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Repository lacks an immutable Git revision")
    destination = root / repository.replace("/", "--") / revision
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "publisher-metadata.json").write_bytes(raw)
    prefix = "datasets/" if kind == "datasets" else ""
    artifacts, remote_weights = {}, {}
    for item in metadata.get("siblings", []):
        name = item["rfilename"]
        if name in {
            "README.md",
            "LICENSE",
            "LICENSE.md",
            "NOTICE.md",
            "config.json",
            "tokenizer_config.json",
            "data_summary_card.md",
        }:
            url = (
                f"https://huggingface.co/{prefix}{repository}/resolve/{revision}/{name}"
            )
            body = fetch(url)
            (destination / name).write_bytes(body)
            artifacts[name] = {
                "sha256": hashlib.sha256(body).hexdigest(),
                "source": url,
            }
        if name.endswith((".safetensors", ".parquet", ".jsonl")):
            remote_weights[name] = {
                "publisher_lfs_sha256": item.get("lfs", {}).get("sha256"),
                "bytes": item.get("size"),
                "local_bytes_verified": False,
            }
    license_id = metadata.get("cardData", {}).get("license")
    known = license_id in {"apache-2.0", "mit", "cc-by-sa-3.0"}
    record = {
        "repository": repository,
        "kind": kind,
        "role": role,
        "revision": revision,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "primary_api": api,
        "metadata_sha256": hashlib.sha256(raw).hexdigest(),
        "declared_license": license_id,
        "local_metadata": artifacts,
        "unverified_payload_inventory": remote_weights,
        "status": "REVIEW_REQUIRED" if known else "REJECTED",
        "approval": "NOT_APPROVED",
        "reviewer": None,
        "blockers": (
            [
                "Accountable rights review NOT FOUND",
                "Payload bytes NOT ACQUIRED / NOT VERIFIED",
                "PII/copyright and upstream provenance review NOT COMPLETE",
            ]
            if kind == "datasets"
            else [
                "Accountable commercial-use/training review NOT FOUND",
                "Weights NOT ACQUIRED / NOT VERIFIED",
                "Offline runtime compatibility NOT EXECUTED",
                "Internal quality comparison NOT EXECUTED",
            ]
        ),
    }
    if not known:
        record["blockers"].append(
            "Noncommercial, mixed, or unknown rights cannot enter training"
        )
    config_path = destination / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_bytes())
        text_config = config.get("text_config", config)
        record["technical_metadata"] = {
            "architecture": config.get("architectures"),
            "text_model_type": text_config.get("model_type"),
            "publisher_parameters": metadata.get("safetensors", {}).get("total"),
            "configured_context": text_config.get("max_position_embeddings"),
            "languages": metadata.get("cardData", {}).get("language"),
            "local_weights_verified": False,
        }
        if config.get("auto_map") or text_config.get("auto_map"):
            record["status"] = "REJECTED"
            record["blockers"].append(
                "auto_map violates no-remote-code admission; a native supported upstream artifact is required"
            )
        if not remote_weights:
            record["status"] = "REJECTED"
            record["blockers"].append(
                "No safetensors inventory; unsafe pickle weights are not admitted"
            )
    (destination / "review-dossier.json").write_text(
        json.dumps(record, indent=2) + "\n"
    )
    return {
        "repository": repository,
        "revision": revision,
        "status": record["status"],
        "dossier": str((destination / "review-dossier.json").relative_to(root)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    records = []
    for kind, entries in (("models", MODELS), ("datasets", DATASETS)):
        for repository, role in entries.items():
            try:
                records.append(capture(args.output, repository, role, kind))
            except Exception as error:
                records.append(
                    {
                        "repository": repository,
                        "status": "REJECTED",
                        "reason": type(error).__name__,
                        "evidence": "NOT FOUND / BLOCKED",
                    }
                )
            (args.output / "index.json").write_text(
                json.dumps(records, indent=2) + "\n"
            )
    print(json.dumps({"review_dossiers": len(records), "admitted": 0, "approved": 0}))


if __name__ == "__main__":
    main()
