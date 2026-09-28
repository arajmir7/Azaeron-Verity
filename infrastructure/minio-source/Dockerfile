# The archived MinIO community releases are fetched from their immutable
# upstream Git commits. BuildKit checks the archive bytes before extraction.
FROM golang:1.26.8-alpine3.24@sha256:8ac98ca534ac3f51e1f420a1dd2c15e74c75cfa0f23f3ad27eb5d7236c349a0c AS server-build
WORKDIR /src
ADD --checksum=sha256:09ffb1ddfa9636348f8d029f9680bb086840dccf9d34370e8462151d28e95f97 https://codeload.github.com/minio/minio/tar.gz/5aebb3970e132ca231508152c0333cb223c83d70 /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1 && rm /tmp/source.tgz
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/apache/thrift@v0.24.0 github.com/buger/jsonparser@v1.1.2 \
      github.com/go-jose/go-jose/v4@v4.1.4 github.com/prometheus/prometheus@v0.311.3 \
      github.com/rabbitmq/amqp091-go@v1.13.0 \
      golang.org/x/crypto@v0.55.0 google.golang.org/grpc@v1.83.2 \
    && go mod download && go mod verify
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -mod=mod -trimpath -tags kqueue -ldflags='-s -w' -o /out/minio . \
    && go mod verify

FROM golang:1.26.8-alpine3.24@sha256:8ac98ca534ac3f51e1f420a1dd2c15e74c75cfa0f23f3ad27eb5d7236c349a0c AS client-build
WORKDIR /src
ADD --checksum=sha256:4cea8ed209c8f96e59ea1a5cc4901019b54c2be6d6f5f16c6749ea8bdcf4172e https://codeload.github.com/minio/mc/tar.gz/d6541ea280b73a834b64d4097e21f2be77676104 /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1 && rm /tmp/source.tgz
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN --mount=type=cache,target=/go/pkg/mod \
    go get github.com/prometheus/prometheus@v0.311.3 \
      golang.org/x/crypto@v0.55.0 google.golang.org/grpc@v1.83.2 \
    && go mod tidy && go mod download && go mod verify
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -trimpath -tags kqueue -ldflags='-s -w' -o /out/mc .

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS server
RUN apk add --no-cache ca-certificates && addgroup -g 10001 minio && adduser -D -H -u 10001 -G minio minio \
    && mkdir /data && chown minio:minio /data
COPY --from=server-build /out/minio /usr/local/bin/minio
COPY --from=server-build /src/LICENSE /usr/share/licenses/minio/LICENSE
COPY --from=server-build /src/NOTICE /usr/share/licenses/minio/NOTICE
USER 10001:10001
VOLUME /data
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]

FROM alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8 AS client
RUN apk add --no-cache ca-certificates && addgroup -g 10001 minio && adduser -D -u 10001 -G minio minio
COPY --from=client-build /out/mc /usr/local/bin/mc
COPY --from=client-build /src/LICENSE /usr/share/licenses/mc/LICENSE
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/mc"]
