# Official datasource release archives retain their complete signed manifests.
# Digest-pinned base and SHA256-checked archives are scanned without exceptions.
ARG TARGETARCH

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

USER 472:0
