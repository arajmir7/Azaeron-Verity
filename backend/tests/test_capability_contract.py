from app.main import app


async def test_discovery_reports_available_keys_limited_erasure_and_unavailable_ai(
    client,
):
    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["zero_external_ai_api"] is True
    assert data["production_certified"] is False
    states = {item["id"]: item["state"] for item in data["capabilities"]}
    assert states["private_inference"] == "UNAVAILABLE"
    assert states["privacy_erasure"] == "LIMITED"
    assert states["api_keys"] == "AVAILABLE"
    assert states["detection"] == states["refine"] == "LIMITED"


def test_published_openapi_is_31_and_includes_protected_span_contract():
    schema = app.openapi()
    assert schema["openapi"].startswith("3.1.")
    assert "/api/v1/capabilities" in schema["paths"]
    assert (
        schema["components"]["schemas"]["AegisRefineRequest"]["additionalProperties"]
        is False
    )
    assert (
        "locked_spans"
        in schema["components"]["schemas"]["AegisRefineRequest"]["properties"]
    )


def test_public_openapi_declares_key_scopes_without_exposing_internal_inference():
    schema = app.openapi()
    assert "AzaeronAPIKey" in schema["components"]["securitySchemes"]
    for path, method, scopes in (
        ("/api/v1/documents", "get", ["documents:read"]),
        ("/api/v1/text/analyze", "post", ["text:analyze"]),
        ("/api/v1/text/refine", "post", ["text:refine"]),
        ("/api/v1/text/verify", "post", ["text:verify"]),
        ("/api/v1/usage", "get", ["usage:read"]),
    ):
        operation = schema["paths"][path][method]
        assert operation["x-api-key-scopes"] == scopes
        assert {"AzaeronAPIKey": []} in operation["security"]
    assert all("/internal/" not in path for path in schema["paths"])
