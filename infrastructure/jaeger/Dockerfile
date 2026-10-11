# PRD-022/TRD-022: reproducible, non-production trial of the upstream Jaeger
# 2.22.0 source with the patched Go standard library and x/net module.
FROM golang:1.27.2-alpine3.24@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS build
RUN apk add --no-cache gzip
WORKDIR /src
ADD --checksum=sha256:74ff87bf31cfc1512b1c309831f9f47319a0291c8ec8ff3cf2956917a0a9847f https://codeload.github.com/jaegertracing/jaeger/tar.gz/462bb49fcff9af4be9556bf0206d07f5171bd8d7 /tmp/source.tgz
ADD --checksum=sha256:18d9deb8aaf19ba9a5f9709417f8ae7ca71d99937ea68140a866d9d703da3d6a https://github.com/jaegertracing/jaeger-ui/releases/download/v2.22.0/assets.tar.gz /tmp/ui.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1 \
    && tar -xzf /tmp/ui.tgz -C /tmp \
    && cp -R /tmp/packages/jaeger-ui/build/. cmd/jaeger/internal/extension/jaegerquery/internal/ui/actual/ \
    && find cmd/jaeger/internal/extension/jaegerquery/internal/ui/actual -type f ! -name .gitignore -exec gzip --no-name {} +
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOMAXPROCS=2
RUN --mount=type=cache,target=/go/pkg/mod go get golang.org/x/net@v0.60.0 \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = v0.60.0
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -trimpath -ldflags='-s -w' -o /out/jaeger ./cmd/jaeger \
    && go version -m /out/jaeger > /out/build-info.txt \
    && go mod verify

FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN mkdir -p /etc/jaeger /tmp/badger-v2/key /tmp/badger-v2/data \
    && chmod 1777 /tmp \
    && chown -R 10001:0 /tmp/badger-v2
COPY --from=build --chown=10001:0 /out/jaeger /usr/local/bin/jaeger
COPY --from=build /out/build-info.txt /usr/share/jaeger/build-info.txt
COPY --from=build /src/LICENSE /usr/share/licenses/jaeger/LICENSE
COPY --chown=10001:0 config.yaml /etc/jaeger/config.yaml
USER 10001:0
VOLUME /tmp
EXPOSE 4317 4318 16686
ENTRYPOINT ["/usr/local/bin/jaeger"]
CMD ["--config=/etc/jaeger/config.yaml"]
