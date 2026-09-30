"""AZAERON API v1 router assembly."""

from fastapi import APIRouter
from app.api.v1 import (
    ai,
    auth,
    organizations,
    documents,
    jobs,
    detection,
    evidence,
    reports,
    assignments,
    aegiswrite,
    similarity,
    citations,
    authorship,
    provenance,
)
from app.api.v1 import (
    capabilities,
    models,
    text,
    api_keys,
    identity,
    privacy,
    usage,
    telemetry,
    model_platform,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(model_platform.router)
api_router.include_router(ai.router)
api_router.include_router(usage.router)
api_router.include_router(telemetry.router)
api_router.include_router(privacy.router)
api_router.include_router(identity.router)
api_router.include_router(api_keys.router)
api_router.include_router(capabilities.router)
api_router.include_router(models.router)
api_router.include_router(text.router)
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(detection.router)
api_router.include_router(evidence.router)
api_router.include_router(reports.router)
api_router.include_router(assignments.router)
api_router.include_router(aegiswrite.router)
api_router.include_router(similarity.router)
api_router.include_router(citations.router)
api_router.include_router(authorship.router)
api_router.include_router(provenance.router)
