"""Public capability discovery reports implemented scope, never readiness."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.core.config import settings
from app.modules.aegiswrite.engine import EDITORIAL_ENGINE_VERSION

router = APIRouter(tags=["Capabilities"])


class Capability(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    state: Literal["AVAILABLE", "LIMITED", "UNAVAILABLE"]
    description: str


class CapabilitiesResponse(BaseModel):
    api_version: Literal["v1"] = "v1"
    zero_external_ai_api: bool
    production_certified: Literal[False] = False
    capabilities: list[Capability]


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        zero_external_ai_api=settings.ZERO_EXTERNAL_AI_API,
        capabilities=[
            Capability(
                id="documents",
                state="AVAILABLE",
                description="Private uploads, immutable input versions and version-scoped analysis.",
            ),
            Capability(
                id="refine",
                state="LIMITED",
                description=f"Deterministic editorial suggestions with protected spans ({EDITORIAL_ENGINE_VERSION}); no generative model or semantic guarantee.",
            ),
            Capability(
                id="detection",
                state="LIMITED",
                description="Observable writing signals with abstention; no calibrated production detector.",
            ),
            Capability(
                id="provenance",
                state="LIMITED",
                description="Version lineage and content hashes; no independently signed authorship proof.",
            ),
            Capability(
                id="private_inference",
                state="UNAVAILABLE",
                description="An approved writing model, measured quality and private inference deployment are required.",
            ),
            Capability(
                id="voice",
                state="UNAVAILABLE",
                description="The complete user-controlled voice-profile workflow is not implemented.",
            ),
            Capability(
                id="api_keys",
                state="AVAILABLE",
                description="Tenant-scoped keys with display-once secrets, expiry, rotation, revocation, rate limits and durable quota accounting.",
            ),
            Capability(
                id="privacy_erasure",
                state="LIMITED",
                description="Authorized document, account and organization erasure is implemented; complete backup and object-store recovery is not certified.",
            ),
        ],
    )
