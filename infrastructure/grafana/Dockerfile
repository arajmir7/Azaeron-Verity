# PRD-022/TRD-022: patch the server without altering vendor-signed datasources.
# The image remains blocked by datasource findings until signed fixes exist.
ARG TARGETARCH
FROM golang:1.27.2-alpine3.24@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS patched-server
RUN apk add --no-cache git
WORKDIR /src
ADD --checksum=sha256:222f8cd14b5345d024ab460d592c63c1e7432cb20a89e2dbcc86d7bfd83df3ac https://codeload.github.com/grafana/grafana/tar.gz/6193dc03311b631b9727b560d24369e683dc396e /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2
RUN --mount=type=cache,target=/go/pkg/mod go get golang.org/x/net@v0.60.0 \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = v0.60.0
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -tags oss -trimpath -buildvcs=false \
      -ldflags='-s -w -X main.version=13.2.3 -X main.commit=6193dc03311b631b9727b560d24369e683dc396e' \
      -o /out/grafana ./pkg/cmd/grafana \
    && go version -m /out/grafana > /out/build-info.txt \
    && go mod verify

# Official datasource release archives retain their complete signed manifests.
# Digest-pinned base and SHA256-checked archives are scanned without exceptions.
FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS plugins-amd64

ADD --checksum=sha256:dc57642e289ba81a2dd7179b0f7e945966f5db1234c7aaf9e470a2db34207ce1 https://github.com/grafana/grafana-jaeger-datasource/releases/download/v13.0.5/jaeger-13.0.5.linux_amd64.zip /tmp/jaeger.zip

ADD --checksum=sha256:8bdd6583e398f84d497dabec0287563b9eee471d711dea08a21482db5cd5a294 https://github.com/grafana/grafana-prometheus-datasource/releases/download/v13.2.3/prometheus-13.2.3.linux_amd64.zip /tmp/prometheus.zip

RUN mkdir /plugins && unzip -q /tmp/jaeger.zip -d /plugins && unzip -q /tmp/prometheus.zip -d /plugins && chmod +x /plugins/*/gpx_*

FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6 AS plugins-arm64

ADD --checksum=sha256:62cac5d2ab05881ddfafb0654267406ae13df3c11395ce7ef6f65e0b3193c17f https://github.com/grafana/grafana-jaeger-datasource/releases/download/v13.0.5/jaeger-13.0.5.linux_arm64.zip /tmp/jaeger.zip

ADD --checksum=sha256:a49bb6a6fe6e79578dc78841ce7f437a50d294a0fdb74bf25214cd6ce75d85db https://github.com/grafana/grafana-prometheus-datasource/releases/download/v13.2.3/prometheus-13.2.3.linux_arm64.zip /tmp/prometheus.zip

RUN mkdir /plugins && unzip -q /tmp/jaeger.zip -d /plugins && unzip -q /tmp/prometheus.zip -d /plugins && chmod +x /plugins/*/gpx_*

FROM plugins-${TARGETARCH} AS plugins

FROM grafana/grafana:13.2.3@sha256:b28bae15e219c998fb0e0424ed724930cc61b1f61fb404d47c862f9a23f9e572

USER root

RUN rm -rf /usr/share/grafana/data/plugins-bundled/*

COPY --from=plugins --chown=472:0 /plugins/ /usr/share/grafana/data/plugins-bundled/
COPY --from=patched-server /out/grafana /usr/share/grafana/bin/grafana
COPY --from=patched-server /out/build-info.txt /usr/share/grafana/build-info.txt

USER 472:0
