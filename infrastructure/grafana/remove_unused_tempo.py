"""Exclude the unused Tempo datasource from the pinned Grafana OSS build.

Only Prometheus and Jaeger are provisioned by Verity. Every replacement is
counted so an upstream source change fails the build instead of silently
leaving Tempo's vulnerable dependency linked into the server.
"""

from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    source = Path(path)
    content = source.read_text()
    actual = content.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrences, found {actual}: {old!r}")
    source.write_text(content.replace(old, new))


core = "pkg/services/pluginsintegration/coreplugin/coreplugins.go"
replace(core, '\t"github.com/grafana/grafana/pkg/tsdb/tempo"\n', "")
replace(core, "pr *prometheus.Service, t *tempo.Service, td *testdatasource.Service", "pr *prometheus.Service, td *testdatasource.Service")
replace(core, "\t\tTempo:           asBackendPlugin(t),\n", "")
replace(core, "\tcase Tempo:\n\t\tsvc = tempo.ProvideService(httpClientProvider, tracer)\n", "")

wire = "pkg/server/wire.go"
replace(wire, '\t"github.com/grafana/grafana/pkg/tsdb/tempo"\n', "")
replace(wire, "\ttempo.ProvideService,\n", "")

generated = "pkg/server/wire_gen.go"
replace(generated, '\t"github.com/grafana/grafana/pkg/tsdb/tempo"\n', "")
replace(generated, "\ttempoService := tempo.ProvideService(httpclientProvider, tracer)\n", "", 2)
replace(generated, ", tempoService, testdatasourceService", ", testdatasourceService", 2)
replace(generated, ", tempo.ProvideService, loki.ProvideService", ", loki.ProvideService")

enterprise = "pkg/extensions/enterprise_imports.go"
replace(enterprise, '\t_ "github.com/grafana/grafana/pkg/tsdb/tempo"\n', "")
replace(enterprise, '\t_ "github.com/grafana/tempo/pkg/traceql"\n', "")
