#!/usr/bin/env python3
"""Offline tokenizer/logit compatibility measurement; never a quality benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

PROMPTS = (
    "State the number after seven.",
    "Rewrite clearly: Mira delivered 12 units on 6 August 2024.",
    "Summarize: The east office closed at 17:00; the west closed at 19:00.",
    "Answer from this source only: The council voted 8 to 2 on 3 May 2023. When?",
    "Preserve this quotation exactly: 'The plan is not final.'",
    "Translate into French: The library opens tomorrow.",
    "Return JSON with keys name and count for Ari and 14 items.",
    "Explain why 9 multiplied by 7 is 63 in one sentence.",
    "What is the next step after checking a document citation?",
    "Write a short, polite reminder about a Monday meeting.",
)


def dump_logits(model_path: Path, output_dir: Path) -> None:
    import mlx.core as mx
    from mlx_lm import load

    if output_dir.exists():
        raise ValueError("output already exists; refusing to overwrite")
    output_dir.mkdir(parents=True)
    model, tokenizer = load(str(model_path), trust_remote_code=False)
    items = []
    for index, prompt in enumerate(PROMPTS):
        messages = [{"role": "user", "content": prompt}]
        token_ids = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        logits = model(mx.array([token_ids]))[0, -1].astype(mx.float32)
        mx.eval(logits)
        values = np.asarray(logits).astype(np.float32, copy=False)
        np.save(output_dir / f"logits-{index:02d}.npy", values)
        items.append(
            {
                "index": index,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "token_ids": token_ids,
                "logit_vector_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
            }
        )
    (output_dir / "index.json").write_text(
        json.dumps(
            {
                "model_path": str(model_path),
                "peak_mlx_bytes": mx.get_peak_memory(),
                "items": items,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def compare(source_dir: Path, converted_dir: Path) -> dict[str, object]:
    source = json.loads((source_dir / "index.json").read_text())
    converted = json.loads((converted_dir / "index.json").read_text())
    if len(source["items"]) != len(PROMPTS) or len(converted["items"]) != len(PROMPTS):
        raise ValueError("incomplete inference comparison")
    cases = []
    for a, b in zip(source["items"], converted["items"], strict=True):
        if a["index"] != b["index"] or a["prompt_sha256"] != b["prompt_sha256"]:
            raise ValueError("prompt mismatch")
        if a["token_ids"] != b["token_ids"]:
            raise ValueError(f"chat-template tokenizer mismatch on item {a['index']}")
        index = a["index"]
        left = np.load(source_dir / f"logits-{index:02d}.npy")
        right = np.load(converted_dir / f"logits-{index:02d}.npy")
        if left.shape != right.shape:
            raise ValueError("vocabulary logit shape mismatch")
        left64, right64 = left.astype(np.float64), right.astype(np.float64)
        delta = right64 - left64
        cosine = np.dot(left64, right64) / (
            np.linalg.norm(left64) * np.linalg.norm(right64)
        )
        top_source = int(np.argmax(left))
        top_converted = int(np.argmax(right))
        top_two = np.partition(left, -2)[-2:]
        top_margin = float(top_two.max() - top_two.min())
        source_prob = np.exp(left64 - np.max(left64))
        source_prob /= np.sum(source_prob)
        converted_prob = np.exp(right64 - np.max(right64))
        converted_prob /= np.sum(converted_prob)
        cases.append(
            {
                "index": index,
                "prompt_sha256": a["prompt_sha256"],
                "token_count": len(a["token_ids"]),
                "vocabulary_size": int(left.size),
                "cosine_similarity": round(float(cosine), 8),
                "rms_logit_delta": round(float(np.sqrt(np.mean(delta * delta))), 6),
                "max_absolute_logit_delta": round(float(np.max(np.abs(delta))), 6),
                "source_top1_token_id": top_source,
                "converted_top1_token_id": top_converted,
                "top1_equal": top_source == top_converted,
                "source_top1_margin": round(top_margin, 6),
                "source_top1_probability": round(float(source_prob[top_source]), 6),
                "converted_probability_of_source_top1": round(
                    float(converted_prob[top_source]), 6
                ),
                "softmax_total_variation": round(
                    float(0.5 * np.sum(np.abs(source_prob - converted_prob))), 6
                ),
                "top10_overlap": len(
                    set(np.argsort(left)[-10:]) & set(np.argsort(right)[-10:])
                ),
                "source_logits_sha256": a["logit_vector_sha256"],
                "converted_logits_sha256": b["logit_vector_sha256"],
            }
        )
    return {
        "classification": "NON_TRAINING_QUANTIZATION_COMPATIBILITY_ONLY",
        "source_model_path": source["model_path"],
        "converted_model_path": converted["model_path"],
        "same_chat_template_token_ids_all_cases": True,
        "prompt_count": len(cases),
        "min_cosine_similarity": min(item["cosine_similarity"] for item in cases),
        "max_softmax_total_variation": max(
            item["softmax_total_variation"] for item in cases
        ),
        "top1_equal_count": sum(item["top1_equal"] for item in cases),
        "source_peak_mlx_bytes": source["peak_mlx_bytes"],
        "converted_peak_mlx_bytes": converted["peak_mlx_bytes"],
        "cases": cases,
        "limitation": "Next-token logits on ten short prompts only; not full-response or production-quality equivalence.",
        "base_admitted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    dump = sub.add_parser("dump")
    dump.add_argument("--model", type=Path, required=True)
    dump.add_argument("--output-dir", type=Path, required=True)
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("--source-dir", type=Path, required=True)
    compare_parser.add_argument("--converted-dir", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "dump":
        dump_logits(args.model, args.output_dir)
    else:
        args.output.write_text(
            json.dumps(
                compare(args.source_dir, args.converted_dir), sort_keys=True, indent=2
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
