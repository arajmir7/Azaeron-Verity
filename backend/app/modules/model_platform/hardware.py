"""Conservative planning estimates, not measured training-memory certification."""

from __future__ import annotations

import platform
import shutil

from .policy import PolicyError


def profile():
    import psutil
    import torch

    memory = psutil.virtual_memory()
    gpus = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            item = torch.cuda.get_device_properties(index)
            free, total = torch.cuda.mem_get_info(index)
            gpus.append(
                {
                    "index": index,
                    "name": item.name,
                    "total_bytes": total,
                    "free_bytes": free,
                }
            )
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "memory_total_bytes": memory.total,
        "memory_available_bytes": memory.available,
        "disk_free_bytes": shutil.disk_usage(".").free,
        "mps_available": torch.backends.mps.is_available(),
        "cuda": gpus,
    }


def plan(
    parameters,
    trainable,
    *,
    method,
    precision,
    layers,
    width,
    heads,
    vocab,
    sequence,
    microbatch,
    accumulation,
    checkpointing,
    tokens,
):
    if (
        min(
            parameters,
            trainable,
            layers,
            width,
            heads,
            vocab,
            sequence,
            microbatch,
            accumulation,
            tokens,
        )
        <= 0
    ):
        raise PolicyError("invalid_memory_plan_dimensions")
    element = 4 if precision == "float32" else 2
    weights = int(parameters * (0.625 if method == "qlora" else element))
    # Full-precision Adam moments, gradients and a conservative master-weight allowance.
    optimizer = trainable * 8
    gradients = trainable * 4
    master = trainable * 4
    activations = (
        microbatch * sequence * width * element * (4 if checkpointing else layers * 16)
    )
    # Include eager attention and vocabulary logits even when fused kernels might reduce them.
    attention = (
        microbatch * heads * sequence**2 * element * (1 if checkpointing else layers)
    )
    logits = microbatch * sequence * vocab * 4
    subtotal = (
        weights + optimizer + gradients + master + activations + attention + logits
    )
    estimated = int(subtotal * 1.3 + 1024**3)
    return {
        "kind": "CONSERVATIVE_ESTIMATE_NOT_MEASUREMENT",
        "parameters": parameters,
        "trainable_parameters": trainable,
        "method": method,
        "precision": precision,
        "weights_bytes": weights,
        "optimizer_bytes": optimizer,
        "gradient_bytes": gradients,
        "master_weights_bytes": master,
        "activation_bytes": activations,
        "attention_bytes": attention,
        "logits_bytes": logits,
        "sequence_length": sequence,
        "microbatch": microbatch,
        "gradient_accumulation": accumulation,
        "effective_batch": microbatch * accumulation,
        "gradient_checkpointing": checkpointing,
        "estimated_device_bytes": estimated,
        "estimated_training_tokens": tokens,
        "estimated_training_flops": 6 * parameters * tokens,
        "estimated_compute_seconds": None,
        "compute_time_blocker": "Requires measured sustained throughput on the selected GPU",
    }


def enforce(plan_value, hardware, device, *, output_bytes):
    if plan_value["method"] == "qlora" and device != "cuda":
        raise PolicyError("qlora_requires_validated_cuda_runtime")
    if device == "cuda":
        if not hardware["cuda"]:
            raise PolicyError("cuda_gpu_not_available")
        available = int(hardware["cuda"][0]["free_bytes"] * 0.8)
    else:
        if device == "mps" and not hardware["mps_available"]:
            raise PolicyError("mps_not_available")
        available = min(
            int(hardware["memory_total_bytes"] * 0.6),
            hardware["memory_available_bytes"] - 2 * 1024**3,
        )
    if plan_value["estimated_device_bytes"] > available:
        raise PolicyError("insufficient_safe_training_memory")
    if output_bytes + 5 * 1024**3 > hardware["disk_free_bytes"]:
        raise PolicyError("insufficient_checkpoint_disk")
