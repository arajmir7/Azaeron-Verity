#!/usr/bin/env python3
"""Bounded, non-training verification of the pinned third-party Qwen MLX bundle.

Only small metadata/assets are fetched. Neither source nor MLX weights are downloaded.
This does not prove which source checkpoint or conversion procedure produced the MLX
weights, and it cannot grant model admission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import urllib.request
from pathlib import Path
from typing import Any

MLX_REPO = "Qwen/Qwen3-4B-MLX-4bit"
MLX_REV = "52a5ab34fa604bc8af6d3ce0cac0cab10b7eb495"
SOURCE_REPO = "Qwen/Qwen3-4B"
# Latest source revision before the MLX repository's first weight upload. This is
# a compatible source candidate, NOT an attested conversion input.
SOURCE_PRE_UPLOAD_REV = "531c80e289d6cff3a7cd8c0db8110231d23a6f7a"
# A later license-only source revision lets us check whether published weight
# object IDs changed when the license file was added.
SOURCE_LICENSED_REV = "1cfa9a7208912126459214e8b04321603b3df60c"
EXPECTED_LOCAL = {
    "model.safetensors": "e56a94b846a2dce7d1cc154ce58b9cfc4b8d99e8ffb74bfe256a265f4cbc7fb9",
    "model.safetensors.index.json": "278844a566da15beab6e9068c57f606c50a99c440d4515206b871a8b5282b3de",
    "config.json": "76eae114d67a444c7296be7a6bc0409ecc15c340e113f1bac7572cb7d0928b6f",
    "tokenizer.json": "aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4",
    "tokenizer_config.json": "d5d09f07b48c3086c508b30d1c9114bd1189145b74e982a265350c923acd8101",
    "merges.txt": "8831e4f1a044471340f7c0a83d7bd71306a5b867e95fd870f74d0c5308a904d5",
    "vocab.json": "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910",
}
EXPECTED_LICENSE = "832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e"
SMALL_ASSETS = (
    "config.json",
    "model.safetensors.index.json",
    "tokenizer_config.json",
    "merges.txt",
    "vocab.json",
)
SOURCE_COMPARABLE_ASSETS = ("tokenizer_config.json", "merges.txt", "vocab.json")
USER_AGENT = "Azaeron-third-party-lineage-verification/1.0"


def digest_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def fetch_bytes(url: str, *, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > limit:
            raise ValueError(f"remote object exceeds byte limit: {url}")
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"remote object exceeds byte limit: {url}")
    return payload


def model_metadata(repo: str, revision: str) -> dict[str, Any]:
    url = f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true"
    data = json.loads(fetch_bytes(url, limit=1_000_000))
    if data.get("sha") != revision:
        raise ValueError(f"revision mismatch for {repo}")
    return data


def pinned_asset(repo: str, revision: str, name: str, *, limit: int) -> bytes:
    return fetch_bytes(
        f"https://huggingface.co/{repo}/resolve/{revision}/{name}", limit=limit
    )


def siblings_by_name(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["rfilename"]: item for item in metadata["siblings"]}


def inspect_safetensors(path: Path, index_path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        prefix = handle.read(8)
        if len(prefix) != 8:
            raise ValueError("truncated safetensors prefix")
        header_length = struct.unpack("<Q", prefix)[0]
        if not 0 < header_length <= 2_000_000:
            raise ValueError("safetensors header is outside bounded limit")
        header = json.loads(handle.read(header_length))
    tensors = {name: value for name, value in header.items() if name != "__metadata__"}
    indexed = json.loads(index_path.read_text())
    if set(tensors) != set(indexed["weight_map"]):
        raise ValueError("safetensors header and weight index disagree")
    if set(indexed["weight_map"].values()) != {"model.safetensors"}:
        raise ValueError("weight index references another file")
    data_size = path.stat().st_size - 8 - header_length
    spans = []
    for name, info in tensors.items():
        start, end = info["data_offsets"]
        if not 0 <= start < end <= data_size:
            raise ValueError(f"invalid tensor data offsets: {name}")
        spans.append((start, end))
    spans.sort()
    if spans[0][0] != 0 or spans[-1][1] != data_size:
        raise ValueError("safetensors data area is not fully indexed")
    if any(left[1] != right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("safetensors tensor spans overlap or have gaps")
    if indexed["metadata"]["total_size"] != data_size:
        raise ValueError("index total_size differs from safetensors data size")
    return {
        "status": "PASS",
        "tensor_count": len(tensors),
        "header_bytes": header_length,
        "data_bytes": data_size,
        "dtypes": sorted({item["dtype"] for item in tensors.values()}),
    }


def verify(snapshot: Path, *, online: bool) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for name, expected in EXPECTED_LOCAL.items():
        actual, size = digest_file(snapshot / name)
        if actual != expected:
            raise ValueError(f"local hash mismatch: {name}")
        files[name] = {"sha256": actual, "bytes": size}
    structure = inspect_safetensors(
        snapshot / "model.safetensors", snapshot / "model.safetensors.index.json"
    )
    result: dict[str, Any] = {
        "classification": "THIRD_PARTY_DEV_ONLY",
        "mlx_repository": MLX_REPO,
        "mlx_revision": MLX_REV,
        "local_file_verification": "PASS",
        "local_files": files,
        "safetensors_structure": structure,
        "source_checkpoint_revision_attested": False,
        "conversion_command_and_tool_revision_attested": False,
        "production_admission": "BLOCKED",
    }
    if not online:
        result["publisher_metadata_verification"] = "NOT_RUN"
        return result

    mlx = model_metadata(MLX_REPO, MLX_REV)
    source = model_metadata(SOURCE_REPO, SOURCE_PRE_UPLOAD_REV)
    licensed = model_metadata(SOURCE_REPO, SOURCE_LICENSED_REV)
    mlx_siblings = siblings_by_name(mlx)
    source_siblings = siblings_by_name(source)
    licensed_siblings = siblings_by_name(licensed)
    for name in ("model.safetensors", "tokenizer.json"):
        if mlx_siblings[name]["lfs"]["sha256"] != files[name]["sha256"]:
            raise ValueError(f"publisher LFS digest mismatch: {name}")
    source_tokenizer = source_siblings["tokenizer.json"]["lfs"]["sha256"]
    if source_tokenizer != files["tokenizer.json"]["sha256"]:
        raise ValueError("compatible source tokenizer differs from MLX tokenizer")
    checked_small_assets = {}
    for name in SMALL_ASSETS:
        payload = pinned_asset(MLX_REPO, MLX_REV, name, limit=3_000_000)
        sha = hashlib.sha256(payload).hexdigest()
        if sha != files[name]["sha256"]:
            raise ValueError(f"pinned MLX asset differs from local asset: {name}")
        checked_small_assets[name] = sha
    license_sha = hashlib.sha256(
        pinned_asset(MLX_REPO, MLX_REV, "LICENSE", limit=30_000)
    ).hexdigest()
    if license_sha != EXPECTED_LICENSE:
        raise ValueError("pinned MLX license differs from reviewed license")
    source_license_sha = hashlib.sha256(
        pinned_asset(SOURCE_REPO, SOURCE_LICENSED_REV, "LICENSE", limit=30_000)
    ).hexdigest()
    if source_license_sha != EXPECTED_LICENSE:
        raise ValueError("later source license differs from pinned MLX license")
    source_asset_match = {}
    for name in SOURCE_COMPARABLE_ASSETS:
        sha = hashlib.sha256(
            pinned_asset(SOURCE_REPO, SOURCE_PRE_UPLOAD_REV, name, limit=3_000_000)
        ).hexdigest()
        source_asset_match[name] = sha == files[name]["sha256"]
    if not all(source_asset_match.values()):
        raise ValueError("compatible source tokenizer support files differ")
    source_config = json.loads(
        pinned_asset(SOURCE_REPO, SOURCE_PRE_UPLOAD_REV, "config.json", limit=10_000)
    )
    mlx_config = json.loads((snapshot / "config.json").read_text())
    architecture_keys = (
        "architectures",
        "hidden_size",
        "intermediate_size",
        "num_attention_heads",
        "num_hidden_layers",
        "num_key_value_heads",
        "vocab_size",
        "rope_theta",
    )
    if any(source_config.get(key) != mlx_config.get(key) for key in architecture_keys):
        raise ValueError("compatible source architecture differs from MLX")
    source_weights = {
        name: item["lfs"]["sha256"]
        for name, item in source_siblings.items()
        if name.endswith(".safetensors")
    }
    licensed_weights = {
        name: item["lfs"]["sha256"]
        for name, item in licensed_siblings.items()
        if name.endswith(".safetensors")
    }
    if not source_weights or source_weights != licensed_weights:
        raise ValueError("source publisher weight object IDs changed across revisions")
    result.update(
        {
            "publisher_metadata_verification": "PASS",
            "publisher_mlx_license_sha256": license_sha,
            "publisher_later_source_license_sha256": source_license_sha,
            "publisher_small_asset_sha256": checked_small_assets,
            "compatible_source_candidate": {
                "repository": SOURCE_REPO,
                "pre_upload_revision": SOURCE_PRE_UPLOAD_REV,
                "later_licensed_revision": SOURCE_LICENSED_REV,
                "source_weight_lfs_sha256_publisher_metadata_only": source_weights,
                "weights_unchanged_across_these_revisions": True,
                "tokenizer_sha256_equal": True,
                "support_files_equal": source_asset_match,
                "architecture_core_equal": True,
                "config_differences": {
                    key: {"source": source_config.get(key), "mlx": mlx_config.get(key)}
                    for key in sorted(set(source_config) | set(mlx_config))
                    if source_config.get(key) != mlx_config.get(key)
                },
                "source_weight_bytes_verified_locally": False,
                "exact_conversion_parent_proven": False,
            },
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=Path.home()
        / ".cache/huggingface/hub/models--Qwen--Qwen3-4B-MLX-4bit/snapshots"
        / MLX_REV,
    )
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.snapshot, online=args.online)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
