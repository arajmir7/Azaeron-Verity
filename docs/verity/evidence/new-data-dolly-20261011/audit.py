"""Read-only audit of the pinned Databricks Dolly 15k publisher payload.

Only hashes, source locators, category counts and review flags are emitted.
No text export, training split, or admission is created.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

REVISION = "bdd27f4d94b9c1f951818a7da7fd7aeea5dbff1a"
EXPECTED = {
    "README.md": "db06c60090a11b20e79d1933b2f316f781605f07761ff2ae2795d6523e3e960b",
    "databricks-dolly-15k.jsonl": "2df9083338b4abd6bceb5635764dab5d833b393b55759dffb0959b6fcbf794ec",
}
CATEGORIES = {
    "open_qa",
    "general_qa",
    "classification",
    "closed_qa",
    "brainstorming",
    "information_extraction",
    "summarization",
    "creative_writing",
}
CONTEXT_EXPECTED = {"closed_qa", "information_extraction", "summarization"}
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
URL = re.compile(r"https?://\S+", re.I)
PHONE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
)
LONG_NUMBER = re.compile(r"(?<!\d)\d{9,}(?!\d)")
WORDS = re.compile(r"\w+", re.UNICODE)


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def normalized(text: str) -> str:
    return " ".join(WORDS.findall(text.casefold()))


def audit(source: Path, output: Path) -> None:
    source_files = {}
    for name, expected in EXPECTED.items():
        path = source / name
        if path.stat().st_size > 20_000_000:
            raise ValueError(f"source_too_large:{name}")
        actual = digest(path.read_bytes())
        if actual != expected:
            raise ValueError(f"source_hash_mismatch:{name}")
        source_files[name] = {"sha256": actual, "bytes": path.stat().st_size}

    category_counts = Counter()
    context_counts = Counter()
    flag_counts = Counter()
    pattern_flagged_rows = 0
    pattern_flagged_by_context = Counter()
    instruction_keys: dict[str, list[str]] = defaultdict(list)
    pair_keys: dict[str, list[str]] = defaultdict(list)
    records = []
    with (source / "databricks-dolly-15k.jsonl").open("rb") as stream:
        for line_number, raw in enumerate(stream, 1):
            row = json.loads(raw)
            if set(row) != {"instruction", "context", "response", "category"}:
                raise ValueError(f"invalid_fields:{line_number}")
            if any(not isinstance(value, str) for value in row.values()):
                raise ValueError(f"invalid_types:{line_number}")
            if (
                not row["instruction"].strip()
                or not row["response"].strip()
                or row["category"] not in CATEGORIES
            ):
                raise ValueError(f"invalid_content:{line_number}")
            category = row["category"]
            context = row["context"]
            has_context = bool(context.strip())
            if has_context != (category in CONTEXT_EXPECTED):
                raise ValueError(f"unexpected_context_category:{line_number}")
            locator = f"payload:{line_number}"
            combined = "\n".join((row["instruction"], context, row["response"]))
            flags = [
                label
                for label, pattern in (
                    ("email_pattern", EMAIL),
                    ("url_pattern", URL),
                    ("phone_pattern", PHONE),
                    ("long_number_pattern", LONG_NUMBER),
                )
                if pattern.search(combined)
            ]
            if flags:
                pattern_flagged_rows += 1
                pattern_flagged_by_context["present" if has_context else "absent"] += 1
            if has_context:
                flags.append("wikipedia_context_attribution_review")
                normalized_context = normalized(context)
                normalized_response = normalized(row["response"])
                if normalized_response == normalized_context:
                    flags.append("response_equals_context")
                elif (
                    len(normalized_response) >= 100
                    and normalized_response in normalized_context
                ):
                    flags.append("long_response_excerpt_in_context")
            for flag in flags:
                flag_counts[flag] += 1
            category_counts[category] += 1
            context_counts["present" if has_context else "absent"] += 1
            instruction_key = digest(normalized(row["instruction"]).encode())
            pair_key = digest(
                (normalized(row["instruction"]) + "\n" + normalized(context)).encode()
            )
            instruction_keys[instruction_key].append(locator)
            pair_keys[pair_key].append(locator)
            records.append(
                {
                    "source_locator": locator,
                    "source_revision": REVISION,
                    "row_sha256": digest(raw.rstrip(b"\r\n")),
                    "category": category,
                    "context_present": has_context,
                    "review_flags": flags,
                }
            )
    if len(records) != 15011:
        raise ValueError("unexpected_row_count")

    def duplicate_summary(groups: dict[str, list[str]]) -> dict:
        repeated = [ids for ids in groups.values() if len(ids) > 1]
        return {
            "groups": len(repeated),
            "rows": sum(len(ids) for ids in repeated),
            "source_locators": repeated,
        }

    output.mkdir(parents=True, exist_ok=True)
    inventory = output / "row-hashes.jsonl"
    inventory.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in records
        )
    )
    summary = {
        "schema_version": 1,
        "candidate": "databricks/databricks-dolly-15k",
        "source_revision": REVISION,
        "status": "QUARANTINED_REVIEW_ONLY",
        "commercial_training_admission": "NOT_APPROVED",
        "source_files": source_files,
        "rows": len(records),
        "categories": dict(sorted(category_counts.items())),
        "context": dict(sorted(context_counts.items())),
        "review_flags": dict(sorted(flag_counts.items())),
        "pattern_flagged_rows": pattern_flagged_rows,
        "pattern_flagged_by_context": dict(sorted(pattern_flagged_by_context.items())),
        "normalized_instruction_duplicates": duplicate_summary(instruction_keys),
        "normalized_instruction_context_duplicates": duplicate_summary(pair_keys),
        "row_hash_inventory": {
            "path": inventory.name,
            "sha256": digest(inventory.read_bytes()),
        },
        "automated_review_limit": "Patterns and lexical duplicates do not establish author rights, privacy clearance, Wikipedia revision/attribution, five-split isolation, or model quality.",
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    audit(args.source_dir, args.out_dir)
