"""Rights-filtered, paper-isolation audit of the pinned arXivEdits release.

Only aggregate counts and source hashes are emitted. This is not a rights or
privacy approval and does not export training rows.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

EXPECTED = {
    "data/edits/train.json": "22b8e4b8f2e5dd4710665bc5077456b4f455fa2d0e07b31635f5dc89a99e44d1",
    "data/edits/dev.json": "2280be90e03f7cb794769d82b92b1769fa8ec84fa0e563df6a9a3a3a1a8840a6",
    "data/edits/test.json": "d0db73e78cf0c3086146d7339307a870769f5a50b0e0a969478b45041bb9ece3",
    "data/sentence_alignment/train.json": "6ee44429681edb7eab39a90d9272aa28e79473458d8d5b94cb99394c173ad184",
    "data/sentence_alignment/dev.json": "2252147b738a52133f7617b352c7e77639b0efe951adeacb3e371a4cd6dbfadf",
    "data/sentence_alignment/test.json": "995f042d44e87c2d891429e2d30bf22c9f97a4dd9c3799854944325b31a18eb0",
}
PERMISSIVE = {
    "http://creativecommons.org/licenses/by/3.0/",
    "http://creativecommons.org/licenses/by/4.0/",
    "http://creativecommons.org/licenses/publicdomain/",
    "http://creativecommons.org/publicdomain/zero/1.0/",
}


def verify(path: Path, expected: str) -> None:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    if hasher.hexdigest() != expected:
        raise ValueError(f"source SHA-256 mismatch: {path.name}")


def audit(source: Path) -> dict:
    for relative, sha in EXPECTED.items():
        verify(source / relative, sha)
    per_split = {}
    paper_ids = {}
    for split in ("train", "dev", "test"):
        papers = json.loads(
            (source / "data/sentence_alignment" / f"{split}.json").read_text()
        )
        edits = json.loads((source / "data/edits" / f"{split}.json").read_text())
        licenses = Counter()
        eligible = set()
        for paper_id, paper in papers.items():
            version_licenses = paper.get("license", {})
            source_license = version_licenses.get("1")
            target_license = version_licenses.get("2")
            licenses[f"{source_license} -> {target_license}"] += 1
            if source_license in PERMISSIVE and target_license in PERMISSIVE:
                eligible.add(paper_id)
        edited_papers = {edit["arxiv-id"] for edit in edits.values()}
        paper_ids[split] = edited_papers
        per_split[split] = {
            "published_aligned_papers": len(papers),
            "published_annotated_edits": len(edits),
            "annotated_papers": len(edited_papers),
            "annotated_paper_ids_missing_alignment": len(edited_papers - set(papers)),
            "papers_with_both_versions_in_positive_commercial_reuse_license": len(
                eligible
            ),
            "annotated_edits_with_both_versions_positive": sum(
                edit["arxiv-id"] in eligible for edit in edits.values()
            ),
            "publisher_license_pairs_by_paper": dict(licenses),
        }
    overlaps = {
        f"{left}_{right}": len(paper_ids[left] & paper_ids[right])
        for left, right in (("train", "dev"), ("train", "test"), ("dev", "test"))
    }
    return {
        "status": "QUARANTINED_REVIEW_ONLY",
        "source_repository": "https://github.com/chaojiang06/arXivEdits",
        "source_revision": "113913d68522c1c8428d8e191d5c9bed633da6ce",
        "source_sha256": EXPECTED,
        "positive_license_filter": "Both version 1 and version 2 must have publisher-recorded CC BY 3.0/4.0, CC0 or public-domain URL; unknown, noncommercial, share-alike and arXiv nonexclusive-distribution excluded",
        "results_by_split": per_split,
        "annotated_paper_ids_cross_split_overlap": overlaps,
        "source_to_target_version_mapping_independently_confirmed": False,
        "row_level_privacy_and_copyright_review": "NOT_DONE",
        "task_coverage": "Scientific sentence revision only; no chat, summary, document QA, VoiceLock or OOD set",
        "admitted_rows": 0,
        "training_permitted_by_azaeron_gate": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.source_dir)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k != "source_sha256"}, indent=2)
    )


if __name__ == "__main__":
    main()
