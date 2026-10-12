"""Hash-only, non-training audit of the pinned Aya English original annotations.

The parquet payloads remain outside this repository. The output never contains
prompt, completion, or publisher user IDs. Requires duckdb==1.4.1.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata

import duckdb

REVISION = "f9ea04583f02a8f86404ff6c58bf75fe637df8a2"
EXPECTED = {
    "README.md": "3ac54f63eec84100c155571945da01c7c18cd8ec97ea94639e2b94a6860e8573",
    "train.parquet": "51baa85043b569ba117f41516b32d1b0e4e2647fb203a08933f98a556fb1fb06",
    "test.parquet": "52bbb79461bff9887c9987a5737d9a06f5ec6c78c08d770828c37fc182ce2cca",
}
FLAGS = {
    "email_pattern": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    "url_pattern": re.compile(r"https?://\S+", re.I),
    "phone_pattern": re.compile(
        r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)"
    ),
    "long_number_pattern": re.compile(r"(?<!\d)\d{9,}(?!\d)"),
    "copyright_notice_pattern": re.compile(
        r"\b(?:copyright|all rights reserved|©)\b", re.I
    ),
}
TASKS = {
    "rewrite_or_edit": re.compile(
        r"\b(rewrite|rephrase|paraphrase|edit|proofread|improve (?:the )?(?:writing|text|sentence)|make (?:this|it) sound)\b",
        re.I,
    ),
    "summarize": re.compile(r"\b(summariz[es]|summary|briefly recap)\b", re.I),
    "explain": re.compile(
        r"\b(explain|describe how|describe why|what (?:does|is) .* mean)\b", re.I
    ),
    "creative_writing": re.compile(
        r"\b(write|compose|draft|create)\b.*\b(story|poem|letter|essay|speech|article|paragraph)\b",
        re.I,
    ),
    "structured_extraction": re.compile(
        r"\b(extract|list|identify)\b.*\b(from|in the following|entities|details)\b",
        re.I,
    ),
    "document_question": re.compile(
        r"\b(according to|based on (?:the|this) (?:text|document|passage)|in (?:the|this) passage)\b",
        re.I,
    ),
}
SPLITS = ("train", "validation", "calibration", "test", "ood")
TARGET_FRACTIONS = (0.70, 0.075, 0.075, 0.075, 0.075)


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", value, re.UNICODE))


def rows(connection: duckdb.DuckDBPyConnection, path: Path) -> list[dict]:
    query = """SELECT file_row_number, inputs, targets, language_code,
                      annotation_type, user_id
               FROM read_parquet(?, file_row_number=true)
               WHERE language_code='eng' AND annotation_type='original-annotations'
               ORDER BY file_row_number"""
    output = []
    for ordinal, prompt, answer, language, kind, user_id in connection.execute(
        query, [str(path)]
    ).fetchall():
        if not all(
            isinstance(x, str) and x.strip()
            for x in (prompt, answer, language, kind, user_id)
        ):
            raise ValueError(f"invalid_english_original_row:{path.name}:{ordinal}")
        payload = {
            "inputs": prompt,
            "targets": answer,
            "language_code": language,
            "annotation_type": kind,
            "user_id": user_id,
        }
        text = prompt + "\n" + answer
        flags = [name for name, regex in FLAGS.items() if regex.search(text)]
        if len(answer.strip()) < 20:
            flags.append("short_target_review")
        if len(answer) > 2000:
            flags.append("long_target_review")
        if normalized(prompt) == normalized(answer):
            flags.append("target_equals_input_review")
        latin_letters = sum("a" <= char.casefold() <= "z" for char in text)
        all_letters = sum(char.isalpha() for char in text)
        if all_letters and latin_letters / all_letters < 0.7:
            flags.append("english_language_label_review")
        output.append(
            {
                "locator": f"{path.stem}:{ordinal}",
                "row_sha256": digest(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
                "author_sha256": digest("aya-author-v1:" + user_id),
                "input_key_sha256": digest(normalized(prompt)),
                "target_key_sha256": (
                    digest(normalized(answer))
                    if len(normalized(answer)) >= 80
                    else None
                ),
                "flags": flags,
                "task_tags": [
                    name for name, regex in TASKS.items() if regex.search(prompt)
                ],
            }
        )
    return output


def components(train: list[dict]) -> list[list[dict]]:
    parent = {row["author_sha256"]: row["author_sha256"] for row in train}

    def find(key: str) -> str:
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def merge(first: str, second: str) -> None:
        left, right = find(first), find(second)
        parent[max(left, right)] = min(left, right)

    for key_name in ("input_key_sha256", "target_key_sha256"):
        owner: dict[str, str] = {}
        for row in train:
            key = row[key_name]
            if key is None:
                continue
            previous = owner.setdefault(key, row["author_sha256"])
            merge(previous, row["author_sha256"])

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in train:
        groups[find(row["author_sha256"])].append(row)
    return sorted(
        groups.values(), key=lambda group: (-len(group), group[0]["author_sha256"])
    )


def audit(source: Path, output: Path) -> None:
    source_files = {}
    for name, expected in EXPECTED.items():
        path = source / name
        actual = file_hash(path)
        if actual != expected:
            raise ValueError(f"source_hash_mismatch:{name}")
        source_files[name] = {"sha256": actual, "bytes": path.stat().st_size}

    connection = duckdb.connect(database=":memory:")
    train = rows(connection, source / "train.parquet")
    published_test = rows(connection, source / "test.parquet")
    if (len(train), len(published_test)) != (2164, 250):
        raise ValueError("source_row_count_changed")

    test_authors = {row["author_sha256"] for row in published_test}
    test_inputs = {row["input_key_sha256"] for row in published_test}
    author_overlap = {row["author_sha256"] for row in train} & test_authors
    test_prompt_overlap = {row["input_key_sha256"] for row in train} & test_inputs
    input_groups: dict[str, int] = Counter(row["input_key_sha256"] for row in train)
    target_groups: dict[str, int] = Counter(
        row["target_key_sha256"] for row in train if row["target_key_sha256"]
    )
    lengths = connection.execute(
        """SELECT quantile_cont(length(inputs), 0.5), quantile_cont(length(inputs), 0.95),
                  quantile_cont(length(targets), 0.5), quantile_cont(length(targets), 0.95)
           FROM read_parquet(?) WHERE language_code='eng' AND annotation_type='original-annotations'""",
        [str(source / "train.parquet")],
    ).fetchone()

    # A provisional review partition only. The publisher test is excluded because
    # all its English authors also occur in publisher train.
    groups = components(train)
    assigned = dict.fromkeys(SPLITS, 0)
    row_split = {}
    targets = dict(zip(SPLITS, (len(train) * x for x in TARGET_FRACTIONS)))
    for group in groups:
        split = max(
            SPLITS,
            key=lambda name: (targets[name] - assigned[name], -SPLITS.index(name)),
        )
        assigned[split] += len(group)
        for row in group:
            row_split[row["locator"]] = split

    inventory = []
    flag_counts = Counter()
    task_counts = Counter()
    for row in train + published_test:
        flags = list(row["flags"])
        if row in train:
            if input_groups[row["input_key_sha256"]] > 1:
                flags.append("duplicate_normalized_prompt_review")
            if row["target_key_sha256"] and target_groups[row["target_key_sha256"]] > 1:
                flags.append("duplicate_long_target_review")
            if row["input_key_sha256"] in test_prompt_overlap:
                flags.append("published_test_prompt_overlap")
        else:
            flags.append("publisher_test_excluded")
        flag_counts.update(flags)
        if row in train:
            task_counts.update(row["task_tags"])
        inventory.append(
            {
                "source_locator": row["locator"],
                "source_revision": REVISION,
                "row_sha256": row["row_sha256"],
                "author_sha256": row["author_sha256"],
                "input_key_sha256": row["input_key_sha256"],
                "provisional_review_split": row_split.get(row["locator"]),
                "review_flags": sorted(flags),
                "heuristic_task_tags": row["task_tags"],
                "status": "QUARANTINED_REVIEW_ONLY",
            }
        )

    split_authors = {name: set() for name in SPLITS}
    split_inputs = {name: set() for name in SPLITS}
    split_targets = {name: set() for name in SPLITS}
    for row in train:
        split = row_split[row["locator"]]
        split_authors[split].add(row["author_sha256"])
        split_inputs[split].add(row["input_key_sha256"])
        if row["target_key_sha256"]:
            split_targets[split].add(row["target_key_sha256"])
    for index, first in enumerate(SPLITS):
        for second in SPLITS[index + 1 :]:
            if (
                split_authors[first] & split_authors[second]
                or split_inputs[first] & split_inputs[second]
                or split_targets[first] & split_targets[second]
            ):
                raise ValueError(f"provisional_split_leakage:{first}:{second}")

    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / "row-hashes.jsonl"
    inventory_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in inventory
        )
    )
    summary = {
        "schema_version": 1,
        "candidate": "CohereLabs/aya_dataset:English:original-annotations",
        "source_revision": REVISION,
        "status": "QUARANTINED_REVIEW_ONLY",
        "commercial_training_admission": "NOT_APPROVED",
        "source_files": source_files,
        "english_original_train_rows": len(train),
        "english_original_publisher_test_rows_excluded": len(published_test),
        "train_authors": len({row["author_sha256"] for row in train}),
        "publisher_test_authors": len(test_authors),
        "publisher_train_test_author_overlap": len(author_overlap),
        "publisher_train_test_prompt_overlap": len(test_prompt_overlap),
        "duplicate_normalized_prompt_groups": sum(
            count > 1 for count in input_groups.values()
        ),
        "duplicate_normalized_prompt_rows": sum(
            count for count in input_groups.values() if count > 1
        ),
        "duplicate_long_target_groups": sum(
            count > 1 for count in target_groups.values()
        ),
        "english_original_length_characters": {
            "prompt_p50": lengths[0],
            "prompt_p95": lengths[1],
            "target_p50": lengths[2],
            "target_p95": lengths[3],
        },
        "pattern_and_overlap_flags": dict(sorted(flag_counts.items())),
        "heuristic_task_counts": dict(sorted(task_counts.items())),
        "provisional_author_isolated_review_split_rows": assigned,
        "provisional_author_isolated_review_split_authors": {
            name: len(split_authors[name]) for name in SPLITS
        },
        "largest_source_group_rows": max(len(group) for group in groups),
        "source_groups": len(groups),
        "cross_provisional_split_author_prompt_long_target_overlap": 0,
        "ood_limitation": "Author holdout only; no adjudicated domain-shift OOD set.",
        "row_hash_inventory": {
            "path": inventory_path.name,
            "sha256": file_hash(inventory_path),
        },
        "automated_review_limit": "Publisher Apache-2.0 and data-card commercial statement do not prove each contributor's grant, each row's original copyright status, privacy clearance, professional editing, or task-complete Writer quality. No row is admitted.",
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()
    audit(arguments.source_dir, arguments.out_dir)
