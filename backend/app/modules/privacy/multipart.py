"""Pinned MinIO 7.2 adapter for standard S3 multipart listing and abort.

MinIO's public Python API does not expose these operations. Keep SDK-private
calls here and exercise them against actual MinIO on every storage gate.
"""

from minio.error import S3Error

from app.core.config import settings


def multipart_uploads(storage, keys: set[str], prefixes: set[str]):
    seen = set()
    for prefix in sorted(keys | prefixes):
        key_marker = upload_marker = None
        while True:
            page = storage._list_multipart_uploads(
                settings.MINIO_BUCKET,
                prefix=prefix,
                key_marker=key_marker,
                upload_id_marker=upload_marker,
                max_uploads=1000,
            )
            for item in page.uploads:
                identifier = (item.object_name, item.upload_id)
                if identifier not in seen and (
                    item.object_name in keys
                    or any(item.object_name.startswith(p) for p in prefixes)
                ):
                    seen.add(identifier)
                    yield item
            if not page.is_truncated:
                break
            following = (page.next_key_marker, page.next_upload_id_marker)
            if following == (key_marker, upload_marker) or not following[0]:
                raise RuntimeError("Multipart listing did not advance")
            key_marker, upload_marker = following


def erase_multipart(storage, keys: set[str], prefixes: set[str]) -> int:
    count = 0
    for item in multipart_uploads(storage, keys, prefixes):
        try:
            storage._abort_multipart_upload(
                settings.MINIO_BUCKET, item.object_name, item.upload_id
            )
        except S3Error as error:
            if error.code != "NoSuchUpload":
                raise
        count += 1
    return count
