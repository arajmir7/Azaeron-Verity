"""Read-only HelpSteer3 edit audit; writes hashes and aggregate review leads only.

The script never exports prompts or edited text. Results do not grant rights or
privacy approval, and approximate duplicate screening does not prove isolation.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re

EXPECTED = {
    "README.md": "d5d46db58e8374937ea284b33b1583a4a465b232bf74b941745d80e3c35fd8ae",
    "edit/train.jsonl.gz": "c0d4208ddedd1bb66845fd29ff8be2549e8dde7dda720af944bd9308df688df2",
    "edit/validation.jsonl.gz": "80ac8fa3d204e71778aa7a09e1f8050d247b758d85f8a6d27014757aaef8c74c",
    "edit_quality/train.jsonl.gz": "5df23b690d2d3fb8347d9fcf0e15f521d580a1d3347f68d4815b378a28ba0d1f",
    "edit_quality/validation.jsonl.gz": "6c89444f8be151b62a0e0d9693d470fbd21ccd226c656fa788556ab650df8184",
}
EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
URL = re.compile(r"(?i)https?://[^\s<>()]+")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PHONE = re.compile(r"(?<!\w)(?:\+?\d[\s.()-]?){10,14}(?!\w)")
NUMBER = re.compile(r"(?<!\w)[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?!\w)")
WORDS = re.compile(r"\w+")
SUMMARY = re.compile(r"(?i)\b(?:summari[sz]e|summary|tldr|tl;dr|abstract)\b")
REWRITE = re.compile(
    r"(?i)\b(?:rewrit(?:e|ing)|rephras(?:e|ing)|polish|edit|proofread|improv(?:e|ing)\s+(?:the\s+)?(?:writing|text|prose)|tone|style)\b"
)
DOCUMENT_QA = re.compile(
    r"(?i)\b(?:according to|based on|in the (?:document|passage|article)|the provided (?:text|context)|given (?:document|passage|context))\b"
)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def context_text(row: dict) -> str:
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in row["context"])


def shingles(text: str) -> set[int]:
    words = WORDS.findall(text.casefold())
    return {
        int.from_bytes(
            hashlib.blake2b(
                " ".join(words[i : i + 5]).encode(), digest_size=8
            ).digest(),
            "big",
        )
        for i in range(max(0, len(words) - 4))
    }


def signature(values: set[int]) -> tuple[int, ...] | None:
    if len(values) < 10:
        return None
    bottom = sorted(values)[:32]
    return tuple(bottom + [2**64 - 1] * (32 - len(bottom)))


def lead_names(text: str) -> list[str]:
    patterns = {"email": EMAIL, "url": URL, "ipv4": IPV4, "phone_pattern": PHONE}
    return [name for name, pattern in patterns.items() if pattern.search(text)]


def verify_source(source: Path) -> None:
    for relative, expected in EXPECTED.items():
        path = source / relative
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
        actual = hasher.hexdigest()
        if actual != expected:
            raise ValueError(f"source SHA-256 mismatch: {relative}")


def audit(source: Path, output: Path) -> dict:
    verify_source(source)
    output.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    domains: dict[str, Counter[str]] = defaultdict(Counter)
    languages: dict[str, Counter[str]] = defaultdict(Counter)
    flags: Counter[str] = Counter()
    task_leads: Counter[str] = Counter()
    contexts: dict[str, list[tuple[str, int]]] = defaultdict(list)
    originals: dict[str, list[tuple[str, int]]] = defaultdict(list)
    edited: dict[str, list[tuple[str, int]]] = defaultdict(list)
    train_buckets: dict[
        tuple[int, tuple[int, ...]], list[tuple[int, str, set[int]]]
    ] = defaultdict(list)
    validation_signatures: list[tuple[int, str, set[int], tuple[int, ...] | None]] = []
    edit_train_signature_count = 0
    with (output / "row-hashes.jsonl").open("w") as hashes:
        for relative in EXPECTED:
            if not relative.endswith(".jsonl.gz"):
                continue
            split = relative.rsplit("/", 1)[1].split(".", 1)[0]
            section = relative.split("/", 1)[0]
            with gzip.open(source / relative, "rt", encoding="utf-8") as stream:
                for ordinal, line in enumerate(stream):
                    row = json.loads(line)
                    context = context_text(row)
                    original = row["original_response"]
                    result = row.get("edited_response", row.get("good_edited_response"))
                    if not isinstance(result, str):
                        raise ValueError(
                            f"missing human edit in {relative} row {ordinal}"
                        )
                    where = f"{section}/{split}"
                    counts[where] += 1
                    domains[where][row["domain"]] += 1
                    languages[where][row["language"]] += 1
                    key = (where, ordinal)
                    context_digest = digest_bytes(normalized(context).encode())
                    original_digest = digest_bytes(normalized(original).encode())
                    result_digest = digest_bytes(normalized(result).encode())
                    contexts[context_digest].append(key)
                    originals[original_digest].append(key)
                    edited[result_digest].append(key)
                    text = "\n".join((context, original, result))
                    pii_leads = lead_names(text)
                    for name in pii_leads:
                        flags[f"pii_lead_{name}"] += 1
                    num_drift = Counter(NUMBER.findall(original)) != Counter(
                        NUMBER.findall(result)
                    )
                    if num_drift:
                        flags["number_change_lead"] += 1
                    unchanged = normalized(original) == normalized(result)
                    if unchanged:
                        flags["unchanged_edit_lead"] += 1
                    user_text = "\n".join(
                        turn["content"]
                        for turn in row["context"]
                        if turn["role"] == "user"
                    )
                    for tag, pattern in (
                        ("summary", SUMMARY),
                        ("rewrite", REWRITE),
                        ("document_qa", DOCUMENT_QA),
                    ):
                        if pattern.search(user_text):
                            task_leads[f"{where}:{tag}"] += 1
                    hashes.write(
                        json.dumps(
                            {
                                "file": relative,
                                "ordinal": ordinal,
                                "row_sha256": digest_bytes(line.encode()),
                                "context_normalized_sha256": context_digest,
                                "original_normalized_sha256": original_digest,
                                "edited_normalized_sha256": result_digest,
                                "pii_pattern_leads": pii_leads,
                                "number_change_lead": num_drift,
                                "unchanged_edit_lead": unchanged,
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    if (
                        section != "edit"
                        or row["domain"] not in {"general", "stem"}
                        or row["language"] != "english"
                    ):
                        continue
                    grams = shingles(context)
                    sig = signature(grams)
                    if split == "train" and sig:
                        edit_train_signature_count += 1
                        for band in range(8):
                            train_buckets[(band, sig[band * 4 : band * 4 + 4])].append(
                                (ordinal, context_digest, grams)
                            )
                    elif split == "validation":
                        validation_signatures.append(
                            (ordinal, context_digest, grams, sig)
                        )
    cross: dict[str, dict[str, int]] = {}
    for label, index in (
        ("normalized_context", contexts),
        ("normalized_original", originals),
        ("normalized_edited", edited),
    ):
        cross[label] = {
            "edit_train_vs_validation_keys": sum(
                1
                for matches in index.values()
                if any(p == "edit/train" for p, _ in matches)
                and any(p == "edit/validation" for p, _ in matches)
            ),
            "edit_vs_edit_quality_keys": sum(
                1
                for matches in index.values()
                if any(p.startswith("edit/") for p, _ in matches)
                and any(p.startswith("edit_quality/") for p, _ in matches)
            ),
            "repeated_keys_anywhere": sum(
                1 for matches in index.values() if len(matches) > 1
            ),
        }
    near_pairs: set[tuple[int, int]] = set()
    near_nonexact_pairs: set[tuple[int, int]] = set()
    near_candidate_pairs: set[tuple[int, int]] = set()
    for ordinal, val_context_digest, val_grams, sig in validation_signatures:
        if not sig:
            continue
        for band in range(8):
            for train_ordinal, train_context_digest, train_grams in train_buckets.get(
                (band, sig[band * 4 : band * 4 + 4]), ()
            ):
                pair = (train_ordinal, ordinal)
                if pair in near_candidate_pairs:
                    continue
                near_candidate_pairs.add(pair)
                intersection = len(train_grams & val_grams)
                union = len(train_grams) + len(val_grams) - intersection
                if union and intersection / union >= 0.8:
                    near_pairs.add(pair)
                    if train_context_digest != val_context_digest:
                        near_nonexact_pairs.add(pair)
    summary = {
        "status": "QUARANTINED_REVIEW_ONLY",
        "source_repository": "https://huggingface.co/datasets/nvidia/HelpSteer3",
        "source_revision": "f6d145777bcbde96137596340fab89793acd1031",
        "source_sha256": EXPECTED,
        "rows_by_section_split": dict(counts),
        "domains_by_section_split": {k: dict(v) for k, v in sorted(domains.items())},
        "languages_by_section_split": {
            k: dict(v) for k, v in sorted(languages.items())
        },
        "automated_review_leads_not_dispositions": dict(flags),
        "heuristic_user_prompt_task_leads_not_labels": dict(task_leads),
        "duplicate_normalized_keys": cross,
        "approximate_near_context_screen": {
            "method": "English general/stem only; 32-smallest 5-word-shingle hashes, 8x4 LSH bands, then exact Jaccard >=0.8 for candidates",
            "train_rows_indexed": edit_train_signature_count,
            "validation_rows_with_signature": sum(
                sig is not None for _, _, _, sig in validation_signatures
            ),
            "candidate_pairs_checked": len(near_candidate_pairs),
            "pairs_at_or_above_0_8_jaccard": len(near_pairs),
            "nonexact_pairs_at_or_above_0_8_jaccard": len(near_nonexact_pairs),
            "exhaustive": False,
        },
        "source_author_document_lineage_identifiers_in_rows": False,
        "publisher_splits": ["train", "validation"],
        "admitted_rows": 0,
        "training_permitted_by_azaeron_gate": False,
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.source_dir, args.out_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
