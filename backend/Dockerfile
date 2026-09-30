FROM gcr.io/distroless/base-debian13:nonroot@sha256:0896741ba5bafd3ac87ea025a5f578952f2d238ddc3614cb368acc983a687aa2 AS runtime-os-upstream

FROM python:3.12-slim-trixie@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS runtime-security
# Stable trixie-security DSA-6531-1. Retain actual package records in the
# final distroless image; do not suppress scanner findings or use unstable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libssl3t64=3.5.7-1~deb13u3 openssl-provider-legacy=3.5.7-1~deb13u3 \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/runtime_security_overlay.py /runtime_security_overlay.py
RUN python /runtime_security_overlay.py

FROM runtime-os-upstream AS runtime-os
COPY --from=runtime-security /security-overlay/ /

FROM python:3.12-slim-trixie@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements.lock \
    && useradd --create-home --uid 1000 azaeron

FROM runtime-base AS verification-base
COPY requirements-dev.lock ./
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements-dev.lock

FROM verification-base AS verification-assemble
COPY --from=runtime-os / /base/
COPY scripts/assemble_runtime.py /assemble_runtime.py
RUN python /assemble_runtime.py --include-sqlite

FROM runtime-os AS verification
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:/usr/bin:/bin LD_LIBRARY_PATH=/usr/local/lib \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    RUFF_CACHE_DIR=/tmp/ruff-cache MYPY_CACHE_DIR=/tmp/mypy-cache
WORKDIR /app
COPY --from=verification-assemble /runtime-root/ /
COPY --chown=65532:65532 . .
USER 65532:65532
CMD ["pytest", "tests", "-q"]

FROM runtime-base AS assemble
COPY --from=runtime-os / /base/
COPY scripts/assemble_runtime.py /assemble_runtime.py
RUN python /assemble_runtime.py

FROM runtime-os AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH=/usr/local/bin:/usr/bin:/bin LD_LIBRARY_PATH=/usr/local/lib \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
COPY --from=assemble /runtime-root/ /
COPY --chown=65532:65532 app ./app
COPY --chown=65532:65532 alembic ./alembic
COPY --chown=65532:65532 migration_snapshots ./migration_snapshots
COPY --chown=65532:65532 alembic.ini ./
USER 65532:65532
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
