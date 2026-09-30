"""Public model discovery exposes capabilities, never engine credentials/URLs."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.inference.registry import InferenceUnavailable
from app.modules.inference.service import registry

router = APIRouter(tags=["Models"])


class PublicModel(BaseModel):
    id: str
    revision: str
    tasks: list[str]
    languages: list[str]
    context_limit: int
    license: str
    classification: str
    family: str


class ModelList(BaseModel):
    models: list[PublicModel]
    status: str


@router.get("/models", response_model=ModelList)
async def models(user: User = Depends(get_current_user)) -> ModelList:
    try:
        approved = [
            m
            for m in registry().models
            if m.status == "APPROVED" and m.lineage is not None
        ]
    except InferenceUnavailable:
        approved = []
    return ModelList(
        models=[
            PublicModel(
                id=m.model_id,
                revision=m.revision,
                tasks=list(m.tasks),
                languages=m.languages,
                context_limit=m.context_limit,
                license=m.license,
                classification=m.lineage.classification if m.lineage else "UNAVAILABLE",
                family=(
                    "Azaeron-Verity-" + m.lineage.family.title()
                    if m.lineage
                    else "UNAVAILABLE"
                ),
            )
            for m in approved
        ],
        status=(
            "APPROVED_MODELS_REGISTERED"
            if approved
            else "BLOCKED_BY_EXTERNAL_INFRASTRUCTURE"
        ),
    )
