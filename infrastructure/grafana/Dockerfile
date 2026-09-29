FROM grafana/grafana:13.2.2@sha256:ac461fb352abc50da10a51c7d02462e9c05488f11f53f14b3ad79a8145f638a0

# Keep only data sources configured by this repository, refresh the Alpine
# security packages, and retain Grafana's upstream entrypoint and runtime user.
USER root
RUN apk upgrade --no-cache \
    && find /usr/share/grafana/data/plugins-bundled -mindepth 1 -maxdepth 1 \
        ! -name jaeger ! -name prometheus -exec rm -rf {} +
USER 472:0
