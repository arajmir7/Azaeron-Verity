"""Aggregate blinded ratings bound to exact writer outputs, never manufacture them."""

import json
from pathlib import Path
import statistics

from .policy import PolicyError, digest

DIMENSIONS = {
    "naturalness",
    "instruction_following",
    "semantic_preservation",
    "factual_preservation",
    "citation_preservation",
    "hallucination_free",
}


def writer_review(
    path: Path, checkpoint: str, dataset: str, candidates: dict[str, str]
):
    data = json.loads(path.read_bytes())
    if (
        data.get("checkpoint_sha256") != checkpoint
        or data.get("dataset_manifest_sha256") != dataset
        or data.get("method") != "blinded_independent_ratings_v1"
    ):
        raise PolicyError("writer_review_lineage_mismatch")
    rows = data.get("ratings", [])
    seen, reviewers = set(), set()
    values: dict[str, list[float]] = {key: [] for key in DIMENSIONS}
    for row in rows:
        identifier, reviewer = row["example_id"], row["reviewer"]
        if (
            identifier not in candidates
            or row["candidate_sha256"] != candidates[identifier]
            or not isinstance(reviewer, str)
            or not reviewer.strip()
            or (identifier, reviewer) in seen
            or set(row["scores"]) != DIMENSIONS
        ):
            raise PolicyError("invalid_writer_rating")
        seen.add((identifier, reviewer))
        reviewers.add(reviewer)
        for key, score in row["scores"].items():
            if type(score) not in (int, float) or not 0 <= score <= 1:
                raise PolicyError("invalid_writer_score")
            values[key].append(score)
    if len(reviewers) < 2 or any(
        sum(example == identifier for example, _ in seen) < 2
        for identifier in candidates
    ):
        raise PolicyError("independent_writer_review_incomplete")
    return {key: statistics.mean(scores) for key, scores in values.items()}, digest(
        path
    )
