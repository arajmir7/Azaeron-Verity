"""Owned voice profiles and licensed offline corpus safeguards."""

import hashlib
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError
import pytest

from app.modules.agent.voice import create_profile, resolve_profile
from app.modules.agent.schemas import VoiceCreate, Attachment
from app.modules.processing.service import DocumentProcessingService
from app.modules.similarity.corpus import coverage
from app.modules.similarity.public_index import PublicSource, build_index, retrieve
from tests.test_editor_revisions import seed_editor


async def test_voice_requires_owned_approved_samples_and_contains_statistics_only(
    db_session, monkeypatch
):
    org, user, doc, version, storage, _ = await seed_editor(db_session, monkeypatch)
    sample = (
        "We present careful evidence and keep the original source available for review. "
        * 12
    )
    from app.modules.documents.editor import EditorRevisionService

    version = await EditorRevisionService(db_session, storage).save(
        doc.id, org.id, user.id, version.id, str(uuid4()), sample, []
    )
    data = VoiceCreate(
        name="My academic voice",
        samples=[
            Attachment(document_id=UUID(doc.id), document_version_id=UUID(version.id))
        ],
        approved=True,
    )
    profile = await create_profile(db_session, org.id, user.id, data)
    assert all(isinstance(value, float) for value in profile.style.values())
    assert sample not in json.dumps(profile.samples) and len(profile.style) == 5
    assert (
        await resolve_profile(db_session, org.id, user.id, profile.id)
    ).id == profile.id
    with pytest.raises(HTTPException) as denied:
        await resolve_profile(db_session, str(uuid4()), user.id, profile.id)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException):
        await resolve_profile(db_session, org.id, str(uuid4()), profile.id)
    with pytest.raises(ValidationError):
        VoiceCreate(name="Unapproved", samples=data.samples, approved=False)


def source(**changes):
    text = "An original test fixture describing a public research source with specific words and attribution."
    result = {
        "corpus": "OPEN_SCHOLARLY",
        "url": "https://example.org/paper#fragment",
        "title": "Authored fixture",
        "text": text,
        "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "license": "Test fixture owned by this repository",
        "permission_reference": "test-fixture",
        "rights_review_reference": "test-fixture",
        "captured_at": "2026-09-29T00:00:00Z",
        "index_allowed": True,
        "display_passages_allowed": True,
    }
    return {**result, **changes}


def test_offline_corpus_index_rights_canonicalization_and_retrieval(tmp_path):
    bundle = tmp_path / "licensed.jsonl"
    bundle.write_text(
        json.dumps(source())
        + "\n"
        + json.dumps(source(url="https://example.org/mirror"))
        + "\n"
    )
    path = tmp_path / "index.sqlite"
    report = build_index(bundle, path)
    assert report["sources"] == 1 and report["production_approved"] is False
    results = retrieve(
        path, "a public research source with specific words and attribution"
    )
    assert len(results) == 1 and "#" not in results[0]["url"]
    assert results[0]["matched_shingles"] > 0
    assert not retrieve(path, "different wording with no shared passage at all")
    with pytest.raises(ValueError):
        build_index(bundle, path)
    for changes in (
        {"index_allowed": False},
        {"display_passages_allowed": False},
        {"permission_reference": ""},
        {"content_sha256": "0" * 64},
        {"corpus": "PRIVATE_WORKSPACE"},
        {"paywalled": True},
        {"url": "file:///etc/passwd"},
    ):
        with pytest.raises(ValidationError):
            PublicSource.model_validate(source(**changes))
    assert [item["state"] for item in coverage()] == [
        "AVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
    ]
