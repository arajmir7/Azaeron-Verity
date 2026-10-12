#!/usr/bin/env python3
"""Inspect packed-weight error and same-model repeat without training."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mlx.core as mx


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_error(source, converted) -> dict[str, object]:
    mx.eval(source, converted)
    delta = source.astype(mx.float32) - converted.astype(mx.float32)
    numerator = float(mx.sum(delta * delta))
    denominator = float(mx.sum(source.astype(mx.float32) ** 2))
    return {
        "shape": list(source.shape),
        "relative_rmse": round((numerator / denominator) ** 0.5, 8),
        "max_absolute_delta": round(float(mx.max(mx.abs(delta))), 8),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--converted", type=Path, required=True)
    parser.add_argument("--source-logits", type=Path, required=True)
    parser.add_argument("--converted-logits", type=Path, required=True)
    parser.add_argument("--converted-repeat-logits", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_config = json.loads((args.source / "config.json").read_text())
    converted_config = json.loads((args.converted / "config.json").read_text())
    config_changes = {
        key: [source_config.get(key), converted_config.get(key)]
        for key in sorted(set(source_config) | set(converted_config))
        if source_config.get(key) != converted_config.get(key)
    }
    index = json.loads((args.source / "model.safetensors.index.json").read_text())[
        "weight_map"
    ]
    quant = mx.load(str(args.converted / "model.safetensors"))
    source_shards: dict[str, dict] = {}

    def weight(name: str):
        shard = index[name]
        if shard not in source_shards:
            source_shards[shard] = mx.load(str(args.source / shard))
        return source_shards[shard][name]

    source_logits = json.loads((args.source_logits / "index.json").read_text())
    converted_logits = json.loads((args.converted_logits / "index.json").read_text())
    repeat_logits = json.loads(
        (args.converted_repeat_logits / "index.json").read_text()
    )
    if (
        not len(source_logits["items"])
        == len(converted_logits["items"])
        == len(repeat_logits["items"])
    ):
        raise ValueError("logit case counts differ")
    for a, b, c in zip(
        source_logits["items"],
        converted_logits["items"],
        repeat_logits["items"],
        strict=True,
    ):
        if a["token_ids"] != b["token_ids"] or b["token_ids"] != c["token_ids"]:
            raise ValueError("same-prompt token IDs changed")
        if b["logit_vector_sha256"] != c["logit_vector_sha256"]:
            raise ValueError("converted same-model logits were not deterministic")

    token_ids = sorted(
        {token_id for item in source_logits["items"] for token_id in item["token_ids"]}
    )
    rows = mx.array(token_ids)
    names = (
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.mlp.gate_proj.weight",
        "model.layers.35.self_attn.o_proj.weight",
    )
    errors = {}
    for name in names:
        original = weight(name)
        packed = quant[name]
        scales = quant[name.removesuffix(".weight") + ".scales"]
        biases = quant[name.removesuffix(".weight") + ".biases"]
        if name == "model.embed_tokens.weight":
            original = original[rows]
            packed, scales, biases = packed[rows], scales[rows], biases[rows]
        dequantized = mx.dequantize(packed, scales, biases, 128, 4, "affine")
        errors[name] = relative_error(original, dequantized)

    result = {
        "classification": "NON_TRAINING_QUANTIZATION_DIAGNOSTIC",
        "source_model_type": source_config["model_type"],
        "converted_model_type": converted_config["model_type"],
        "model_forward_implementation": "mlx_lm.models.qwen3.Model.__call__ for both; converted layers use quantized MLX modules",
        "config_changes": config_changes,
        "identical_chat_template_token_ids_all_cases": True,
        "converted_same_model_repeated_logits_identical_count": len(
            converted_logits["items"]
        ),
        "converted_same_model_repeated_logit_count": len(converted_logits["items"]),
        "source_same_model_repeat_not_tested": True,
        "sampled_embedding_token_rows": len(token_ids),
        "weight_error": errors,
        "peak_mlx_bytes": mx.get_peak_memory(),
        "conclusion": "4-bit packed-weight error is measurable; quantized inference equivalence is not established by these diagnostics.",
    }
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
