from app.modules.uploads.service import UploadService
import uuid


class NoopStorage:
    pass


def test_upload_rejects_oversize_and_invalid_magic_bytes():
    service = UploadService(NoopStorage())
    valid, _ = service.validate_file("paper.pdf", "application/pdf", 101 * 1024 * 1024)
    assert not valid
    valid, _ = service.validate_uploaded_content(
        "uploads/a/b/id.pdf", "application/pdf", b"not a pdf"
    )
    assert not valid
    valid, _ = service.validate_file("paper.txt", "text/plain", -1)
    assert not valid


def test_upload_rejects_scripted_html():
    service = UploadService(NoopStorage())
    valid, _ = service.validate_uploaded_content(
        "uploads/a/b/id.html", "text/html", b"<script>alert(1)</script>"
    )
    assert not valid


def test_upload_key_binding_rejects_path_like_and_cross_namespace_keys():
    upload_id = str(uuid.uuid4())
    safe = f"uploads/org-a/user-a/{upload_id}.txt"
    assert UploadService.expected_storage_key(safe, upload_id, "org-a", "user-a")
    assert not UploadService.expected_storage_key(
        f"uploads/org-a/user-a/{upload_id}.txt/../../org-b/secret.txt",
        upload_id,
        "org-a",
        "user-a",
    )
    assert not UploadService.expected_storage_key(
        f"uploads/org-b/user-b/{upload_id}.txt", upload_id, "org-a", "user-a"
    )


async def test_accepted_snapshot_is_independent_of_mutable_staging():
    import hashlib
    import pytest
    from tests.test_editor_revisions import MemoryStorage

    storage = MemoryStorage()
    service = UploadService(storage)
    key = f"uploads/org/user/{uuid.uuid4()}.txt"
    content = b"Original accepted text."
    digest = hashlib.sha256(content).hexdigest()
    frozen = await service.freeze_upload(key, content, digest, "text/plain")
    storage.objects[key] = b"Changed through a still-valid staging URL"
    assert frozen.startswith("versions/")
    assert storage.objects[frozen] == content
    with pytest.raises(ValueError, match="fingerprint"):
        await service.freeze_upload(key, b"different", digest, "text/plain")
    assert storage.objects[frozen] == content
