#!/usr/bin/env python3
"""Offline source-hash-gated MLX conversion; never admits the result for training."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from verify import digest, verify_conversion, verify_source

MIN_FREE_BYTES = 20 * 1024**3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    existing = args.existing.resolve()
    if output.exists() or args.manifest.exists():
        parser.error("output or manifest exists; refusing to overwrite it")
    if shutil.disk_usage(output.parent).free < MIN_FREE_BYTES:
        parser.error("less than 20 GiB free; refusing conversion")
    verify_source(source)

    command = [
        sys.executable,
        "-m",
        "mlx_lm",
        "convert",
        "--hf-path",
        str(source),
        "--mlx-path",
        str(output),
        "-q",
        "--q-group-size",
        "128",
        "--q-bits",
        "4",
        "--q-mode",
        "affine",
    ]
    environment = os.environ.copy()
    environment.update(
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
    )
    print("Executing pinned, offline, unadmitted conversion", flush=True)
    subprocess.run(command, check=True, env=environment)
    emitted_tokenizer = digest(output / "tokenizer.json")
    shutil.copyfile(source / "LICENSE", output / "LICENSE")
    # save_pretrained rewrites tokenizer JSON bytes. Retain the publisher's
    # exact pinned tokenizer so the converted bundle has a directly proven
    # tokenizer lineage rather than merely equivalent reserialized content.
    shutil.copyfile(source / "tokenizer.json", output / "tokenizer.json")
    result = verify_conversion(source, output, existing)
    result["conversion"]["converter_emitted_tokenizer_sha256"] = emitted_tokenizer[
        "sha256"
    ]
    result["conversion"]["exact_source_tokenizer_restored_after_serialization"] = True
    result["conversion"]["command"] = [
        "python",
        "-m",
        "mlx_lm",
        "convert",
        "--hf-path",
        "<verified local source>",
        "--mlx-path",
        "<new local output>",
        "-q",
        "--q-group-size",
        "128",
        "--q-bits",
        "4",
        "--q-mode",
        "affine",
    ]
    args.manifest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("Conversion and hash verification complete; admission remains blocked")


if __name__ == "__main__":
    main()
