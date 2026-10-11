"""Hash-bound owner decisions for production model and data admission.

The record is an internal attestation, never a substitute for third-party rights
or for independent model-quality review. Pending/rejected records grant nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .policy import Digest, PolicyError, StrictModel, canonical


class ReviewedSubject(StrictModel):
    kind: Literal["DATASET", "BASE_MODEL", "MODEL_RELEASE"]
    identifier: str = Field(min_length=1)
    sha256: Digest
    license: str = Field(min_length=1)
    rights: Literal["PASS", "UNRESOLVED"]
    provenance: Literal["PASS", "UNRESOLVED"]
    copyright: Literal["PASS", "UNRESOLVED"]
    privacy: Literal["PASS", "NOT_APPLICABLE", "UNRESOLVED"]
    permitted_uses: list[str] = Field(min_length=1)
    findings: list[str] = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    risks: list[str]
    restrictions: list[str]


class OwnerDecision(StrictModel):
    schema_version: Literal[1] = 1
    subjects: list[ReviewedSubject] = Field(min_length=1)
    subject_sha256: Digest
    decision: Literal["PENDING", "APPROVE_WITHIN_SCOPE", "REJECT"]
    approver_role: Literal["AZAERON_PROJECT_OWNER"] = "AZAERON_PROJECT_OWNER"
    approver_name: str | None = None
    decided_at: str | None = None
    rationale: str | None = None
    reviewed_record_sha256: Digest | None = None
    confirmation_status: Literal["PENDING", "CONFIRMED"] = "PENDING"
    confirmation_reference: str | None = None

    @model_validator(mode="after")
    def bound_and_explicit(self):
        expected = hashlib.sha256(
            canonical([subject.model_dump(mode="json") for subject in self.subjects])
        ).hexdigest()
        if self.subject_sha256 != expected:
            raise ValueError("Owner decision subject hash mismatch")
        keys = [(subject.kind, subject.sha256) for subject in self.subjects]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate owner decision subject")
        if self.decision == "PENDING":
            if (
                any(
                    (
                        self.approver_name,
                        self.decided_at,
                        self.rationale,
                        self.reviewed_record_sha256,
                        self.confirmation_reference,
                    )
                )
                or self.confirmation_status != "PENDING"
            ):
                raise ValueError("Pending decision cannot contain an owner attestation")
        else:
            if not all(
                (
                    self.approver_name,
                    self.decided_at,
                    self.rationale,
                    self.reviewed_record_sha256,
                )
            ):
                raise ValueError(
                    "Owner identity, date, rationale and reviewed record are required"
                )
            if (
                self.confirmation_status == "CONFIRMED"
                and not self.confirmation_reference
            ):
                raise ValueError(
                    "Confirmed decision needs an owner confirmation reference"
                )
            if self.confirmation_status == "PENDING" and self.confirmation_reference:
                raise ValueError(
                    "Unconfirmed decision cannot claim a confirmation reference"
                )
            if (
                self.decision == "APPROVE_WITHIN_SCOPE"
                and self.confirmation_status != "CONFIRMED"
            ):
                raise ValueError("Approval requires explicit owner confirmation")
        return self


def require_owner_approval(path: Path, kind: str, subject_sha256: str, use: str):
    record = OwnerDecision.model_validate_json(path.read_bytes())
    if (
        record.decision != "APPROVE_WITHIN_SCOPE"
        or record.confirmation_status != "CONFIRMED"
    ):
        raise PolicyError("owner_decision_not_approved")
    matching = [
        subject
        for subject in record.subjects
        if subject.kind == kind and subject.sha256 == subject_sha256
    ]
    if len(matching) != 1:
        raise PolicyError("owner_decision_subject_mismatch")
    subject = matching[0]
    if (
        use not in subject.permitted_uses
        or any(
            getattr(subject, field) != "PASS"
            for field in ("rights", "provenance", "copyright")
        )
        or (kind == "DATASET" and subject.privacy != "PASS")
        or subject.privacy == "UNRESOLVED"
    ):
        raise PolicyError("owner_decision_rights_or_scope_unresolved")
    return record
