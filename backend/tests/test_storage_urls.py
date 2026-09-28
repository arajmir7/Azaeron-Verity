from datetime import timedelta

from app.api.v1.documents import get_storage_client
from app.core.config import settings


def test_presigned_storage_urls_use_browser_endpoint_without_region_lookup(monkeypatch):
    monkeypatch.setattr(settings, "MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setattr(settings, "MINIO_PUBLIC_ENDPOINT", "localhost:9000")
    monkeypatch.setattr(settings, "MINIO_REGION", "us-east-1")
    monkeypatch.setattr(settings, "MINIO_SECURE", False)

    client = get_storage_client(public=True)
    url = client.presigned_put_object(
        settings.MINIO_BUCKET,
        "uploads/org/user/upload.txt",
        expires=timedelta(minutes=7),
    )

    assert url.startswith("http://localhost:9000/azaeron-documents/")
    assert "X-Amz-SignedHeaders=host" in url
