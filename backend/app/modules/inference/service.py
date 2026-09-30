"""Deployment configuration: disabled means unavailable, never simulated output."""

import ssl

from app.core.config import settings
from app.modules.inference.gateway import AzaeronInferenceGateway
from app.modules.inference.registry import AzaeronModelRegistry, InferenceUnavailable


def registry() -> AzaeronModelRegistry:
    return AzaeronModelRegistry.load(settings.MODEL_REGISTRY_PATH)


def gateway() -> AzaeronInferenceGateway:
    if not settings.INFERENCE_ENABLED:
        raise InferenceUnavailable("blocked_by_external_infrastructure")
    catalog = registry()
    writer = catalog.select("refine")
    verifier = catalog.select("verify")
    if writer.model_id == verifier.model_id or writer.revision == verifier.revision:
        raise InferenceUnavailable("independent_verifier_required")
    if settings.INFERENCE_ENDPOINT == settings.INFERENCE_VERIFY_ENDPOINT:
        raise InferenceUnavailable("independent_runtime_routes_required")
    ca, cert, key = (
        settings.INFERENCE_CA_FILE,
        settings.INFERENCE_CERT_FILE,
        settings.INFERENCE_KEY_FILE,
    )
    if not ca or not cert or not key:
        raise InferenceUnavailable("runtime_mtls_required")
    try:
        tls = ssl.create_default_context(cafile=ca)
        tls.load_cert_chain(cert, key)
    except (OSError, ssl.SSLError):
        raise InferenceUnavailable("runtime_mtls_invalid") from None
    return AzaeronInferenceGateway(
        catalog,
        {
            **settings.INFERENCE_MODEL_ENDPOINTS,
            writer.model_id: settings.INFERENCE_ENDPOINT,
            verifier.model_id: settings.INFERENCE_VERIFY_ENDPOINT,
        },
        tls=tls,
    )


def validate_inference_startup() -> None:
    if settings.INFERENCE_ENABLED:
        gateway()  # Missing approval/configuration prevents application startup.
