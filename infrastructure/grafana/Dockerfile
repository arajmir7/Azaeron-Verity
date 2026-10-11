# Grafana 13.1.7 is a supported maintenance release with built-in Prometheus
# and Jaeger datasources. Rebuild its server with patched Go dependencies.
# This avoids the vulnerable standalone signed datasource binaries introduced
# in 13.2 without weakening plugin signature verification or image scanning.
FROM golang:1.27.2-alpine3.24@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS patched-server
RUN apk add --no-cache git
WORKDIR /src
ADD --checksum=sha256:0847dbf85e4c10f8bb70f7f8e0650d6403f3c53b97022d034bdcae3673230d0a https://codeload.github.com/grafana/grafana/tar.gz/a9465000d8f7f3bde52bb9a456b8a1e9e9b1d51a /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2
RUN --mount=type=cache,target=/go/pkg/mod go get golang.org/x/net@v0.60.0 \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = v0.60.0
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -tags oss -trimpath -buildvcs=false \
      -ldflags='-s -w -X main.version=13.1.7 -X main.commit=a9465000d8f7f3bde52bb9a456b8a1e9e9b1d51a' \
      -o /out/grafana ./pkg/cmd/grafana \
    && go version -m /out/grafana > /out/build-info.txt \
    && go mod verify

FROM grafana/grafana:13.1.7@sha256:248cda1de5bc3e69c3fb23c5efe1292aa18399d8ece499aa88cab6fd16f78d4b
USER root
COPY --from=patched-server /out/grafana /usr/share/grafana/bin/grafana
COPY --from=patched-server /out/build-info.txt /usr/share/grafana/build-info.txt
USER 472:0
