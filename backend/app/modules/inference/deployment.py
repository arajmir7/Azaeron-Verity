"""Render private Kubernetes/Compose runtime manifests only for approved models.

Run in the verification image: python -m app.modules.inference.deployment ...
No model, image or artifact is downloaded by this command.
"""

import argparse
import json
from pathlib import Path
import re
from typing import get_args

from app.modules.inference.registry import AzaeronModelRegistry, Task, verify_artifacts

# This path is a private emptyDir/tmpfs in a read-only pod.
SCRATCH_DIRECTORY = "/tmp"  # nosec B108


def deployment(
    catalog: AzaeronModelRegistry,
    task: Task,
    app_image: str,
    namespace: str = "azaeron",
) -> dict:
    model = catalog.select(task)
    name = {"refine": "inference", "verify": "verification"}.get(
        task, "inference-" + task
    )
    if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", app_image):
        raise ValueError("Artifact-check image must be digest-pinned")
    if not re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", namespace):
        raise ValueError("Invalid namespace")
    args = [
        "serve",
        "/models",
        "--served-model-name",
        model.model_id,
        "--host",
        # Network policy limits this pod to API/worker ingress.
        "0.0.0.0",  # nosec B104
        "--port",
        "8000",
        "--max-model-len",
        str(model.context_limit),
        "--load-format",
        "safetensors",
        "--generation-config",
        "vllm",
        "--no-trust-remote-code",
        "--no-enable-log-requests",
        "--no-enable-log-outputs",
        "--disable-fastapi-docs",
        "--ssl-certfile",
        "/tls/tls.crt",
        "--ssl-keyfile",
        "/tls/tls.key",
        "--ssl-ca-certs",
        "/tls/ca.crt",
        "--ssl-cert-reqs",
        "2",
    ]
    if model.quantization != "none":
        args.extend(["--quantization", model.quantization])
    labels = {"app": f"azaeron-{name}"}
    env = [
        {"name": name, "value": value}
        for name, value in {
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
            "VLLM_NO_USAGE_STATS": "1",
            "VLLM_LOGGING_LEVEL": "WARNING",
            "HF_HOME": f"{SCRATCH_DIRECTORY}/huggingface",
        }.items()
    ]
    mounts = [
        {"name": name, "mountPath": path, "readOnly": True}
        for name, path in (
            ("models", "/models"),
            ("tls", "/tls"),
            ("registry", "/registry"),
        )
    ]
    security = {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    common = {"namespace": namespace}
    policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {**common, "name": f"azaeron-{name}-private"},
        "spec": {
            "podSelector": {"matchLabels": labels},
            "policyTypes": ["Ingress", "Egress"],
            "egress": [],
            "ingress": [
                {
                    "from": [
                        {"podSelector": {"matchLabels": {"app": "azaeron-api"}}},
                        {"podSelector": {"matchLabels": {"app": "azaeron-worker"}}},
                    ],
                    "ports": [{"protocol": "TCP", "port": 8000}],
                }
            ],
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {**common, "name": f"{name}-runtime"},
        "spec": {
            "type": "ClusterIP",
            "selector": labels,
            "ports": [{"port": 8000, "targetPort": 8000}],
        },
    }
    pod = {
        "serviceAccountName": f"azaeron-{name}",
        "automountServiceAccountToken": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": 65532,
            "runAsGroup": 65532,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "nodeSelector": {"azaeron.ai/workload": "inference"},
        "initContainers": [
            {
                "name": "artifact-integrity",
                "image": app_image,
                "command": [
                    "python",
                    "-m",
                    "app.modules.inference.deployment",
                    "--registry",
                    "/registry/registry.json",
                    "--verify",
                    "/models",
                    "--task",
                    task,
                ],
                "volumeMounts": mounts,
                "securityContext": security,
            }
        ],
        "containers": [
            {
                "name": "runtime",
                "image": model.runtime_image,
                "command": ["vllm"],
                "args": args,
                "env": env,
                "securityContext": security,
                "volumeMounts": mounts
                + [{"name": "scratch", "mountPath": SCRATCH_DIRECTORY}],
                "ports": [{"containerPort": 8000}],
                "resources": {
                    "limits": {"nvidia.com/gpu": "1"},
                    "requests": {
                        "cpu": "2",
                        "memory": model.hardware.get("memory", "16Gi"),
                    },
                },
                "startupProbe": {
                    "tcpSocket": {"port": 8000},
                    "failureThreshold": 90,
                    "periodSeconds": 10,
                },
                "readinessProbe": {"tcpSocket": {"port": 8000}, "periodSeconds": 10},
            }
        ],
        "volumes": [
            {
                "name": "models",
                "persistentVolumeClaim": {
                    "claimName": f"azaeron-approved-{task}-model",
                    "readOnly": True,
                },
            },
            {"name": "tls", "secret": {"secretName": f"azaeron-{name}-tls"}},
            {"name": "registry", "configMap": {"name": "azaeron-model-registry"}},
            {"name": "scratch", "emptyDir": {"sizeLimit": "4Gi"}},
        ],
    }
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": [
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {**common, "name": f"azaeron-{name}"},
                "automountServiceAccountToken": False,
            },
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {**common, "name": "azaeron-model-registry"},
                "data": {"registry.json": catalog.model_dump_json()},
            },
            policy,
            service,
            {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {**common, "name": f"azaeron-{name}"},
                "spec": {
                    "replicas": 1,
                    "selector": {"matchLabels": labels},
                    "strategy": {"type": "Recreate"},
                    "template": {"metadata": {"labels": labels}, "spec": pod},
                },
            },
        ],
    }


