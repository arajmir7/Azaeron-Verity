FROM jaegertracing/jaeger:2.21.0@sha256:3d0ac795ff98aa04d1be04311d2dac6c25b4bfc8322dc02e53bc5b170c5018c3 AS upstream

FROM alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6
RUN mkdir -p /etc/jaeger /tmp/badger-v2/key /tmp/badger-v2/data \
    && chmod 1777 /tmp \
    && chown -R 10001:0 /tmp/badger-v2
COPY --from=upstream --chown=10001:0 /cmd/jaeger/jaeger-linux /usr/local/bin/jaeger
COPY --chown=10001:0 config.yaml /etc/jaeger/config.yaml
USER 10001:0
VOLUME /tmp
EXPOSE 4317 4318 16686
ENTRYPOINT ["/usr/local/bin/jaeger"]
CMD ["--config=/etc/jaeger/config.yaml"]
