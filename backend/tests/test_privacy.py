"""Erasure requires verified version absence, including legacy staging keys."""

from types import SimpleNamespace

import pytest

from app.modules.privacy.service import erase_objects, object_targets


class Storage:
    def __init__(self, rows, *, refuse=False):
        self.rows = set(rows)
        self.refuse = refuse

    def list_objects(self, bucket, prefix, recursive, include_version):
        assert recursive and include_version
        return iter(
            [
                SimpleNamespace(object_name=key, version_id=version)
                for key, version in self.rows
                if key.startswith(prefix)
            ]
        )

    def remove_object(self, bucket, key, version_id):
        if not self.refuse:
            self.rows.discard((key, version_id))

    def _list_multipart_uploads(self, *args, **kwargs):
        return SimpleNamespace(uploads=[], is_truncated=False)


def test_erasure_deletes_all_versions_and_markers_without_prefix_collision():
    storage = Storage(
        {
            ("versions/o/d/file.txt", "old"),
            ("versions/o/d/file.txt", "new"),
            ("versions/o/d/file.txt", "marker"),
            ("uploads/o/u/doc.txt", None),
            ("uploads/o/u/doc.txt.other", "keep"),
            ("versions/other/d/file.txt", "keep"),
        }
    )
    request = {"object_keys": ["uploads/o/u/doc.txt"], "prefixes": ["versions/o/d/"]}
    assert erase_objects(storage, request) == 4
    assert storage.rows == {
        ("uploads/o/u/doc.txt.other", "keep"),
        ("versions/other/d/file.txt", "keep"),
    }
    assert erase_objects(storage, request) == 0


def test_snapshot_erasure_includes_original_staging_object():
    keys, prefixes = object_targets(
        {
            "object_keys": ["versions/uploads/o/u/upload/" + "a" * 64 + ".txt"],
            "prefixes": [],
        }
    )
    assert "uploads/o/u/upload.txt" in keys
    assert not prefixes


def test_retained_object_is_not_success():
    storage = Storage({("versions/o/d/file.txt", "version")}, refuse=True)
    with pytest.raises(RuntimeError, match="absence"):
        erase_objects(storage, {"object_keys": [], "prefixes": ["versions/o/d/"]})


def test_unavailable_listing_is_not_success():
    class Unavailable(Storage):
        def list_objects(self, *args, **kwargs):
            raise OSError("synthetic storage unavailable")

    with pytest.raises(OSError):
        erase_objects(
            Unavailable(set()),
            {"object_keys": ["uploads/o/u/file.txt"], "prefixes": []},
        )


@pytest.mark.parametrize("path", ["", "/root", "uploads/o/../other/"])
def test_invalid_manifests_fail_closed(path):
    with pytest.raises(ValueError):
        object_targets({"object_keys": [], "prefixes": [path]})


def test_lifecycle_initialization_and_operator_rule_preservation():
    from minio.commonconfig import ENABLED, Filter
    from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
    from app.modules.privacy.storage import configure_lifecycle

    class LifecycleStorage:
        config = None

        def get_bucket_lifecycle(self, bucket):
            return self.config

        def set_bucket_lifecycle(self, bucket, config):
            self.config = config

    storage = LifecycleStorage()
    configure_lifecycle(storage)
    assert {rule.rule_id for rule in storage.config.rules} == {"verity-temporary"}
    custom = Rule(
        ENABLED,
        rule_id="operator-policy",
        rule_filter=Filter(prefix="operator/"),
        expiration=Expiration(days=30),
    )
    storage.config = LifecycleConfig([*storage.config.rules, custom])
    configure_lifecycle(storage)
    assert len(storage.config.rules) == 2
    assert custom in storage.config.rules


def test_multipart_abort_and_verification_cannot_hide_remaining_parts():
    class MultipartStorage(Storage):
        def __init__(self, refuse=False):
            super().__init__(set(), refuse=refuse)
            self.uploads = {("uploads/o/u/file.txt", "fixture-upload")}

        def _list_multipart_uploads(self, bucket, **kwargs):
            return SimpleNamespace(
                uploads=[
                    SimpleNamespace(object_name=key, upload_id=value)
                    for key, value in self.uploads
                ],
                is_truncated=False,
            )

        def _abort_multipart_upload(self, bucket, key, upload_id):
            if not self.refuse:
                self.uploads.discard((key, upload_id))

    record = {"object_keys": ["uploads/o/u/file.txt"], "prefixes": []}
    storage = MultipartStorage()
    assert erase_objects(storage, record) == 1
    assert not storage.uploads
    with pytest.raises(RuntimeError, match="Multipart absence"):
        erase_objects(MultipartStorage(refuse=True), record)