def compose_manifest(catalog: AzaeronModelRegistry, task: Task, app_image: str) -> dict:
    name = {"refine": "inference", "verify": "verification"}.get(
        task, "inference-" + task
    )
    bundle = (
        "${AZAERON_"
        + task.upper()
        + "_MODEL_DIRECTORY:?approved local bundle required}:/models:ro"
    )
    tls = "${AZAERON_" + task.upper() + "_TLS_DIRECTORY:?mutual TLS required}:/tls:ro"
    spec = deployment(catalog, task, app_image)["items"][-1]["spec"]["template"]["spec"]
    runtime = spec["containers"][0]
    return {
        "services": {
            f"{name}-integrity": {
                "image": app_image,
                "network_mode": "none",
                "user": "65532:65532",
                "read_only": True,
                "command": spec["initContainers"][0]["command"],
                "volumes": [
                    bundle,
                    "${AZAERON_REGISTRY_DIRECTORY:?registry required}:/registry:ro",
                ],
            },
            f"{name}-runtime": {
                "image": runtime["image"],
                "command": runtime["command"] + runtime["args"],
                "user": "65532:65532",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {v["name"]: v["value"] for v in runtime["env"]},
                "tmpfs": [f"{SCRATCH_DIRECTORY}:uid=65532,gid=65532,size=4g"],
                "volumes": [
                    bundle,
                    tls,
                ],
                "depends_on": {
                    f"{name}-integrity": {"condition": "service_completed_successfully"}
                },
                "networks": ["inference-private"],
                "deploy": {
                    "resources": {
                        "reservations": {
                            "devices": [
                                {
                                    "driver": "nvidia",
                                    "count": 1,
                                    "capabilities": ["gpu"],
                                }
                            ]
                        }
                    }
                },
            },
        },
        "networks": {"inference-private": {"internal": True}},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--task", choices=get_args(Task), default="refine")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--app-image")
    parser.add_argument(
        "--format", choices=["kubernetes", "compose"], default="kubernetes"
    )
    args = parser.parse_args()
    catalog = AzaeronModelRegistry.load(args.registry)
    if args.verify:
        verify_artifacts(catalog.select(args.task), args.verify)
        print('{"artifact_integrity":"PASS"}')
    else:
        if not args.app_image:
            parser.error("--app-image is required for deployment generation")
        if args.format == "kubernetes":
            result = deployment(catalog, args.task, args.app_image)
        else:
            result = compose_manifest(catalog, args.task, args.app_image)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
