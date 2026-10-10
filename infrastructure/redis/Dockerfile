# Retain the upstream Redis binary and entrypoint; apply fixed packages from
# the same stable Alpine 3.21 repository used by this digest-pinned image.
FROM redis:7.4-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499
RUN apk add --no-cache --upgrade libcrypto3=3.3.7-r2 libssl3=3.3.7-r2
