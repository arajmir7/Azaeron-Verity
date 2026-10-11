#!/usr/bin/env python3
"""Compare safetensors payloads without loading full models into RAM."""

from __future__ import annotations

import argparse
import json
import mmap
import struct
from pathlib import Path

from verify import digest


def header(mapped: mmap.mmap) -> tuple[dict[str, object], int]:
    length = struct.unpack("<Q", mapped[:8])[0]
    if not 0 < length < 10_000_000:
        raise ValueError("invalid safetensors header length")
    return json.loads(mapped[8 : 8 + length]), 8 + length


def compare(controlled: Path, existing: Path) -> dict[str, object]:
    result: dict[str, object] = {
        "controlled_sha256": digest(controlled)["sha256"],
        "existing_sha256": digest(existing)["sha256"],
        "tensor_names_equal": False,
        "tensor_count": 0,
        "shape_dtype_equal_count": 0,
        "value_equal_count": 0,
        "value_different_examples": [],
        "shape_dtype_different_examples": [],
        "historical_parent_proven": False,
    }
    with (
        controlled.open("rb") as new_file,
        existing.open("rb") as old_file,
        mmap.mmap(new_file.fileno(), 0, access=mmap.ACCESS_READ) as new_map,
        mmap.mmap(old_file.fileno(), 0, access=mmap.ACCESS_READ) as old_map,
    ):
        new_header, new_start = header(new_map)
        old_header, old_start = header(old_map)
        names = sorted(set(new_header) - {"__metadata__"})
        result["tensor_names_equal"] = set(names) == set(old_header) - {"__metadata__"}
        result["tensor_count"] = len(names)
        for name in names:
            if name not in old_header:
                continue
            new = new_header[name]
            old = old_header[name]
            if new["dtype"] != old["dtype"] or new["shape"] != old["shape"]:
                if len(result["shape_dtype_different_examples"]) < 12:
                    result["shape_dtype_different_examples"].append(name)
                continue
            result["shape_dtype_equal_count"] += 1
            new_from, new_to = new["data_offsets"]
            old_from, old_to = old["data_offsets"]
            equal = (
                new_to - new_from == old_to - old_from
                and memoryview(new_map)[new_start + new_from : new_start + new_to]
                == memoryview(old_map)[old_start + old_from : old_start + old_to]
            )
            if equal:
                result["value_equal_count"] += 1
            elif len(result["value_different_examples"]) < 12:
                result["value_different_examples"].append(name)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controlled", type=Path, required=True)
    parser.add_argument("--existing", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(compare(args.controlled, args.existing), sort_keys=True, indent=2)
        + "\n"
    )


if __name__ == "__main__":
    main()
