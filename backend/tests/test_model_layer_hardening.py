"""Model-layer regressions. All examples and model records are TEST_ONLY fixtures."""

import json
import math
import random
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.modules.inference.gateway import AzaeronInferenceGateway, AzaeronInferenceJob
from app.modules.inference.registry import AzaeronModelRegistry, InferenceUnavailable
from app.modules.model_platform.contracts import DetectionOutput
from app.modules.model_platform.datasets import read_native_dataset
from app.modules.model_platform.detector_metrics import (
    detector_report,
    operating_thresholds,
)
from app.modules.model_platform.evaluate import classification_metrics
from app.modules.model_platform.policy import DatasetManifest, PolicyError, canonical
from tests.test_candidate_program import dataset_fixture, save_dataset
from tests.test_private_inference import approved_model, private_dns


def test_ood_abstention_applies_to_every_decision_metric():
    result = detector_report(
        [[0.01, 0.98, 0.01], [0.01, 0.98, 0.01]],
        [0, 1],
        ["unknown", "validated"],
        {"validated"},
        operating_thresholds([0.1, 0.9], [0, 1]),
    )
    assert result["coverage"] == 0.5
    assert result["human_fpr"] == 0
    assert result["human_fpr_upper95"] > 0.5
    assert result["selective_accuracy"] == 1
    assert result["recall_by_class"]["1"] == result["multiclass"]["1"]["recall"] == 1
    assert result["operating_points"]["0.001"]["test_fpr"] == 0
    assert not result["operating_points"]["0.001"]["fpr_bound_meets_target"]
    abstained = detector_report(
        [[0.01, 0.98, 0.01]],
        [1],
        ["unknown"],
        set(),
        operating_thresholds([0.1, 0.9], [0, 1]),
    )
    assert abstained["selective_accuracy"] is None
    assert abstained["recall_by_class"]["1"] == 0
    assert abstained["multiclass"]["1"]["recall"] == 0


def test_threshold_optimization_preserves_ties_and_reference_results():
    rng = random.Random(764)
    for _ in range(20):
        scores = [rng.randrange(11) / 10 for _ in range(100)]
        labels = [i % 3 for i in range(100)]
        humans = [p for p, y in zip(scores, labels, strict=True) if y == 0]
        candidates = sorted({0.0, *scores, math.nextafter(1.0, math.inf)})
        reference = {
            str(rate): min(
                t
                for t in candidates
                if sum(p >= t for p in humans) / len(humans) <= rate
            )
            for rate in [0.001, 0.01, 0.05]
        }
        assert operating_thresholds(scores, labels) == reference


@pytest.mark.parametrize(
    "probabilities,labels,threshold,mask",
    [
        ([[0.5, 0.5]], [2], 0.9, None),
        ([[0.5, 0.5]], [True], 0.9, None),
        ([[0.5, 0.5], [1.0]], [0, 0], 0.9, None),
        ([[0.5, 0.5]], [0], float("nan"), None),
        ([[0.5, 0.5]], [0], 0.9, [1]),
        ([[0.5, 0.5]], [0], 0.9, []),
    ],
)
def test_invalid_metric_inputs_fail_closed(probabilities, labels, threshold, mask):
    with pytest.raises(PolicyError):
        classification_metrics(probabilities, labels, threshold, accepted_mask=mask)


def detection_fixture():
    return dict(
        label="UNCERTAIN",
        probabilities=None,
        abstained=True,
        checkpoint_sha256="a" * 64,
        calibration_sha256="b" * 64,
        limitations=["TEST_ONLY"],
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"probabilities": [0.99, 0.005, 0.005]},
        {"label": "HUMAN"},
        {"abstained": False},
        {"abstained": False, "label": "AI", "probabilities": [0.99, 0.005, 0.005]},
        {"label": "INDETERMINATE"},
    ],
)
def test_detection_contract_withholds_probabilities(mutation):
    assert DetectionOutput(**detection_fixture()).probabilities is None
    with pytest.raises(ValidationError):
        DetectionOutput(**{**detection_fixture(), **mutation})


async def test_gateway_rejects_probability_leak_and_checkpoint_substitution():
    model = approved_model(tasks=["classify"])
    model = approved_model(
        tasks=["classify"], artifacts={**model.artifacts, "calibration.json": "b" * 64}
    )
    result = {
        **detection_fixture(),
        "checkpoint_sha256": model.lineage.checkpoint_sha256,
    }
    payload = {
        "model": model.model_id,
        "revision": model.revision,
        "result": result,
        "usage": {"prompt_tokens": 3, "completion_tokens": 0},
    }
    private = AzaeronInferenceGateway(
        AzaeronModelRegistry(models=[model], routes={"classify": model.model_id}),
        "https://inference-runtime",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
        resolve=private_dns,
    )
    job = AzaeronInferenceJob(
        operation_id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        task="classify",
        text="fixture",
    )
    assert json.loads((await private.run(job)).output)["probabilities"] is None
    result["probabilities"] = [0.99, 0.005, 0.005]
    with pytest.raises(InferenceUnavailable, match="invalid_output"):
        await private.run(job)
    result["probabilities"] = None
    result["checkpoint_sha256"] = "f" * 64
    with pytest.raises(InferenceUnavailable, match="invalid_output"):
        await private.run(job)


@pytest.mark.parametrize("smoke", [False, True])
def test_legacy_production_data_cannot_bypass_five_split_rights_gate(tmp_path, smoke):
    manifest = DatasetManifest(
        dataset_id="TEST_ONLY_attack",
        purpose="PRODUCTION",
        source="fixture",
        license="fixture",
        allowed_tasks=["detector"],
        splits={},
        reviews={},
    )
    path = tmp_path / "dataset.json"
    path.write_bytes(canonical(manifest.model_dump()))
    with pytest.raises(PolicyError, match="five_split_dataset_v2"):
        read_native_dataset(path, "detector", smoke=smoke)


def test_native_v2_uses_five_splits_and_bound_rights_review(tmp_path):
    manifest = dataset_fixture(tmp_path)
    path = save_dataset(tmp_path, manifest)
    validated, rows = read_native_dataset(path, "detector", smoke=True)
    assert validated.schema_version == 2
    assert set(rows) == {"train", "validation", "calibration", "test", "ood"}
    assert all(row["target"] == "ai" for values in rows.values() for row in values)
    metadata = json.loads(path.read_bytes())
    metadata["license"] = "changed_after_review"
    path.write_bytes(canonical(metadata))
    with pytest.raises(PolicyError, match="review_binding"):
        read_native_dataset(path, "detector", smoke=True)
