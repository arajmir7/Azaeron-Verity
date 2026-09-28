import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.verification.service import verify_text, deterministic_reasons


def identity():
    return dict(operation_id=uuid4(), organization_id=uuid4(), user_id=uuid4())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original,candidate",
    [
        ("This does not establish safety.", "This does establish safety."),
        ("The treatment may help.", "The treatment will help."),
        ("The result was approximately 10%.", "The result was 10%."),
        ("The cost is $10 million.", "The cost is $10 billion."),
        ("Smith et al. [7] reported a result.", "Smith et al. reported a result."),
        ("ACME works in London.", "ACME works in Paris."),
        ("The iPhone is a product.", "The Android is a product."),
        (
            "Contact a@example.com at https://example.com.",
            "Contact b@example.com at https://example.com.",
        ),
        ("It states “do not change this”.", "It states “change this”."),
        ("Use `value != 1`.", "Use `value == 1`."),
        ("The equation is $x + y$.", "The equation is $x - y$."),
        ("A finding.[^7]", "A finding."),
    ],
)
async def test_factual_drift(original, candidate):
    result = await verify_text(original, candidate, **identity())
    assert result.outcome == "REJECTED" and not result.semantic_checked
    assert not result.deterministic_passed


@pytest.mark.asyncio
async def test_missing_model_never_produces_semantic_pass():
    result = await verify_text(
        "The report is clear.", "The report is concise.", **identity()
    )
    assert result.outcome == "UNAVAILABLE" and result.deterministic_passed
    identical = await verify_text("Unchanged text.", "Unchanged text.", **identity())
    assert identical.outcome == "VERIFIED" and identical.reasons == ["identical_text"]


def test_explicit_locked_spans_and_invalid_range():
    assert "locked_text_changed" in deterministic_reasons(
        "keep this text", "edit this text", [(0, 4)]
    )
    with pytest.raises(ValueError):
        deterministic_reasons("text", "text", [(0, 999)])


class VerifierFixture:
    """Test-only independent adapter; never registered by production code."""

    def __init__(self, assessment, revision="b" * 40):
        self.assessment = assessment
        self.router = SimpleNamespace(
            route=lambda task: SimpleNamespace(
                model_id="verifier-fixture", revision=revision
            )
        )
        self.calls = 0

    async def run(self, job):
        self.calls += 1
        assert job.task == "verify"
        assert set(json.loads(job.text)) == {"original", "candidate"}
        return SimpleNamespace(output=json.dumps(self.assessment))


@pytest.mark.asyncio
async def test_independent_verifier_outcomes_and_same_model_rejected():
    body = dict(
        equivalent=True,
        contradiction=False,
        unsupported_additions=False,
        uncertain=False,
    )
    fixture = VerifierFixture(body)
    result = await verify_text(
        "The report is clear.",
        "The report is concise.",
        **identity(),
        gateway=fixture,
        writing_model_revision="b" * 40
    )
    assert result.outcome == "UNAVAILABLE" and fixture.calls == 0
    for changes, expected in [
        ({}, "VERIFIED"),
        ({"uncertain": True}, "VERIFIED_WITH_WARNINGS"),
        ({"contradiction": True}, "REJECTED"),
        ({"unsupported_additions": True}, "REJECTED"),
        ({"equivalent": "yes"}, "UNAVAILABLE"),
    ]:
        fixture = VerifierFixture({**body, **changes})
        result = await verify_text(
            "The report is clear.",
            "The report is concise.",
            **identity(),
            gateway=fixture,
            writing_model_revision="a" * 40
        )
        assert result.outcome == expected


@pytest.mark.asyncio
async def test_drift_rejected_before_model_call():
    fixture = VerifierFixture({})
    result = await verify_text(
        "It does not work.", "It does work.", **identity(), gateway=fixture
    )
    assert result.outcome == "REJECTED" and fixture.calls == 0


@pytest.mark.asyncio
async def test_text_api_auth_contract_and_unavailable_generation(client):
    import secrets

    token = secrets.token_urlsafe(20) + "Aa1!"
    operation = str(uuid4())
    payload = {
        "operation_id": operation,
        "original": "It may help.",
        "candidate": "It will help.",
    }
    assert (await client.post("/api/v1/text/verify", json=payload)).status_code == 401
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "verify-api@example.com", "password": token},
    )
    assert registered.status_code == 201
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "verify-api@example.com", "password": token},
    )
    auth = {"Authorization": "Bearer " + login.cookies["access_token"]}
    organization = await client.post(
        "/api/v1/organizations", json={"name": "Verification fixture"}, headers=auth
    )
    assert organization.status_code == 201
    selected = await client.post(
        "/api/v1/organizations/" + organization.json()["id"] + "/select", headers=auth
    )
    auth = {"Authorization": "Bearer " + selected.cookies["access_token"]}
    response = await client.post("/api/v1/text/verify", json=payload, headers=auth)
    assert response.status_code == 200 and response.json()["outcome"] == "REJECTED"
    response = await client.post(
        "/api/v1/text/refine",
        json={"operation_id": operation, "text": "Keep my document intact."},
        headers=auth,
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "blocked_by_external_infrastructure"
    response = await client.post(
        "/api/v1/text/verify",
        json={**payload, "organization_id": str(uuid4())},
        headers=auth,
    )
    assert response.status_code == 422
    schema = (await client.get("/api/openapi.json")).json()
    assert schema["openapi"] == "3.1.0"
    assert "/api/v1/text/verify" in schema["paths"]
