#!/usr/bin/env python3
"""Compare two independently executed, locally hash-verified MLX conversions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verify import digest


def compare(first: Path, second: Path) -> dict[str, object]:
    a = json.loads(first.read_text())
    b = json.loads(second.read_text())
    files_a = a["conversion"]["files"]
    files_b = b["conversion"]["files"]
    if a["source"] != b["source"]:
        raise ValueError("repeated conversions used different source manifests")
    if a["conversion"]["parameters"] != b["conversion"]["parameters"]:
        raise ValueError("repeated conversions used different parameters")
    if files_a != files_b:
        raise ValueError("repeated conversion output file hashes differ")
    return {
        "classification": "NON_TRAINING_REPRODUCIBILITY_CHECK_ONLY",
        "first_manifest_sha256": digest(first)["sha256"],
        "second_manifest_sha256": digest(second)["sha256"],
        "pinned_source_revision": a["source"]["revision"],
        "all_output_file_hashes_identical": True,
        "output_file_count": len(files_a),
        "model_safetensors_sha256": files_a["model.safetensors"]["sha256"],
        "tokenizer_json_sha256": files_a["tokenizer.json"]["sha256"],
        "chat_template_jinja_sha256": files_a["chat_template.jinja"]["sha256"],
        "repeat_environment": "same Mac and installed dependency environment; cross-host reproducibility not tested",
        "base_admitted": False,
        "training_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(compare(args.first, args.second), sort_keys=True, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
