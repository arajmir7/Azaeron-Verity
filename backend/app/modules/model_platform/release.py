"""Offline promotion: verify all evidence, then atomically write a new registry.

No command flag bypasses rights, test-only restrictions or independent approval.
The input registry is preserved; the operator reviews the new output file.
"""

import argparse
import json
from pathlib import Path

from app.modules.inference.registry import (
    AzaeronModelRegistry,
    ModelRecord,
    verify_artifacts,
)
from .policy import (
    Lineage,
    PolicyError,
    ReleaseApproval,
    canonical,
    digest,
    verify_release_files,
)


def promote(
    bundle: Path, metadata: dict, approval: dict, catalog: AzaeronModelRegistry
):
    lineage = Lineage.model_validate_json((bundle / "lineage.json").read_bytes())
    release = ReleaseApproval.model_validate(approval)
    if any(path.is_symlink() for path in bundle.rglob("*")):
        raise PolicyError("symlink_not_allowed")
    artifacts = {
        path.relative_to(bundle).as_posix(): digest(path)
        for path in bundle.rglob("*")
        if path.is_file()
    }
    record = ModelRecord.model_validate(
        {
            **metadata,
            "artifacts": artifacts,
            "lineage": lineage,
            "release": release,
            "status": "APPROVED",
            "commercial_use_approved": True,
            "approval_reference": release.reference,
            "evaluation_sha256": release.gates["evaluation"].evidence.sha256,
        }
    )
    if record.model_id in {m.model_id for m in catalog.models}:
        raise PolicyError("model_id_already_registered_use_new_versioned_id")
    verify_artifacts(record, bundle)
    verify_release_files(record, bundle)
    evaluation = json.loads(
        (bundle / release.gates["evaluation"].evidence.path).read_bytes()
    )
    if (
        evaluation.get("purpose") != "PRODUCTION"
        or evaluation.get("examples", 0) < 1000
        or not evaluation.get("checks")
        or not all(value is True for value in evaluation["checks"].values())
        or evaluation.get("baseline_comparison") != "PASS"
        or evaluation.get("production_load_benchmark") != "PASS"
    ):
        raise PolicyError("evaluation_or_comparative_benchmarks_incomplete")
    if lineage.family in {"detector", "verifier"}:
        calibration = json.loads((bundle / "calibration.json").read_bytes())
        if calibration != evaluation.get("calibration"):
            raise PolicyError("calibration_not_bound_to_evaluation")
    return AzaeronModelRegistry.model_validate(
        {
            **catalog.model_dump(),
            "models": [*catalog.models, record],
            "routes": {
                **catalog.routes,
                **{task: record.model_id for task in record.tasks},
            },
            "status": "APPROVED_MODELS_REGISTERED",
        }
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["bundle", "metadata", "approval", "registry", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    updated = promote(
        args.bundle,
        json.loads(args.metadata.read_bytes()),
        json.loads(args.approval.read_bytes()),
        AzaeronModelRegistry.load(args.registry),
    )
    # Exclusive creation prevents an accidental overwrite of the active registry.
    with args.output.open("xb") as stream:
        stream.write(canonical(updated.model_dump(mode="json")) + b"\n")
    print(
        json.dumps(
            {
                "status": "REGISTRY_WRITTEN",
                "models": len(updated.models),
                "deployment": "NOT_PERFORMED",
            }
        )
    )


if __name__ == "__main__":
    main()
