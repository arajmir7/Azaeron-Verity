# Private inference deployment

The registry is deliberately empty. No runtime image, model or benchmark has been
approved. Rendering a production manifest therefore fails closed today.

After a licensed model and measured runtime have been approved in
`config/models/registry.json`, use the verification image to run:

```
python -m app.modules.inference.deployment --registry /registry/registry.json \
  --app-image <digest-pinned-Azaeron-runtime> --format kubernetes
```

The same command with `--format compose` emits a private Docker deployment.
Supply the local approved model bundle, registry directory and mutual-TLS directory.
The runtime has no published host ports or internet egress. Attach only the API/worker
to its private network; mount the registry and client certificate/key/CA into those
services, set `INFERENCE_ENABLED=true`, and set their private HTTPS endpoint.

Kubernetes output includes a ClusterIP service, service account without API token,
default-deny egress, ingress restricted to API/worker pods, non-root security context,
GPU node selection, artifact-integrity init container and immutable image references.
Provision the named read-only model PVC and mutual-TLS secret separately. A namespace
with an enforcing network-policy CNI and controlled service-account/pod labels is required.
Use a default-deny policy for API/worker egress with explicit DB/queue/storage/DNS/runtime
allowances. TCP probes indicate listener state; the gateway checks model-runtime health.

Weights are read only. Extra files, missing files, symlinks, pickle weights and remote
model code are rejected. The runtime is offline, request/output logging is disabled,
and no provider API key is used. No browser has model credentials or direct access.

The vLLM CLI contract is based on the [official serving reference](https://docs.vllm.ai/en/latest/cli/serve/).
Runtime flags, GPU scheduling, cold load, cancellation and quality must be exercised
against the exact approved image before promotion; generated manifests are contract-tested,
not evidence of an executed GPU deployment.

Generate and apply both `--task refine` and `--task verify` manifests. Each task has
its own runtime service, PVC, TLS secret and model-integrity job. The shared registry
ConfigMap is identical. Compose expects `AZAERON_REFINE_MODEL_DIRECTORY`,
`AZAERON_VERIFY_MODEL_DIRECTORY`, and corresponding `AZAERON_REFINE_TLS_DIRECTORY`
and `AZAERON_VERIFY_TLS_DIRECTORY`. Configure `INFERENCE_ENDPOINT` and
`INFERENCE_VERIFY_ENDPOINT` on API/worker; equal endpoints or equal model revisions
are rejected. Health requires both registered routes to respond successfully.
