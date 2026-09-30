"""Train all four tiny TEST_ONLY checkpoints; reports mechanics, never readiness."""

import argparse
import json
from pathlib import Path

from app.modules.model_platform.policy import canonical, digest
from app.modules.model_platform.train import train
from app.modules.model_platform.evaluate import evaluate


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    results = []
    for family in ["writer", "verifier", "detector", "embed"]:
        work = root / family
        work.mkdir()
        splits, reviews = {}, {}
        for split_index, split in enumerate(["train", "calibration", "evaluation"]):
            # Program-authored symbols have no imported customer or benchmark text.
            rows = []
            for i in range(12):
                token = f"{split_index}-{i}"
                row = {
                    "id": token,
                    "group": ("ood:" if split == "evaluation" else "") + token,
                    "input": f"Symbol {token}",
                    "target": f"Symbol {token}",
                }
                if family == "verifier":
                    row["target"] = [
                        "equivalent",
                        "contradiction",
                        "unsupported",
                        "uncertain",
                    ][i % 4]
                if family == "detector":
                    row["target"] = ["human", "ai", "mixed"][i % 3]
                rows.append(row)
            source = work / (split + ".jsonl")
            source.write_bytes(b"\n".join(canonical(row) for row in rows) + b"\n")
            splits[split] = {"path": source.name, "sha256": digest(source)}
            review = work / (split + "-review.json")
            review.write_bytes(
                canonical(
                    {
                        "subject_sha256": digest(source),
                        "reviewer": "Program-authored synthetic fixture; TEST ONLY",
                        "reviewed_at": "2026-09-30",
                        "source": "model_platform_smoke.py numeric symbols",
                        "license": "Test fixture authored in this repository",
                        "commercial_training_rights": True,
                        "provenance": "PASS",
                        "pii_review": "PASS",
                        "copyright_review": "PASS",
                        "allowed_tasks": [family],
                        "evidence_reference": "This program generates numeric symbols without external/customer data. TEST_ONLY.",
                    }
                )
            )
            reviews[split] = {"path": review.name, "sha256": digest(review)}
        manifest = work / "dataset.json"
        manifest.write_bytes(
            canonical(
                {
                    "schema_version": 1,
                    "dataset_id": "synthetic-mechanics-" + family,
                    "purpose": "TEST_ONLY",
                    "source": "model_platform_smoke.py numeric symbols",
                    "license": "Test fixture authored in this repository",
                    "allowed_tasks": [family],
                    "splits": splits,
                    "reviews": reviews,
                }
            )
        )
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
