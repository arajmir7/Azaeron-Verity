"""Read-only, hash-bound audit of the publisher's pinned GSM8K files.

The script emits only hashes and review flags, never source text. It does not
create a training manifest or an admission decision.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

REVISION = "3101c7d5072418e28b9008a6636bde82a006892c"
EXPECTED = {
    "LICENSE": "86bbb73e855821d7c401912fd4bf82e34313e6e3b6fd6f909f2b6cc9e209a53b",
    "train.jsonl": "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465",
    "test.jsonl": "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14",
}
EXPECTED_ROWS = {"train": 7473, "test": 1319}
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


def template(text: str) -> str:
    return re.sub(r"\b\d+(?:[.,]\d+)*\b", "<n>", normalized(text))


def inspect(source: Path, output: Path) -> None:
    files = {}
    for name, expected in EXPECTED.items():
        path = source / name
        if path.stat().st_size > 10_000_000:
            raise ValueError(f"source_too_large:{name}")
        actual = digest(path.read_bytes())
        if actual != expected:
            raise ValueError(f"source_hash_mismatch:{name}")
        files[name] = {"sha256": actual, "bytes": path.stat().st_size}

    output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    counts: dict[str, Counter] = defaultdict(Counter)
    exact: dict[str, list[str]] = defaultdict(list)
    templates: dict[str, list[str]] = defaultdict(list)
    answer_markers = Counter()

    for split, expected_count in EXPECTED_ROWS.items():
        with (source / f"{split}.jsonl").open("rb") as stream:
            for line_number, raw in enumerate(stream, 1):
                row = json.loads(raw)
                if set(row) != {"question", "answer"} or not all(
                    isinstance(row[field], str) and row[field].strip()
                    for field in ("question", "answer")
                ):
                    raise ValueError(f"invalid_row:{split}:{line_number}")
                key = f"{split}:{line_number}"
                question, answer = row["question"], row["answer"]
                content = question + "\n" + answer
                flags = [
                    name
                    for name, pattern in (
                        ("email_pattern", EMAIL),
                        ("url_pattern", URL),
                        ("phone_pattern", PHONE),
                        ("long_number_pattern", LONG_NUMBER),
                    )
                    if pattern.search(content)
                ]
                for flag in flags:
                    counts[split][flag] += 1
                if flags:
                    counts[split]["pattern_flagged_rows"] += 1
                marker_count = answer.count("####")
                answer_markers[marker_count] += 1
                if marker_count != 1:
                    flags.append("answer_marker_review")
                q_normal = normalized(question)
                q_template = template(question)
                exact[digest(q_normal.encode())].append(key)
                templates[digest(q_template.encode())].append(key)
                records.append(
                    {
                        "source_locator": key,
                        "source_revision": REVISION,
                        "row_sha256": digest(raw.rstrip(b"\r\n")),
                        "question_sha256": digest(question.encode()),
                        "answer_sha256": digest(answer.encode()),
                        "review_flags": flags,
                    }
                )
                counts[split]["rows"] += 1
        if counts[split]["rows"] != expected_count:
            raise ValueError(f"unexpected_count:{split}")

    def overlap(groups: dict[str, list[str]]) -> list[list[str]]:
        return [
            ids
            for ids in groups.values()
            if len(ids) > 1 and len({item.split(":", 1)[0] for item in ids}) > 1
        ]

    rows_path = output / "row-hashes.jsonl"
    rows_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in records
        )
    )
    summary = {
        "schema_version": 1,
        "candidate": "openai/grade-school-math:main",
        "source_revision": REVISION,
        "status": "QUARANTINED_REVIEW_ONLY",
        "commercial_training_admission": "NOT_APPROVED",
        "license_source_sha256": files["LICENSE"]["sha256"],
        "source_files": files,
        "counts": {
            split: dict(sorted(counts[split].items())) for split in EXPECTED_ROWS
        },
        "answer_marker_counts": dict(sorted(answer_markers.items())),
        "exact_question_cross_split_overlap": overlap(exact),
        "number_template_cross_split_overlap": overlap(templates),
        "row_hash_inventory": {
            "path": rows_path.name,
            "sha256": digest(rows_path.read_bytes()),
        },
        "automated_review_limit": "Pattern flags and lexical overlap are not copyright, contributor-authority, privacy, semantic-leakage, or quality clearance.",
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    inspect(args.source_dir, args.out_dir)
