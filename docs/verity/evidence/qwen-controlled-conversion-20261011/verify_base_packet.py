#!/usr/bin/env python3
"""Replay the proposed base inventory and prove pending owner review fails closed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.modules.model_platform.admission import Candidate, verify_bundle
from app.modules.model_platform.owner_decision import (
    OwnerDecision,
    require_owner_approval,
)
from app.modules.model_platform.policy import PolicyError


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--owner-packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate = Candidate.model_validate_json(args.candidate.read_bytes())
    verify_bundle(candidate, args.bundle)
    packet = OwnerDecision.model_validate_json(args.owner_packet.read_bytes())
    candidate_sha = sha(args.candidate)
    if len(packet.subjects) != 1 or packet.subjects[0].sha256 != candidate_sha:
        raise ValueError("owner packet is not bound to the proposed candidate")
    if packet.decision != "PENDING" or packet.confirmation_status != "PENDING":
        raise ValueError("owner packet was unexpectedly decided")
    checked_evidence = 0
    for reference in packet.subjects[0].evidence:
        if reference.startswith("https://"):
            continue
        path_text, separator, expected = reference.partition(" SHA256 ")
        if not separator or sha(Path(path_text)) != expected:
            raise ValueError(f"supporting evidence hash mismatch: {path_text}")
        checked_evidence += 1
    try:
        require_owner_approval(
            args.owner_packet,
            "BASE_MODEL",
            candidate_sha,
            "commercial_derivative_training",
        )
    except PolicyError as exc:
        if str(exc) != "owner_decision_not_approved":
            raise
    else:
        raise ValueError("pending packet improperly authorized training")

    args.output.write_text(
        json.dumps(
            {
                "candidate_manifest_sha256": candidate_sha,
                "pending_owner_packet_sha256": sha(args.owner_packet),
                "checkpoint_sha256": candidate.artifacts["model.safetensors"],
                "candidate_schema": "PASS",
                "exact_bundle_hash_and_safetensors_validation": "PASS",
                "owner_decision_schema": "PASS",
                "supporting_evidence_hashes_checked": checked_evidence,
                "pending_decision_fail_closed": "PASS",
                "commercial_base_admitted": False,
                "training_authorized": False,
                "production_approved": False,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
