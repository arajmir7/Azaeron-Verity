"""MinIO transport spans with no object names, request URLs or response bodies."""

import time
from minio import Minio as SDKMinio
from opentelemetry.trace import SpanKind
from app.core.observability import record_storage, safe_span


class Minio(SDKMinio):
    # One isolated adapter for the pinned MinIO SDK's transport hook. Live
    # upload/read/retention/erasure tests exercise this hook on SDK upgrades.
    def _execute(self, method, *args, **kwargs):
        operation = (
            method if method in {"GET", "PUT", "POST", "HEAD", "DELETE"} else "OTHER"
        )
        started = time.perf_counter()
        outcome = "error"
        with safe_span("storage." + operation, kind=SpanKind.CLIENT):
            try:
                response = super()._execute(method, *args, **kwargs)
                outcome = "success"
                return response
            finally:
                record_storage(operation, outcome, time.perf_counter() - started)
