"""User-owned, explicitly approved style samples; no source prose in profiles."""

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, func

from app.modules.agent.models import VoiceProfile
from app.modules.agent.receipts import sha
from app.modules.agent.service import authorize
from app.modules.agent.schemas import VoiceCreate
from app.modules.audit.models import AuditAction
from app.modules.audit.service import AuditService
from app.modules.billing.usage import UsageService
from app.modules.documents.target import AnalysisTarget

POLICY = "voice-style-statistics-1"


def style_features(text):
    words = re.findall(r"\b\w+(?:['’]\w+)?\b", text)
    if len(words) < 100:
        raise HTTPException(422, "Voice samples need at least 100 words in total")
    sentences = max(1, len(re.findall(r"[.!?](?:\s|$)", text)))
    return {
        "mean_sentence_words": min(100.0, len(words) / sentences),
        "mean_word_characters": min(30.0, sum(map(len, words)) / len(words)),
        "first_person_rate": sum(
            word.lower() in {"i", "we", "my", "our", "us"} for word in words
        )
        / len(words),
        "contraction_rate": sum("'" in word or "’" in word for word in words)
        / len(words),
        "paragraph_words": min(
            1000.0,
            len(words)
            / max(1, len([p for p in re.split(r"\n\s*\n", text) if p.strip()])),
        ),
    }


async def create_profile(db, org, actor, data: VoiceCreate):
    await authorize(db, org, actor)
    await UsageService(db).lock(org)
    count = await db.scalar(
        select(func.count())
        .select_from(VoiceProfile)
        .where(VoiceProfile.organization_id == org, VoiceProfile.user_id == actor)
    )
    if (count or 0) >= 10:
        raise HTTPException(402, "Voice profile limit reached")
    versions = set()
    texts, samples = [], []
    for reference in data.samples:
        target = await AnalysisTarget.resolve(
            db,
            org,
            str(reference.document_id),
            str(reference.document_version_id),
            lock=True,
        )
        if target.document.owner_id != actor or target.document.erasure_pending:
            raise HTTPException(403, "Voice samples must belong to you")
        if str(target.version.id) in versions:
            raise HTTPException(422, "Use distinct sample versions")
        versions.add(str(target.version.id))
        source = (await target.processed(db)).cleaned_text or ""
        if len(source) > 60_000:
            raise HTTPException(422, "Voice sample is too long")
        texts.append(source)
        samples.append(
            {
                **reference.model_dump(mode="json"),
                "input_sha256": sha(source),
                "approved_by": actor,
            }
        )
    profile = VoiceProfile(
        organization_id=org,
        user_id=actor,
        name=data.name,
        samples=samples,
        style=style_features("\n\n".join(texts)),
        policy_revision=POLICY,
    )
    db.add(profile)
    await db.flush()
    await AuditService(db).log(
        AuditAction.SETTINGS_CHANGED,
        "voice_profile",
        profile.id,
        details={"sample_count": len(samples), "policy": POLICY},
        user_id=actor,
        organization_id=org,
    )
    return profile


async def resolve_profile(db, org, actor, identifier):
    profile = await db.scalar(
        select(VoiceProfile).where(
            VoiceProfile.id == str(identifier),
            VoiceProfile.organization_id == org,
            VoiceProfile.user_id == actor,
        )
    )
    if not profile:
        raise HTTPException(404, "Voice profile not found")
    for sample in profile.samples:
        target = await AnalysisTarget.resolve(
            db, org, sample["document_id"], sample["document_version_id"]
        )
        if target.document.owner_id != actor or target.document.erasure_pending:
            raise HTTPException(403, "Voice sample access changed")
        if (
            sha((await target.processed(db)).cleaned_text or "")
            != sample["input_sha256"]
        ):
            raise HTTPException(409, "Voice sample integrity check failed")
    return profile
