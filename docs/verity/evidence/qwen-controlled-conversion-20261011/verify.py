#!/usr/bin/env python3
"""Verify a locally controlled Qwen source-to-MLX conversion without admitting it."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

SOURCE_REVISION = "1cfa9a7208912126459214e8b04321603b3df60c"
SOURCE_SHARDS = {
    "model-00001-of-00003.safetensors": "328a91d3122359d5547f9d79521205bc0a46e1f79a792dfe650e99fc2d651223",
    "model-00002-of-00003.safetensors": "6cd087b316306a68c562436b5492edbcf6e16c6dba3a1308279caa5a58e21ca5",
    "model-00003-of-00003.safetensors": "e4bf436957184f4eeb86a80e9db394503f1f56446b2e6b7edeac5b81470f4ca1",
}
LICENSE_SHA256 = "832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e"
TOKENIZER_SHA256 = "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4"
CORE_CONFIG_KEYS = (
    "architectures",
    "hidden_size",
    "intermediate_size",
    "num_attention_heads",
    "num_hidden_layers",
    "num_key_value_heads",
    "vocab_size",
    "rope_theta",
)


def digest(path: Path) -> dict[str, int | str]:
    if not path.is_file():
        raise ValueError(f"missing file: {path}")
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            sha.update(chunk)
    return {"sha256": sha.hexdigest(), "bytes": path.stat().st_size}


def inventory(directory: Path) -> dict[str, dict[str, int | str]]:
    return {
        path.name: digest(path)
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "conversion-verification.json"
    }


def verify_source(source: Path) -> dict[str, object]:
    files = inventory(source)
    for name, expected in SOURCE_SHARDS.items():
        if files[name]["sha256"] != expected:
            raise ValueError(
                f"source shard differs from pinned publisher digest: {name}"
            )
    if files["LICENSE"]["sha256"] != LICENSE_SHA256:
        raise ValueError("source LICENSE differs from pinned Apache-2.0 evidence")
    if files["tokenizer.json"]["sha256"] != TOKENIZER_SHA256:
        raise ValueError("source tokenizer differs from pinned publisher tokenizer")
    config = json.loads((source / "config.json").read_text())
    if config.get("model_type") != "qwen3" or config.get("num_hidden_layers") != 36:
        raise ValueError("unexpected source architecture")
    if set(config.get("architectures", [])) != {"Qwen3ForCausalLM"}:
        raise ValueError("unexpected source implementation")
    return {
        "repository": "Qwen/Qwen3-4B",
        "revision": SOURCE_REVISION,
        "shard_sha256_verified_against_publisher": True,
        "license": "Apache-2.0 (publisher file verified; legal admission pending)",
        "notice_file_published_in_snapshot": "NOTICE" in files,
        "files": files,
        "config": config,
    }


def verify_conversion(
    source: Path, converted: Path, existing: Path
) -> dict[str, object]:
    source_result = verify_source(source)
    new_files = inventory(converted)
    old_files = inventory(existing)
    if not any(name.endswith(".safetensors") for name in new_files):
        raise ValueError("conversion has no safetensors checkpoint")
    if new_files["LICENSE"]["sha256"] != LICENSE_SHA256:
        raise ValueError("converted bundle lacks the pinned source license")
    if new_files["tokenizer.json"]["sha256"] != TOKENIZER_SHA256:
        raise ValueError("converted tokenizer differs from the source")
    new_config = json.loads((converted / "config.json").read_text())
    source_config = source_result["config"]
    for key in CORE_CONFIG_KEYS:
        if new_config.get(key) != source_config.get(key):
            raise ValueError(f"conversion changed core architecture: {key}")
    quant = new_config.get("quantization", {})
    if quant.get("bits") != 4 or quant.get("group_size") != 128:
        raise ValueError("conversion does not match requested 4-bit/group-128 mode")
    new_weights = {
        name: item["sha256"]
        for name, item in new_files.items()
        if name.endswith(".safetensors")
    }
    old_weights = {
        name: item["sha256"]
        for name, item in old_files.items()
        if name.endswith(".safetensors")
    }
    if set(new_weights.values()) == set(old_weights.values()):
        raise ValueError(
            "controlled conversion unexpectedly equals the unproven prior bundle"
        )
    return {
        "classification": "THIRD_PARTY_CONVERSION_CANDIDATE_NOT_ADMITTED",
        "source": source_result,
        "conversion": {
            "tool": "mlx-lm",
            "tool_version": version("mlx-lm"),
            "mlx_version": version("mlx"),
            "transformers_version": version("transformers"),
            "safetensors_version": version("safetensors"),
            "platform": platform.platform(),
            "parameters": {
                "quantize": True,
                "bits": 4,
                "group_size": 128,
                "mode": "affine",
                "trust_remote_code": False,
            },
            "files": new_files,
            "weight_sha256": new_weights,
        },
        "comparison_with_existing_unproven_mlx_bundle": {
            "repository": "Qwen/Qwen3-4B-MLX-4bit",
            "revision": "52a5ab34fa604bc8af6d3ce0cac0cab10b7eb495",
            "weight_sha256": old_weights,
            "converted_weight_bytes_identical": False,
            "tokenizer_sha256_identical": new_files["tokenizer.json"]["sha256"]
            == old_files["tokenizer.json"]["sha256"],
            "config_identical": new_files["config.json"]["sha256"]
            == old_files["config.json"]["sha256"],
            "historical_conversion_parent_proven": False,
        },
        "owner_admission": "NOT_REQUESTED",
        "training_authorized": False,
        "production_approval": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--converted", type=Path)
    parser.add_argument("--existing", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.converted) != bool(args.existing):
        parser.error("--converted and --existing must be supplied together")
    result = (
        verify_conversion(args.source, args.converted, args.existing)
        if args.converted
        else verify_source(args.source)
    )
    rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
