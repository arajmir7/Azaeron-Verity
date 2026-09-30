"""Checkpoint-bound held-out metrics. Never substitute fixtures for release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import time

from .policy import DatasetManifest, PolicyError, canonical, digest


def retrieval_metrics(rankings, relevant, k=10):
    recalls, reciprocal, ndcg = [], [], []
    for ranking, truth in zip(rankings, relevant, strict=True):
        truth = set(truth)
        if not truth or len(ranking) != len(set(ranking)):
            raise PolicyError("invalid_retrieval_judgments")
        hits = [i + 1 for i, item in enumerate(ranking) if item in truth]
        recalls.append(sum(position <= k for position in hits) / len(truth))
        reciprocal.append(1 / hits[0] if hits else 0)
        dcg = sum(1 / math.log2(i + 1) for i in hits if i <= k)
        ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(truth))))
        ndcg.append(dcg / ideal)
    return {
        "recall_at_k": statistics.mean(recalls),
        "mrr": statistics.mean(reciprocal),
        "ndcg_at_k": statistics.mean(ndcg),
    }


def classification_metrics(probabilities, labels, threshold=0.9):
    if not labels or len(probabilities) != len(labels):
        raise PolicyError("empty_or_mismatched_predictions")
    for values in probabilities:
        if (
            not all(math.isfinite(v) and 0 <= v <= 1 for v in values)
            or abs(sum(values) - 1) > 1e-5
        ):
            raise PolicyError("invalid_probabilities")
    predictions = [max(range(len(p)), key=p.__getitem__) for p in probabilities]
    confidence = [max(p) for p in probabilities]
    accepted = [c >= threshold for c in confidence]
    bins = []
    for b in range(10):
        indices = [i for i, c in enumerate(confidence) if min(int(c * 10), 9) == b]
        if indices:
            bins.append(
                len(indices)
                / len(labels)
                * abs(
                    statistics.mean(confidence[i] for i in indices)
                    - statistics.mean(predictions[i] == labels[i] for i in indices)
                )
            )
    human = sum(label == 0 for label in labels)
    false = sum(
        y == 0 and p != 0 and a
        for y, p, a in zip(labels, predictions, accepted, strict=True)
    )
    # One-sided conservative Wilson bound (z=1.96); no zero-error certainty claim.
    rate = false / human if human else 1
    z = 1.96
    upper = (
        (
            (
                rate
                + z * z / (2 * human)
                + z * math.sqrt(rate * (1 - rate) / human + z * z / (4 * human * human))
            )
            / (1 + z * z / human)
        )
        if human
        else 1
    )
    return {
        "accuracy": statistics.mean(
            p == y for p, y in zip(predictions, labels, strict=True)
        ),
        "ece": sum(bins),
        "brier": statistics.mean(
            sum((p - int(j == y)) ** 2 for j, p in enumerate(values))
            for values, y in zip(probabilities, labels, strict=True)
        ),
        "coverage": statistics.mean(accepted),
        "human_fpr": rate,
        "human_fpr_upper95": upper,
        "recall_by_class": {
            str(c): sum(
                y == c and p == c and a
                for y, p, a in zip(labels, predictions, accepted, strict=True)
            )
            / max(1, labels.count(c))
            for c in range(len(probabilities[0]))
        },
    }


def evaluate(
    bundle: Path,
    dataset: Path,
    output: Path,
    *,
    smoke=False,
    review: Path | None = None,
):
    import torch
    from .network import load_network, encode, padded, VERIFIER_LABELS, DETECTOR_LABELS
    from .predict import generate

    manifest = DatasetManifest.model_validate_json(dataset.read_bytes())
    training = json.loads((bundle / "training-manifest.json").read_bytes())
    checkpoint_hash = digest(bundle / "checkpoint.safetensors")
    if training["checkpoint_sha256"] != checkpoint_hash or training[
        "dataset_manifest_sha256"
    ] != digest(dataset):
        raise PolicyError("evaluation_lineage_mismatch")
    family = training["family"]
    rows = manifest.load_rows(dataset.parent, family, smoke=smoke)
    model = load_network(bundle)
    torch.set_num_threads(1)
    context = model.architecture.context
    test = rows["evaluation"]
    metrics, calibration, durations = {}, None, []

    def probabilities(split, temperature):
        values = []
        for row in split:
            started = time.perf_counter()
            with torch.inference_mode():
                logits = model(padded([encode(row["input"], context)], "cpu"))
                values.append((logits / temperature).softmax(-1)[0].tolist())
            durations.append((time.perf_counter() - started) * 1000)
        return values

    if family in {"detector", "verifier"}:
        names = DETECTOR_LABELS if family == "detector" else VERIFIER_LABELS
        cal_labels = [names.index(row["target"]) for row in rows["calibration"]]
        trials = []
        for temperature in [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]:
            values = probabilities(rows["calibration"], temperature)
            nll = statistics.mean(
                -math.log(max(p[y], 1e-12))
                for p, y in zip(values, cal_labels, strict=True)
            )
            trials.append((nll, temperature))
        temperature = min(trials)[1]
        labels = [names.index(row["target"]) for row in test]
        probs = probabilities(test, temperature)
        metrics = classification_metrics(probs, labels)
        ood = [i for i, row in enumerate(test) if row["group"].startswith("ood:")]
        metrics["ood_accuracy"] = (
            classification_metrics([probs[i] for i in ood], [labels[i] for i in ood])[
                "accuracy"
            ]
            if ood
            else None
        )
        calibration = {
            "checkpoint_sha256": checkpoint_hash,
            "split_sha256": manifest.splits["calibration"].sha256,
            "temperature": temperature,
            "threshold": 0.9,
            "classes": names,
            "examples": len(cal_labels),
            "purpose": manifest.purpose,
        }
        checks = {
            "accuracy": metrics["accuracy"] >= 0.95,
            "calibration": metrics["ece"] <= 0.05,
            "ood": metrics["ood_accuracy"] is not None
            and metrics["ood_accuracy"] >= 0.9,
            "class_coverage": set(labels) == set(range(len(names)))
            and set(cal_labels) == set(range(len(names))),
            "coverage": metrics["coverage"] >= 0.8,
        }
        if family == "verifier":
            checks["contradiction_unsupported_uncertainty_recall"] = all(
                value >= 0.95 for value in metrics["recall_by_class"].values()
            )
            for category in ["number", "date", "entity", "citation", "negation"]:
                indices = [
                    i
                    for i, row in enumerate(test)
                    if row["group"].startswith(category + ":")
                ]
                checks[category + "_stress_slice"] = (
                    bool(indices)
                    and classification_metrics(
                        [probs[i] for i in indices], [labels[i] for i in indices]
                    )["accuracy"]
                    >= 0.95
                )
        if family == "detector":
            checks.update(
                low_false_positives=metrics["human_fpr_upper95"] <= 0.01,
                mixed_recall=metrics["recall_by_class"]["2"] >= 0.9,
            )
    elif family == "embed":

        def vectors(texts):
            with torch.inference_mode():
                return torch.cat(
                    [model(padded([encode(text, context)], "cpu")) for text in texts]
                )

        started = time.perf_counter()
        scores = (
            vectors([r["input"] for r in test]) @ vectors([r["target"] for r in test]).T
        )
        durations.append((time.perf_counter() - started) * 1000 / len(test))
        rankings = scores.argsort(dim=-1, descending=True).tolist()
        metrics = retrieval_metrics(rankings, [[i] for i in range(len(test))])
        checks = {
            "recall": metrics["recall_at_k"] >= 0.95,
            "mrr": metrics["mrr"] >= 0.9,
            "ndcg": metrics["ndcg_at_k"] >= 0.9,
        }
    else:
        from app.modules.verification.service import deterministic_reasons

        preserved, exact, candidates = [], [], {}
        for row in test:
            started = time.perf_counter()
            candidate = generate(
                model,
                row["input"],
                max_tokens=min(256, context - len(row["input"].encode()) - 3),
            )["text"]
            durations.append((time.perf_counter() - started) * 1000)
            preserved.append(not deterministic_reasons(row["target"], candidate))
            exact.append(candidate == row["target"])
            candidates[row["id"]] = hashlib.sha256(candidate.encode()).hexdigest()
        metrics = {
            "reference_invariant_preservation": statistics.mean(preserved),
            "exact_reference_match": statistics.mean(exact),
        }
        checks = {
            "reference_invariants": metrics["reference_invariant_preservation"] >= 0.99,
            "blind_naturalness_instruction_fidelity_review": False,
            "independent_factual_citation_semantic_review": False,
        }
        if review is not None:
            from .human_review import writer_review

            ratings, review_hash = writer_review(
                review, checkpoint_hash, digest(dataset), candidates
            )
            metrics.update(ratings)
            metrics["human_review_sha256"] = review_hash
            checks["blind_naturalness_instruction_fidelity_review"] = all(
                ratings[key] >= 0.95
                for key in [
                    "naturalness",
                    "instruction_following",
                    "semantic_preservation",
                ]
            )
            checks["independent_factual_citation_semantic_review"] = all(
                ratings[key] >= 0.99
                for key in [
                    "factual_preservation",
                    "citation_preservation",
                    "hallucination_free",
                ]
            )
    checks["evaluation_sample_size"] = len(test) >= 1000
    checks["production_data"] = (
        manifest.purpose == "PRODUCTION"
        and training["purpose"] == "PRODUCTION"
        and not smoke
    )
    metrics["latency_ms_p95"] = sorted(durations)[
        min(len(durations) - 1, math.ceil(len(durations) * 0.95) - 1)
    ]
    report = {
        "schema_version": 1,
        "gate": "evaluation",
        "status": "PASS" if all(checks.values()) else "BLOCKED",
        "checkpoint_sha256": checkpoint_hash,
        "dataset_manifest_sha256": digest(dataset),
        "evaluation_split_sha256": manifest.splits["evaluation"].sha256,
        "family": family,
        "purpose": manifest.purpose,
        "examples": len(test),
        "metrics": metrics,
        "checks": checks,
        "calibration": calibration,
        "baseline_comparison": "NOT_RUN",
        "production_load_benchmark": "NOT_RUN",
    }
    output.write_bytes(canonical(report) + b"\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["bundle", "dataset", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    report = evaluate(
        args.bundle, args.dataset, args.output, smoke=args.smoke, review=args.review
    )
    print(
        json.dumps({k: report[k] for k in ["status", "family", "examples", "checks"]})
    )


if __name__ == "__main__":
    main()
