"""Hash-bound owner decisions for production model and data admission.

The record is an internal attestation, never a substitute for third-party rights
or for independent model-quality review. Pending/rejected records grant nothing.
"""

from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, model_validator

from .policy import Digest, PolicyError, StrictModel, canonical

OWNER_GITHUB_LOGIN = "arajmir7"
OWNER_GITHUB_ID = 236520801
OWNER_NAME = "Ajmir Aribam"
CONFIRMATION_REPOSITORY = "arajmir7/Azaeron-Verity"
CONFIRMATION_PR = 2
QWEN_BASE_SHA256 = "19fe23dd9302d4cb73e8cf9866f42b6a73399c9ec9398c28a340cda1acf1b8ce"
QWEN_BASE_PACKET_SHA256 = (
    "eb6f3f0615628abedd9baecd5eab2b5595e1841f844157e35a8449963c6a2314"
)
CONFIRMATION_REFERENCE = re.compile(
    r"github-issue-comment:([1-9][0-9]*):sha256:([a-f0-9]{64})"
)


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
            if self.confirmation_status == "CONFIRMED" and (
                not self.confirmation_reference
                or not self.confirmation_reference.strip()
                or "insert actual" in self.confirmation_reference.casefold()
                or self.confirmation_reference.strip().casefold()
                in {"pending", "tbd", "placeholder"}
            ):
                raise ValueError(
                    "Confirmed decision needs a non-placeholder owner confirmation reference"
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


def _fetch_confirmation(comment_id: int) -> dict:
    """Read the fixed GitHub approval surface; no user-supplied URL or redirect."""
    connection = http.client.HTTPSConnection("api.github.com", timeout=10)
    try:
        connection.request(
            "GET",
            f"/repos/{CONFIRMATION_REPOSITORY}/issues/comments/{comment_id}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "azaeron-verity-owner-admission/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise PolicyError("owner_confirmation_lookup_failed")
        body = response.read(65_537)
        if len(body) > 65_536:
            raise PolicyError("owner_confirmation_response_too_large")
        value = json.loads(body)
        if not isinstance(value, dict):
            raise PolicyError("owner_confirmation_invalid_response")
        return value
    except (OSError, http.client.HTTPException, UnicodeError, ValueError) as exc:
        raise PolicyError("owner_confirmation_lookup_failed") from exc
    finally:
        connection.close()


def _confirmation_body(
    record: OwnerDecision, subject: ReviewedSubject, use: str
) -> str:
    first = [
        "AZAERON_OWNER_CONFIRMATION_V1",
        "Decision: APPROVE_WITHIN_SCOPE",
        f"Packet-SHA256: {record.reviewed_record_sha256}",
    ]
    if (
        subject.kind == "BASE_MODEL"
        and subject.sha256 == QWEN_BASE_SHA256
        and record.reviewed_record_sha256 == QWEN_BASE_PACKET_SHA256
        and use == "commercial_derivative_training"
    ):
        return "\n".join(
            [
                *first,
                f"Candidate-SHA256: {subject.sha256}",
                f"Permitted-use: {use}",
                "Scope: exact controlled third-party Qwen3-4B base only",
                "Excludes: dataset admission, human technical acceptance, production release",
            ]
        )
    return "\n".join(
        [
            *first,
            f"Subject-kind: {subject.kind}",
            f"Subject-SHA256: {subject.sha256}",
            f"Permitted-use: {use}",
            "Scope: exactly this reviewed subject and use only",
        ]
    )


def _verify_authenticated_confirmation(
    record: OwnerDecision, subject: ReviewedSubject, use: str
) -> None:
    if record.approver_name != OWNER_NAME or len(record.subjects) != 1:
        raise PolicyError("owner_confirmation_identity_or_scope_mismatch")
    pending = record.model_dump(mode="json")
    pending.update(
        decision="PENDING",
        approver_name=None,
        decided_at=None,
        rationale=None,
        reviewed_record_sha256=None,
        confirmation_status="PENDING",
        confirmation_reference=None,
    )
    pending_bytes = canonical(pending)
    if record.reviewed_record_sha256 not in {
        hashlib.sha256(pending_bytes).hexdigest(),
        hashlib.sha256(pending_bytes + b"\n").hexdigest(),
    }:
        raise PolicyError("owner_confirmation_packet_mismatch")
    reference = CONFIRMATION_REFERENCE.fullmatch(record.confirmation_reference or "")
    if reference is None:
        raise PolicyError("owner_confirmation_reference_invalid")
    comment_id, claimed_body_sha256 = int(reference[1]), reference[2]
    expected_body = _confirmation_body(record, subject, use)
    expected_body_sha256 = hashlib.sha256(expected_body.encode()).hexdigest()
    if claimed_body_sha256 != expected_body_sha256:
        raise PolicyError("owner_confirmation_body_hash_mismatch")
    comment = _fetch_confirmation(comment_id)
    user = comment.get("user")
    if (
        comment.get("id") != comment_id
        or comment.get("issue_url")
        != f"https://api.github.com/repos/{CONFIRMATION_REPOSITORY}/issues/{CONFIRMATION_PR}"
        or comment.get("html_url")
        != f"https://github.com/{CONFIRMATION_REPOSITORY}/pull/{CONFIRMATION_PR}#issuecomment-{comment_id}"
        or not isinstance(user, dict)
        or user.get("login") != OWNER_GITHUB_LOGIN
        or user.get("id") != OWNER_GITHUB_ID
        or user.get("type") != "User"
        or comment.get("author_association") != "OWNER"
        or not isinstance(comment.get("body"), str)
        or comment["body"].strip() != expected_body
        or not comment.get("created_at")
        or comment.get("updated_at") != comment.get("created_at")
    ):
        raise PolicyError("owner_confirmation_comment_mismatch")


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
    _verify_authenticated_confirmation(record, subject, use)
    return record
