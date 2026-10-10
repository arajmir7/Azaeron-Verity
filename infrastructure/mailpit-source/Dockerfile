# Rebuild upstream Mailpit v1.31.4 from its exact source commit with patched Go.
# The archive checksum is verified by BuildKit before extraction.
FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85 AS ui-build
WORKDIR /src
ADD --checksum=sha256:e799d0b014001925629b175a5642e363e8cd2425e1fec643e2c7b9b26c1d6ef2 https://codeload.github.com/axllent/mailpit/tar.gz/ccb524a62b3a14b6a3fd55c1275a16945d10e36b /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1 && rm /tmp/source.tgz \
    && npm ci && npm run package

FROM golang:1.26.9-alpine3.24@sha256:3082400e369fa24d5fc60bca20edab3f6d604e0c5a690ec66b295eff4dd87ade AS binary-build
WORKDIR /src
ADD --checksum=sha256:e799d0b014001925629b175a5642e363e8cd2425e1fec643e2c7b9b26c1d6ef2 https://codeload.github.com/axllent/mailpit/tar.gz/ccb524a62b3a14b6a3fd55c1275a16945d10e36b /tmp/source.tgz
RUN tar -xzf /tmp/source.tgz --strip-components=1 && rm /tmp/source.tgz
COPY --from=ui-build /src/server/ui/dist/ /src/server/ui/dist/
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
RUN --mount=type=cache,target=/go/pkg/mod \
    go get golang.org/x/net@v0.60.0 && go mod download && go mod verify
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -trimpath -ldflags='-s -w -X github.com/axllent/mailpit/config.Version=v1.31.4-azaeron-go1.26.9' -o /out/mailpit . \
    && go mod verify

FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates tzdata
COPY --from=binary-build /out/mailpit /mailpit
COPY --from=binary-build /src/LICENSE /usr/share/licenses/mailpit/LICENSE
USER 65532:65532
EXPOSE 1025 1110 8025
HEALTHCHECK --interval=15s --start-period=10s CMD ["/mailpit", "readyz"]
ENTRYPOINT ["/mailpit"]
