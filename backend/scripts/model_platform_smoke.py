"""Train all four tiny TEST_ONLY checkpoints; reports mechanics, never readiness."""

import argparse
import json
from pathlib import Path

from app.modules.model_platform.policy import canonical, digest
from app.modules.model_platform.train import train
from app.modules.model_platform.evaluate import evaluate
from app.modules.model_platform.datasets import Dataset, review_subject


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for family in ["writer", "verifier", "detector", "embed"]:
        work = root / family
        work.mkdir()
        splits = {}
        task = {
            "writer": "natural_prose",
            "verifier": "verify",
            "detector": "classify",
            "embed": "embed",
        }[family]
        for split_index, split in enumerate(
            ["train", "validation", "calibration", "test", "ood"]
        ):
            # Program-authored symbols have no imported customer or benchmark text.
            rows = []
            for i in range(12):
                token = f"{split_index}-{i}"
                row = {
                    "id": token,
                    "group": token,
                    "input": f"Symbol {token}",
                    "target": f"Symbol {token}",
                    "language": "fixture",
                    "domain": "numeric_symbols",
                    "task": task,
                    "slices": [],
                }
                if family == "verifier":
                    row["target"] = [
                        "equivalent",
                        "contradiction",
                        "unsupported",
                        "uncertain",
                    ][i % 4]
                if family == "detector":
                    row["target"] = ["HUMAN", "AI", "MIXED"][i % 3]
                    row["generator_family"] = "TEST_ONLY-" + split
                rows.append(row)
            source = work / (split + ".jsonl")
            source.write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
            splits[split] = {"path": source.name, "sha256": digest(source)}
        manifest = work / "dataset.json"
        dataset = Dataset(
            dataset_id="synthetic-mechanics-" + family,
            version="2",
            purpose="TEST_ONLY",
            source="model_platform_smoke.py numeric symbols",
            license="Test fixture authored in this repository",
            commercial_training_permission="GRANTED",
            derivative_permission="GRANTED",
            redistribution_permission="PROHIBITED",
            provenance="Program-generated numeric symbols",
            acquisition_method="This program; no external/customer text",
            copyright_review="PASS",
            pii_review="PASS",
            language=["fixture"],
            domain=["numeric_symbols"],
            quality_tier="TEST_FIXTURE",
            allowed_model_families=[family],
            allowed_tasks=[task],
            contains_customer_content=False,
            splits=splits,
            review={"path": "review.json", "sha256": "0" * 64},
        )
        review = work / "review.json"
        review.write_bytes(
            canonical(
                {
                    "subject_sha256": review_subject(dataset),
                    "reviewer": "TEST_ONLY program fixture",
                    "reviewer_kind": "TEST_FIXTURE",
                    "reviewed_at": "2026-10-01",
                    "evidence_reference": "Generated symbols, not a human production review",
                    "rights": "PASS",
                    "provenance": "PASS",
                    "copyright": "PASS",
                    "pii": "PASS",
                }
            )
        )
        metadata = dataset.model_dump()
        metadata["review"]["sha256"] = digest(review)
        manifest.write_bytes(canonical(metadata))
        config = work / "config.json"
        config.write_bytes(
            canonical(
                {
                    "family": family,
                    "dataset": {"path": manifest.name, "sha256": digest(manifest)},
                    "seed": 7,
                    "epochs": 3,
                    "batch_size": 4,
                    "learning_rate": 0.003,
                    "width": 32,
                    "heads": 4,
                    "layers": 1,
                    "context": 128,
                    "embedding_size": 16,
                    "device": "cpu",
                }
            )
        )
        training = train(config, work / "bundle", smoke=True)
        evaluation = evaluate(
            work / "bundle", manifest, work / "evaluation.json", smoke=True
        )
        results.append(
            {
                "family": family,
                "purpose": "TEST_ONLY",
                "training_steps": training["steps"],
                "checkpoint_sha256": training["checkpoint_sha256"],
                "initialization_sha256": training["initialization_sha256"],
                "checkpoint_changed": training["checkpoint_sha256"]
                != training["initialization_sha256"],
                "evaluation": evaluation["status"],
                "production_approval": "NOT_APPROVED",
            }
        )
        print(json.dumps(results[-1]), flush=True)
    (root / "results.json").write_bytes(canonical(results) + b"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
