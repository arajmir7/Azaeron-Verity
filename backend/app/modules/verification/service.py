"""Reject factual drift before invoking an independently approved semantic model."""

from collections import Counter
import json
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.aegiswrite.invariants import protected_spans
from app.modules.inference.gateway import AzaeronInferenceGateway, AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable

Outcome = Literal["VERIFIED", "VERIFIED_WITH_WARNINGS", "REJECTED", "UNAVAILABLE"]
QUALIFIERS = re.compile(
    r"\b(?:not|no|never|without|cannot|may|might|could|must|should|will|approximately|approximate|about|estimated|likely|possibly|only|unless|except|at least|at most)\b|n['’]t\b",
    re.I,
)
QUANTITIES = re.compile(
    r"(?<!\w)(?:[$€£₹]\s*)?[+-]?\d+(?:[.,]\d+)*(?:\s*(?:hundred|thousand|million|billion|trillion|percent|%|USD|EUR|GBP|INR|kg|mg|km|cm|mm|ml|litres?|meters?))?",
    re.I,
)
NAMES = re.compile(
    r"\b(?:[A-Z]{2,}[A-Za-z0-9]*|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*|[a-z]+[A-Z][A-Za-z]*)\b"
)
COMMON_STARTS = {
    "A",
    "An",
    "The",
    "This",
    "That",
    "These",
    "Those",
    "It",
    "We",
    "They",
    "He",
    "She",
    "I",
    "You",
    "In",
    "On",
    "At",
    "For",
    "To",
    "By",
    "With",
    "However",
    "Therefore",
    "Although",
    "If",
    "When",
    "As",
    "And",
    "But",
}


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Outcome
    deterministic_passed: bool
    semantic_checked: bool = False
    reasons: list[str] = Field(default_factory=list)
    verifier_model_id: str | None = None
    verifier_revision: str | None = None
    limitations: list[str] = Field(
        default_factory=lambda: [
            "Deterministic name extraction is conservative and is not comprehensive multilingual NER."
        ]
    )


class SemanticAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    equivalent: bool
    contradiction: bool
    unsupported_additions: bool
    uncertain: bool


def deterministic_reasons(
    original: str, candidate: str, locked_spans: list[tuple[int, int]] | None = None
) -> list[str]:
    reasons = []
    original_spans = protected_spans(original, locked_spans or ())
    protected = Counter((span.kind, span.value) for span in original_spans)
    candidate_spans = Counter(
        (span.kind, span.value) for span in protected_spans(candidate)
    )
    for (kind, value), count in protected.items():
        if kind == "locked":
            if candidate.count(value) != original.count(value):
                reasons.append("locked_text_changed")
        elif candidate_spans[(kind, value)] != count:
            reasons.append(f"protected_{kind}_changed")
    for label, pattern in (
        ("negation_or_qualifier", QUALIFIERS),
        ("quantity", QUANTITIES),
    ):
        if Counter(m.group().casefold() for m in pattern.finditer(original)) != Counter(
            m.group().casefold() for m in pattern.finditer(candidate)
        ):
            reasons.append(label + "_changed")
    names = Counter(
        m.group() for m in NAMES.finditer(original) if m.group() not in COMMON_STARTS
    )
    candidate_names = Counter(
        m.group() for m in NAMES.finditer(candidate) if m.group() not in COMMON_STARTS
    )
    if names != candidate_names:
        reasons.append("possible_named_entity_changed")
    return sorted(set(reasons))


async def verify_text(
    original: str,
    candidate: str,
    *,
    operation_id: UUID,
    organization_id: UUID,
    user_id: UUID,
    locked_spans: list[tuple[int, int]] | None = None,
    gateway: AzaeronInferenceGateway | None = None,
    writing_model_id: str | None = None,
    writing_model_revision: str | None = None,
) -> VerificationResult:
    reasons = deterministic_reasons(original, candidate, locked_spans)
    if reasons:
        return VerificationResult(
            outcome="REJECTED", deterministic_passed=False, reasons=reasons
        )
    if original == candidate:
        return VerificationResult(
            outcome="VERIFIED",
            deterministic_passed=True,
            reasons=["identical_text"],
            limitations=[],
        )
    if gateway is None:
        return VerificationResult(
            outcome="UNAVAILABLE",
            deterministic_passed=True,
            reasons=["independent_semantic_model_unavailable"],
        )
    try:
        verifier = gateway.router.route("verify")
        if (
            verifier.model_id == writing_model_id
            or verifier.revision == writing_model_revision
        ):
            raise InferenceUnavailable("independent_verifier_required")
        result = await gateway.run(
            AzaeronInferenceJob(
                operation_id=operation_id,
                organization_id=organization_id,
                user_id=user_id,
                task="verify",
                text=json.dumps(
                    {"original": original, "candidate": candidate}, ensure_ascii=False
                ),
                max_output_tokens=256,
            )
        )
        assessment = SemanticAssessment.model_validate_json(result.output)
    except (InferenceUnavailable, ValidationError, ValueError):
        return VerificationResult(
            outcome="UNAVAILABLE",
            deterministic_passed=True,
            reasons=["independent_semantic_verification_unavailable"],
        )
    outcome: Outcome = "VERIFIED"
    if (
        not assessment.equivalent
        or assessment.contradiction
        or assessment.unsupported_additions
    ):
        outcome = "REJECTED"
    elif assessment.uncertain:
        outcome = "VERIFIED_WITH_WARNINGS"
    return VerificationResult(
        outcome=outcome,
        deterministic_passed=True,
        semantic_checked=True,
        reasons=(
            ["semantic_uncertainty_requires_review"] if assessment.uncertain else []
        ),
        verifier_model_id=verifier.model_id,
        verifier_revision=verifier.revision,
    )
