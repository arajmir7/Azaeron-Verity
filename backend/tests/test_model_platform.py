"""Owned-model gates and public API security; no claims about model quality."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.model_platform.policy import (
    DatasetManifest,
    FileRef,
    Lineage,
    PolicyError,
    Review,
    digest,
)
from app.modules.model_platform.evaluate import (
    classification_metrics,
    retrieval_metrics,
)
from app.modules.inference.registry import AzaeronModelRegistry, InferenceUnavailable
from tests.test_private_inference import approved_model
from tests.test_api_keys import owner, issue


def test_renaming_baseline_or_smoke_checkpoint_cannot_approve():
    with pytest.raises(ValidationError, match="lineage"):
        approved_model(model_id="azaeron-verity-writer", lineage=None)
    model = approved_model()
    with pytest.raises(ValidationError, match="production"):
        approved_model(lineage={**model.lineage.model_dump(), "purpose": "TEST_ONLY"})
    with pytest.raises(ValidationError, match="Unchanged"):
        Lineage.model_validate(
            {
                **model.lineage.model_dump(),
                "initialization_sha256": model.lineage.checkpoint_sha256,
            }
        )
    with pytest.raises(ValidationError, match="Derivative"):
        Lineage.model_validate(
            {**model.lineage.model_dump(), "classification": "AZAERON_DERIVATIVE"}
        )
    with pytest.raises(ValidationError, match="specialized"):
        approved_model(tasks=["refine", "verify"])
    with pytest.raises(ValidationError):
        approved_model(release={**model.release.model_dump(), "gates": {}})
    with pytest.raises(InferenceUnavailable, match="no_approved"):
        AzaeronModelRegistry().select("chat")


def test_hash_and_symlink_checks(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text("original")
    ref = FileRef(path=path.name, sha256=digest(path))
    assert ref.verify(tmp_path) == path
    path.write_text("tampered")
    with pytest.raises(PolicyError, match="hash"):
        ref.verify(tmp_path)
    (tmp_path / "link").symlink_to(path)
    with pytest.raises(PolicyError, match="symlink"):
        FileRef(path="link", sha256=digest(path)).verify(tmp_path)
    with pytest.raises(PolicyError, match="unsafe"):
        FileRef(path="../data", sha256="0" * 64).verify(tmp_path)


def test_unknown_rights_and_test_dataset_cannot_train(tmp_path):
    with pytest.raises(ValidationError):
        Review.model_validate({"commercial_training_rights": False})
    manifest = DatasetManifest(
        dataset_id="fixture",
        purpose="TEST_ONLY",
        source="fixture",
        license="fixture",
        allowed_tasks=["writer"],
        splits={},
        reviews={},
    )
    with pytest.raises(PolicyError, match="test_data"):
        manifest.load_rows(tmp_path, "writer")


def test_metrics_include_uncertainty_and_retrieval_order():
    result = classification_metrics(
        [[0.99, 0.005, 0.005], [0.99, 0.005, 0.005]], [0, 0]
    )
    assert result["human_fpr"] == 0 and result["human_fpr_upper95"] > 0.5
    with pytest.raises(PolicyError):
        classification_metrics([[float("nan"), 0, 1]], [0])
    values = retrieval_metrics([["b", "a"], ["x", "y"]], [["a"], ["x"]], 1)
    assert values == {"recall_at_k": 0.5, "mrr": 0.75, "ndcg_at_k": 0.5}


async def test_public_routes_require_auth_and_fail_closed(client):
    routes = ["/ai/chat", "/ai/chat/stream", "/humanize", "/detect"]
    for route in routes:
        response = await client.post(
            "/api/v1" + route, json={"operation_id": str(uuid4()), "text": "A sample."}
        )
        assert response.status_code == 401
    auth, _ = await owner(client)
    for route in routes:
        response = await client.post(
            "/api/v1" + route,
            headers=auth,
            json={"operation_id": str(uuid4()), "text": "A sample."},
        )
        assert response.status_code == 503, response.text
    models = await client.get("/api/v1/models", headers=auth)
    assert models.json()["models"] == []


async def test_public_api_scopes_and_document_absence(client):
    auth, _ = await owner(client)
    key = await issue(client, auth, scopes=["text:analyze"])
    headers = {"X-API-Key": key["secret"]}
    response = await client.post(
        "/api/v1/ai/chat",
        headers=headers,
        json={"operation_id": str(uuid4()), "text": "A sample."},
    )
    assert response.status_code == 403
    chat_key = await issue(client, auth, scopes=["ai:chat"])
    response = await client.post(
        "/api/v1/ai/chat",
        headers={"X-API-Key": chat_key["secret"]},
        json={"operation_id": str(uuid4()), "text": "A sample."},
    )
    assert response.status_code == 503, response.text
    for task in ["ask", "summarize"]:
        response = await client.post(
            f"/api/v1/documents/{uuid4()}/{task}",
            headers=auth,
            json={
                "operation_id": str(uuid4()),
                "document_version_id": str(uuid4()),
                "text": "What does this document say?",
            },
        )
        assert response.status_code == 404, response.text


async def test_verified_chat_stream_and_replay_use_two_distinct_models(
    client, monkeypatch
):
    import httpx
    from app.modules.inference.gateway import AzaeronInferenceGateway
    from tests.test_private_inference import private_dns
    from tests.test_agent import stream_frames

    writer = approved_model(tasks=["chat"])
    verifier = approved_model(
        model_id="fixture-verifier", revision="c" * 40, tasks=["verify"]
    )
    catalog = AzaeronModelRegistry(
        models=[writer, verifier],
        routes={"chat": writer.model_id, "verify": verifier.model_id},
    )
    calls = []

    async def transport(request):
        data = json.loads(request.content)
        calls.append(data["model"])
        if data["model"] == writer.model_id and data["stream"]:
            return httpx.Response(
                200,
                text="".join(
                    "data: "
                    + (frame if isinstance(frame, str) else json.dumps(frame))
                    + "\n\n"
                    for frame in stream_frames()
                ),
            )
        output = (
            "Test-only output."
            if data["model"] == writer.model_id
            else json.dumps(
                {
                    "equivalent": True,
                    "contradiction": False,
                    "unsupported_additions": False,
                    "uncertain": False,
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "model": data["model"],
                "choices": [{"finish_reason": "stop", "message": {"content": output}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    private = AzaeronInferenceGateway(
        catalog,
        "https://inference-runtime",
        transport=httpx.MockTransport(transport),
        resolve=private_dns,
    )
    monkeypatch.setattr("app.api.v1.model_platform.gateway", lambda: private)
    auth, _ = await owner(client)
    for route in ["chat", "chat/stream"]:
        payload = {"operation_id": str(uuid4()), "text": "Test-only output."}
        response = await client.post("/api/v1/ai/" + route, headers=auth, json=payload)
        assert response.status_code == 200, response.text
        if route.endswith("stream"):
            assert (
                "event: delta" in response.text
                and '"provisional": true' in response.text
            )
            assert (
                "event: completed" in response.text
                and '"accepted": true' in response.text
            )
        else:
            assert response.json()["accepted"] is True
        count = len(calls)
        replay = await client.post("/api/v1/ai/" + route, headers=auth, json=payload)
        assert replay.status_code == 200 and len(calls) == count
    assert calls == [writer.model_id, verifier.model_id] * 2


async def test_specialists_reject_wrong_dimensions_identity_and_nan():
    import hashlib
    import httpx
    from app.modules.inference.gateway import (
        AzaeronInferenceGateway,
        AzaeronInferenceJob,
    )
    from tests.test_private_inference import private_dns

    model = approved_model(tasks=["embed"])
    catalog = AzaeronModelRegistry(models=[model], routes={"embed": model.model_id})
    data = {
        "model": model.model_id,
        "revision": model.revision,
        "usage": {"prompt_tokens": 3, "completion_tokens": 0},
        "result": {"embedding": [1.0] + [0.0] * 7},
    }
    private = AzaeronInferenceGateway(
        catalog,
        "https://inference-runtime",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)),
        resolve=private_dns,
    )
    job = AzaeronInferenceJob(
        operation_id=uuid4(),
        organization_id=uuid4(),
        user_id=uuid4(),
        task="embed",
        text="fixture",
    )
    assert json.loads((await private.run(job)).output)["embedding"][0] == 1
    data["revision"] = "bad"
    with pytest.raises(InferenceUnavailable, match="invalid_output"):
        await private.run(job)
    data["revision"] = model.revision
    data["result"] = {"embedding": [1.0] * 8}
    with pytest.raises(InferenceUnavailable, match="invalid_output"):
        await private.run(job)


def test_dataset_split_leakage_and_review_subject_binding(tmp_path):
    from app.modules.model_platform.policy import canonical

    splits, reviews = {}, {}
    for name in ["train", "calibration", "evaluation"]:
        path = tmp_path / (name + ".jsonl")
        path.write_bytes(
            canonical(
                {
                    "id": name,
                    "group": name,
                    "input": "Same paragraph",
                    "target": "human",
                }
            )
        )
        splits[name] = {"path": path.name, "sha256": digest(path)}
        review = tmp_path / (name + "-review.json")
        review.write_bytes(
            canonical(
                {
                    "subject_sha256": digest(path),
                    "reviewer": "TEST ONLY",
                    "reviewed_at": "2026-09-30",
                    "source": "fixture",
                    "license": "fixture",
                    "commercial_training_rights": True,
                    "provenance": "PASS",
                    "pii_review": "PASS",
                    "copyright_review": "PASS",
                    "allowed_tasks": ["detector"],
                    "evidence_reference": "TEST ONLY",
                }
            )
        )
        reviews[name] = {"path": review.name, "sha256": digest(review)}
    manifest = DatasetManifest(
        dataset_id="fixture",
        purpose="TEST_ONLY",
        source="fixture",
        license="fixture",
        allowed_tasks=["detector"],
        splits=splits,
        reviews=reviews,
    )
    with pytest.raises(PolicyError, match="split_leakage"):
        manifest.load_rows(tmp_path, "detector", smoke=True)
