"""Offline candidate admission. Legal attestations must come from the operator.

Admission is permission to experiment, never approval to serve customers. No
download path exists here. The complete copied bundle is checked before use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import shutil
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from .owner_decision import (
    CONFIRMATION_PR,
    CONFIRMATION_REFERENCE,
    CONFIRMATION_REPOSITORY,
    OWNER_GITHUB_ID,
    OWNER_GITHUB_LOGIN,
    _fetch_confirmation as _fetch_technical_comment,
    require_owner_approval,
)
from .policy import (
    Digest,
    FileRef,
    PolicyError,
    StrictModel,
    canonical,
    digest,
    local_file,
)


class Candidate(StrictModel):
    schema_version: Literal[1] = 1
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    repository: str = Field(min_length=3)
    revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    artifacts: dict[str, Digest] = Field(min_length=4)
    weights: list[str] = Field(min_length=1)
    tokenizer: list[str] = Field(min_length=1)
    license_file: str
    model_card: str
    license: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    parameters: int = Field(gt=0)
    context: int = Field(ge=32, le=2_000_000)
    languages: list[str] = Field(min_length=1)
    runtime_compatibility: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def inventory(self):
        required = {
            *self.weights,
            *self.tokenizer,
            self.license_file,
            self.model_card,
            "config.json",
        }
        if not required <= self.artifacts.keys() or any(
            not name.endswith(".safetensors") for name in self.weights
        ):
            raise ValueError(
                "Complete safe-tensor weights and tokenizer lineage required"
            )
        if {n for n in self.artifacts if n.endswith(".safetensors")} != set(
            self.weights
        ):
            raise ValueError("Every weight file must be declared")
        if (
            "chat_template.jinja" in self.artifacts
            and "chat_template.jinja" not in self.tokenizer
        ):
            raise ValueError("Chat template must be part of tokenizer lineage")
        for name in self.artifacts:
            local_file(Path("."), name)
            if (
                Path(name).suffix.lower()
                not in {".json", ".safetensors", ".model", ".txt", ".md", ".tiktoken"}
                and name != "LICENSE"
                and name != "chat_template.jinja"
            ):
                raise ValueError("Unsupported artifact type")
        return self


class CandidateReview(StrictModel):
    subject_sha256: Digest
    purpose: Literal["PRODUCTION", "TEST_ONLY"]
    reviewer: str = Field(min_length=1)
    reviewer_kind: Literal["HUMAN", "TEST_FIXTURE"]
    reviewed_at: str = Field(min_length=10)
    reference: str = Field(min_length=1)
    license: str = Field(min_length=1)
    commercial_use: Literal["PASS"]
    commercial_training: Literal["PASS"]
    redistribution_requirements: str = Field(min_length=1)
    attribution_requirements: str = Field(min_length=1)
    acceptable_use_restrictions: str = Field(min_length=1)
    technical_review: Literal["PASS"]
    technical_acceptance: FileRef | None = None
    owner_decision: FileRef | None = None
    strong_baseline: bool = False
    strong_baseline_evidence: str | None = None

    @model_validator(mode="after")
    def human_attestation(self):
        if self.purpose == "PRODUCTION" and self.reviewer_kind != "HUMAN":
            raise ValueError("Production review requires an accountable human reviewer")
        if self.purpose == "PRODUCTION" and self.owner_decision is None:
            raise ValueError(
                "Production review requires a bound project-owner decision"
            )
        if self.purpose == "PRODUCTION" and self.technical_acceptance is None:
            raise ValueError(
                "Production review requires independent technical acceptance"
            )
        if self.owner_decision and self.owner_decision.path != "owner-decision.json":
            raise ValueError("Owner decision must be the adjacent owner-decision.json")
        if (
            self.technical_acceptance
            and self.technical_acceptance.path != "technical-acceptance.json"
        ):
            raise ValueError(
                "Technical acceptance must be the adjacent technical-acceptance.json"
            )
        if self.strong_baseline and not self.strong_baseline_evidence:
            raise ValueError("A strong-baseline claim needs evidence")
        return self


class TechnicalAcceptance(StrictModel):
    """A separate human's authenticated decision on the exact base and report."""

    candidate_sha256: Digest
    evidence: FileRef
    reviewer_github_login: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    reviewer_github_id: int = Field(gt=0)
    decision: Literal["PASS"]
    confirmation_reference: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_location(self):
        if self.evidence.path != "technical-evidence.json":
            raise ValueError("Technical evidence must be adjacent")
        return self


class TechnicalProtocol(StrictModel):
    """Declared limits for a bounded comparison on the exact base candidate."""

    candidate_sha256: Digest
    baseline_id: str = Field(min_length=3)
    score_definition: str = Field(min_length=20)
    fixtures: FileRef
    scoring_rule: Literal["exact_or_invariants_v1"]
    task_cases_min: int = Field(ge=32, le=4096)
    mean_score_drop_max: float = Field(ge=0, le=0.1, allow_inf_nan=False)
    stopping_cases_min: int = Field(ge=8, le=4096)
    stopping_violations_max: Literal[0]
    reasoning_leaks_max: Literal[0]
    peak_memory_gib_max: float = Field(gt=0, le=256, allow_inf_nan=False)
    context_tokens_min: int = Field(ge=64)

    @model_validator(mode="after")
    def fixture_location(self):
        if self.fixtures.path != "technical-fixtures.json":
            raise ValueError("Technical fixtures must be adjacent")
        return self


class TechnicalFixtureTask(StrictModel):
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    kind: Literal["exact", "invariants"]
    expected: str | None = None
    required: list[str] | None = None
    forbidden: list[str] | None = None

    @model_validator(mode="after")
    def adjudication(self):
        if self.kind == "exact":
            if (
                not self.expected
                or self.required is not None
                or self.forbidden is not None
            ):
                raise ValueError("Exact task needs only an expected answer")
        elif (
            self.expected is not None
            or not self.required
            or self.forbidden is None
            or any(not marker for marker in self.required + self.forbidden)
        ):
            raise ValueError("Invariant task needs required and forbidden markers")
        return self


class TechnicalFixtureStopping(StrictModel):
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class TechnicalFixtureResource(StrictModel):
    id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    minimum_tokens: int = Field(gt=0)


class TechnicalFixtures(StrictModel):
    tasks: list[TechnicalFixtureTask] = Field(min_length=32, max_length=4096)
    stopping: list[TechnicalFixtureStopping] = Field(min_length=8, max_length=4096)
    resources: list[TechnicalFixtureResource] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def unique_case_ids(self):
        ids = [
            case.id
            for cases in (self.tasks, self.stopping, self.resources)
            for case in cases
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Technical fixture IDs must be unique")
        prompts = [
            re.sub(r"\s+", " ", case.prompt).strip().casefold()
            for cases in (self.tasks, self.stopping, self.resources)
            for case in cases
        ]
        if len(prompts) != len(set(prompts)):
            raise ValueError("Technical fixture prompts must be unique")
        return self


class TechnicalTaskCase(StrictModel):
    id: str = Field(min_length=1)
    prompt_sha256: Digest
    baseline_response_sha256: Digest
    candidate_response_sha256: Digest
    baseline_response: str
    candidate_response: str
    reasoning_visible: StrictBool
    baseline_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    candidate_score: float = Field(ge=0, le=1, allow_inf_nan=False)


class TechnicalStoppingCase(StrictModel):
    id: str = Field(min_length=1)
    prompt_sha256: Digest
    response_sha256: Digest
    response: str
    finish_reason: Literal["stop", "eos", "length", "error"]
    reasoning_visible: StrictBool
    expected_exact_match: StrictBool


class TechnicalResourceCase(StrictModel):
    id: str = Field(min_length=1)
    prompt_sha256: Digest
    response_sha256: Digest
    response: str
    input_tokens: int = Field(gt=0)
    peak_memory_gib: float = Field(ge=0, allow_inf_nan=False)
    finish_reason: Literal["stop", "eos", "length", "error"]
    reasoning_visible: StrictBool
    success: StrictBool


class TechnicalRawResults(StrictModel):
    candidate_sha256: Digest
    protocol_sha256: Digest
    fixtures_sha256: Digest
    baseline_id: str = Field(min_length=3)
    upstream_revision: str = Field(pattern=r"^[a-f0-9]{40,64}$")
    artifact_hashes: dict[str, Digest] = Field(min_length=4)
    source_checkpoint_verified: Literal[True]
    tokenizer_verified: Literal[True]
    runtime_conversion_verified: Literal[True]
    tasks: list[TechnicalTaskCase] = Field(min_length=32, max_length=4096)
    stopping: list[TechnicalStoppingCase] = Field(min_length=8, max_length=4096)
    resources: list[TechnicalResourceCase] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def unique_case_ids(self):
        ids = [
            case.id
            for cases in (self.tasks, self.stopping, self.resources)
            for case in cases
        ]
        if len(ids) != len(set(ids)):
            raise ValueError("Technical case IDs must be unique")
        return self


class TechnicalExecution(StrictModel):
    candidate_sha256: Digest
    protocol_sha256: Digest
    raw_results: FileRef
    task_cases: int = Field(ge=32)
    stopping_cases: int = Field(ge=8)
    baseline_mean_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    candidate_mean_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    stopping_violations: int = Field(ge=0)
    reasoning_leaks: int = Field(ge=0)
    peak_memory_gib: float = Field(ge=0, allow_inf_nan=False)
    tested_context_tokens: int = Field(gt=0)

    @model_validator(mode="after")
    def raw_results_location(self):
        if self.raw_results.path != "technical-raw-results.json":
            raise ValueError("Raw technical results must be adjacent")
        return self


class TechnicalEvidence(StrictModel):
    """Human-reviewed scope and hashes for protocol and executed results."""

    candidate_sha256: Digest
    status: Literal["PASS"]
    protocol: FileRef
    execution: FileRef
    known_limitations: list[str] = Field(min_length=1)
    reviewer_rationale: str = Field(min_length=40)

    @model_validator(mode="after")
    def adjacent_evidence(self):
        if (
            self.protocol.path != "technical-protocol.json"
            or self.execution.path != "technical-execution.json"
            or any(not item.strip() for item in self.known_limitations)
        ):
            raise ValueError("Technical report needs adjacent evidence and limitations")
        return self


def _technical_confirmation_body(candidate_sha256: str, evidence_sha256: str) -> str:
    return "\n".join(
        [
            "AZAERON_TECHNICAL_ACCEPTANCE_V1",
            "Decision: PASS",
            f"Candidate-SHA256: {candidate_sha256}",
            f"Evidence-SHA256: {evidence_sha256}",
            "Scope: experimental base admission only; no production release",
        ]
    )


def _bounded_reference(root: Path, ref: FileRef, limit: int) -> Path:
    path = local_file(root, ref.path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PolicyError("technical_evidence_missing") from exc
    if size > limit:
        raise PolicyError("technical_evidence_too_large")
    return ref.verify(root)


def _technical_normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("\"'`").rstrip(". ")).casefold()


def _technical_reasoning_visible(value: str) -> bool:
    return bool(
        re.search(
            r"<\s*/?think\s*>|<\|im_start\|>assistant<\|meta_sep\|>analysis|"
            r"<\|channel\|>thought|<\|open\|>think<\|sep\|>",
            value,
            flags=re.I,
        )
    )


def _technical_score(fixture: TechnicalFixtureTask, response: str) -> float:
    if fixture.kind == "exact":
        return float(
            _technical_normalize(response)
            == _technical_normalize(fixture.expected or "")
        )
    return float(
        all(marker in response for marker in fixture.required or [])
        and all(marker not in response for marker in fixture.forbidden or [])
    )


def _technical_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_technical_acceptance(
    root: Path, review: CandidateReview, candidate: Candidate, candidate_sha256: str
) -> tuple[Path, ...]:
    """Refetch the non-owner reviewer decision; a local PASS is insufficient."""
    if review.technical_acceptance is None:
        raise PolicyError("independent_technical_acceptance_required")
    acceptance_path = _bounded_reference(root, review.technical_acceptance, 64 * 1024)
    acceptance = TechnicalAcceptance.model_validate_json(acceptance_path.read_bytes())
    if (
        acceptance.candidate_sha256 != candidate_sha256
        or acceptance.reviewer_github_id == OWNER_GITHUB_ID
        or acceptance.reviewer_github_login.casefold() == OWNER_GITHUB_LOGIN.casefold()
    ):
        raise PolicyError("technical_acceptance_subject_or_independence_mismatch")
    evidence_path = _bounded_reference(root, acceptance.evidence, 64 * 1024)
    evidence = TechnicalEvidence.model_validate_json(evidence_path.read_bytes())
    if evidence.candidate_sha256 != candidate_sha256:
        raise PolicyError("technical_evidence_subject_or_status_mismatch")
    protocol_path = _bounded_reference(root, evidence.protocol, 64 * 1024)
    protocol = TechnicalProtocol.model_validate_json(protocol_path.read_bytes())
    fixture_path = _bounded_reference(root, protocol.fixtures, 1024 * 1024)
    fixtures = TechnicalFixtures.model_validate_json(fixture_path.read_bytes())
    execution_path = _bounded_reference(root, evidence.execution, 64 * 1024)
    execution = TechnicalExecution.model_validate_json(execution_path.read_bytes())
    raw_path = _bounded_reference(root, execution.raw_results, 4 * 1024 * 1024)
    raw = TechnicalRawResults.model_validate_json(raw_path.read_bytes())
    if (
        protocol.candidate_sha256 != candidate_sha256
        or execution.candidate_sha256 != candidate_sha256
        or raw.candidate_sha256 != candidate_sha256
        or execution.protocol_sha256 != evidence.protocol.sha256
        or raw.protocol_sha256 != evidence.protocol.sha256
        or raw.fixtures_sha256 != protocol.fixtures.sha256
        or raw.baseline_id != protocol.baseline_id
        or raw.upstream_revision != candidate.revision
        or raw.artifact_hashes != candidate.artifacts
        or protocol.context_tokens_min > candidate.context
    ):
        raise PolicyError("technical_evidence_lineage_mismatch")
    if (
        len(raw.tasks) != len(fixtures.tasks)
        or len(raw.stopping) != len(fixtures.stopping)
        or len(raw.resources) != len(fixtures.resources)
    ):
        raise PolicyError("technical_fixture_count_mismatch")
    for task_fixture, task_case in zip(fixtures.tasks, raw.tasks, strict=True):
        if (
            task_case.id != task_fixture.id
            or task_case.prompt_sha256 != _technical_sha256(task_fixture.prompt)
            or task_case.baseline_response_sha256
            != _technical_sha256(task_case.baseline_response)
            or task_case.candidate_response_sha256
            != _technical_sha256(task_case.candidate_response)
        ):
            raise PolicyError("technical_task_binding_mismatch")
        if (
            task_case.baseline_score
            != _technical_score(task_fixture, task_case.baseline_response)
            or task_case.candidate_score
            != _technical_score(task_fixture, task_case.candidate_response)
            or task_case.reasoning_visible
            != _technical_reasoning_visible(task_case.candidate_response)
        ):
            raise PolicyError("technical_task_score_or_reasoning_mismatch")
    for stopping_fixture, stopping_case in zip(
        fixtures.stopping, raw.stopping, strict=True
    ):
        if (
            stopping_case.id != stopping_fixture.id
            or stopping_case.prompt_sha256 != _technical_sha256(stopping_fixture.prompt)
            or stopping_case.response_sha256
            != _technical_sha256(stopping_case.response)
        ):
            raise PolicyError("technical_stopping_binding_mismatch")
        if stopping_case.expected_exact_match != (
            _technical_normalize(stopping_case.response)
            == _technical_normalize(stopping_fixture.expected)
        ) or stopping_case.reasoning_visible != _technical_reasoning_visible(
            stopping_case.response
        ):
            raise PolicyError("technical_stopping_score_or_reasoning_mismatch")
    for resource_fixture, resource_case in zip(
        fixtures.resources, raw.resources, strict=True
    ):
        if (
            resource_case.id != resource_fixture.id
            or resource_case.prompt_sha256 != _technical_sha256(resource_fixture.prompt)
            or resource_case.response_sha256
            != _technical_sha256(resource_case.response)
        ):
            raise PolicyError("technical_resource_binding_mismatch")
        if resource_case.success != (
            resource_case.input_tokens >= resource_fixture.minimum_tokens
            and resource_case.finish_reason in {"stop", "eos"}
            and _technical_normalize(resource_case.response)
            == _technical_normalize(resource_fixture.expected)
        ) or resource_case.reasoning_visible != _technical_reasoning_visible(
            resource_case.response
        ):
            raise PolicyError("technical_resource_score_or_reasoning_mismatch")
    baseline_mean = sum(case.baseline_score for case in raw.tasks) / len(raw.tasks)
    candidate_mean = sum(case.candidate_score for case in raw.tasks) / len(raw.tasks)
    stopping_violations = sum(
        case.finish_reason not in {"stop", "eos"} or not case.expected_exact_match
        for case in raw.stopping
    )
    reasoning_leaks = sum(
        case.reasoning_visible
        for cases in (raw.tasks, raw.stopping, raw.resources)
        for case in cases
    )
    peak_memory = max(case.peak_memory_gib for case in raw.resources)
    tested_context = max(case.input_tokens for case in raw.resources)
    if (
        execution.task_cases != len(raw.tasks)
        or execution.stopping_cases != len(raw.stopping)
        or not math.isclose(execution.baseline_mean_score, baseline_mean, abs_tol=1e-6)
        or not math.isclose(
            execution.candidate_mean_score, candidate_mean, abs_tol=1e-6
        )
        or execution.stopping_violations != stopping_violations
        or execution.reasoning_leaks != reasoning_leaks
        or not math.isclose(execution.peak_memory_gib, peak_memory, abs_tol=1e-6)
        or execution.tested_context_tokens != tested_context
    ):
        raise PolicyError("technical_execution_summary_mismatch")
    if (
        len(raw.tasks) < protocol.task_cases_min
        or baseline_mean - candidate_mean > protocol.mean_score_drop_max
        or len(raw.stopping) < protocol.stopping_cases_min
        or stopping_violations > protocol.stopping_violations_max
        or reasoning_leaks > protocol.reasoning_leaks_max
        or any(not case.success for case in raw.resources)
        or peak_memory > protocol.peak_memory_gib_max
        or tested_context < protocol.context_tokens_min
        or tested_context > candidate.context
    ):
        raise PolicyError("technical_protocol_threshold_failed")
    reference = CONFIRMATION_REFERENCE.fullmatch(acceptance.confirmation_reference)
    if reference is None:
        raise PolicyError("technical_confirmation_reference_invalid")
    comment_id, claimed_body_sha256 = int(reference[1]), reference[2]
    expected_body = _technical_confirmation_body(
        candidate_sha256, acceptance.evidence.sha256
    )
    if claimed_body_sha256 != hashlib.sha256(expected_body.encode()).hexdigest():
        raise PolicyError("technical_confirmation_body_hash_mismatch")
    comment = _fetch_technical_comment(comment_id)
    user = comment.get("user")
    if (
        comment.get("id") != comment_id
        or comment.get("issue_url")
        != f"https://api.github.com/repos/{CONFIRMATION_REPOSITORY}/issues/{CONFIRMATION_PR}"
        or comment.get("html_url")
        != f"https://github.com/{CONFIRMATION_REPOSITORY}/pull/{CONFIRMATION_PR}#issuecomment-{comment_id}"
        or not isinstance(user, dict)
        or user.get("login") != acceptance.reviewer_github_login
        or user.get("id") != acceptance.reviewer_github_id
        or user.get("id") == OWNER_GITHUB_ID
        or user.get("type") != "User"
        or comment.get("author_association") not in {"COLLABORATOR", "MEMBER"}
        or not isinstance(comment.get("body"), str)
        or comment["body"].replace("\r\n", "\n") != expected_body
        or not comment.get("created_at")
        or comment.get("updated_at") != comment.get("created_at")
    ):
        raise PolicyError("technical_confirmation_comment_mismatch")
    return (
        acceptance_path,
        evidence_path,
        protocol_path,
        fixture_path,
        execution_path,
        raw_path,
    )


def inventory_hash(artifacts: dict[str, str]) -> str:
    return hashlib.sha256(canonical(artifacts)).hexdigest()


def verify_bundle(candidate: Candidate, root: Path):
    files = set()
    for path in root.rglob("*"):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            raise PolicyError("candidate_special_file")
        if path.is_file():
            files.add(path.relative_to(root).as_posix())
    if files != candidate.artifacts.keys():
        raise PolicyError("candidate_inventory_mismatch")
    for name, expected in candidate.artifacts.items():
        path = FileRef(path=name, sha256=expected).verify(root)
        if name in candidate.weights:
            # Validate the bounded safe-tensor container before ML code is imported.
            with path.open("rb") as stream:
                header_length = int.from_bytes(stream.read(8), "little")
                if not 2 <= header_length <= min(16 * 1024**2, path.stat().st_size - 8):
                    raise PolicyError("invalid_safetensors_header")
                header = json.loads(stream.read(header_length))
            sizes = {
                "F64": 8,
                "F32": 4,
                "F16": 2,
                "BF16": 2,
                "I64": 8,
                "I32": 4,
                "I16": 2,
                "I8": 1,
                "U32": 4,  # MLX 4-bit packs quantized weights into unsigned words.
                "U8": 1,
                "BOOL": 1,
            }
            intervals = []
            for key, value in header.items():
                if key == "__metadata__":
                    continue
                shape, offsets = value.get("shape", []), value.get("data_offsets", [])
                if (
                    value.get("dtype") not in sizes
                    or len(offsets) != 2
                    or any(type(v) is not int or v < 0 for v in [*shape, *offsets])
                ):
                    raise PolicyError("invalid_safetensors_layout")
                count = math.prod(shape)
                if (
                    count > candidate.parameters * 2
                    or offsets[1] - offsets[0] != count * sizes[value["dtype"]]
                ):
                    raise PolicyError("invalid_safetensors_shape")
                intervals.append(offsets)
            end = 0
            for start, stop in sorted(intervals):
                if start != end:
                    raise PolicyError("invalid_safetensors_offsets")
                end = stop
            if not intervals or end != path.stat().st_size - 8 - header_length:
                raise PolicyError("invalid_safetensors_payload")
        if name not in candidate.weights and path.stat().st_size > 64 * 1024**2:
            raise PolicyError("candidate_metadata_too_large")
        if name == "chat_template.jinja":
            if path.stat().st_size > 64 * 1024:
                raise PolicyError("candidate_chat_template_too_large")
            try:
                template = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise PolicyError("candidate_chat_template_not_utf8") from exc
            if not template or "\x00" in template:
                raise PolicyError("candidate_chat_template_invalid")
        if path.suffix == ".json":
            value = json.loads(path.read_bytes())

            def inspect(item):
                if isinstance(item, dict):
                    if "auto_map" in item or item.get("trust_remote_code"):
                        raise PolicyError("candidate_remote_code_prohibited")
                    for child in item.values():
                        inspect(child)
                elif isinstance(item, list):
                    for child in item:
                        inspect(child)

            inspect(value)
    config = json.loads((root / "config.json").read_bytes())
    for names, bound in [
        (("num_hidden_layers", "n_layer"), 128),
        (("hidden_size", "n_embd"), 32768),
        (("num_attention_heads", "n_head"), 256),
        (("vocab_size",), 1_000_000),
    ]:
        value = next((config[key] for key in names if key in config), None)
        if type(value) is not int or not 0 < value <= bound:
            raise PolicyError("candidate_architecture_dimensions_invalid")
    if config.get("model_type") != candidate.architecture:
        raise PolicyError("candidate_architecture_mismatch")
    context = config.get("max_position_embeddings", config.get("n_positions"))
    if not isinstance(context, int) or candidate.context > context:
        raise PolicyError("candidate_context_mismatch")


def load_candidate(admitted: Path, *, smoke=False):
    candidate = Candidate.model_validate_json(
        (admitted / "candidate.json").read_bytes()
    )
    review = CandidateReview.model_validate_json(
        (admitted / "review.json").read_bytes()
    )
    record = json.loads((admitted / "admission.json").read_bytes())
    if record != {
        "status": "EXPERIMENTAL",
        "candidate_sha256": digest(admitted / "candidate.json"),
        "review_sha256": digest(admitted / "review.json"),
        "production_approved": False,
    }:
        raise PolicyError("admission_record_mismatch")
    if (
        review.subject_sha256 != digest(admitted / "candidate.json")
        or review.license != candidate.license
        or review.purpose != candidate.purpose
    ):
        raise PolicyError("candidate_review_binding_failed")
    if (candidate.purpose == "TEST_ONLY") != smoke:
        raise PolicyError("candidate_purpose_mismatch")
    if not smoke:
        if review.owner_decision is None:
            raise PolicyError("owner_candidate_decision_required")
        owner = require_owner_approval(
            review.owner_decision.verify(admitted),
            "BASE_MODEL",
            digest(admitted / "candidate.json"),
            "commercial_derivative_training",
        )
        if review.reviewer != owner.approver_name:
            raise PolicyError("candidate_reviewer_is_not_project_owner")
        require_technical_acceptance(
            admitted, review, candidate, digest(admitted / "candidate.json")
        )
    verify_bundle(candidate, admitted / "bundle")
    return candidate, review


def admit(
    manifest: Path, review_file: Path, source: Path, registry: Path, *, smoke=False
):
    candidate = Candidate.model_validate_json(manifest.read_bytes())
    review = CandidateReview.model_validate_json(review_file.read_bytes())
    if (
        review.subject_sha256 != digest(manifest)
        or review.license != candidate.license
        or review.purpose != candidate.purpose
    ):
        raise PolicyError("candidate_review_binding_failed")
    if (candidate.purpose == "TEST_ONLY") != smoke:
        raise PolicyError("candidate_purpose_mismatch")
    technical_paths: tuple[Path, ...] | None = None
    if not smoke:
        if review.owner_decision is None:
            raise PolicyError("owner_candidate_decision_required")
        owner = require_owner_approval(
            review.owner_decision.verify(review_file.parent),
            "BASE_MODEL",
            digest(manifest),
            "commercial_derivative_training",
        )
        if review.reviewer != owner.approver_name:
            raise PolicyError("candidate_reviewer_is_not_project_owner")
        technical_paths = require_technical_acceptance(
            review_file.parent, review, candidate, digest(manifest)
        )
    verify_bundle(candidate, source)
    output = registry / candidate.candidate_id / digest(manifest)
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source, output / "bundle", symlinks=True)
    shutil.copyfile(manifest, output / "candidate.json")
    shutil.copyfile(review_file, output / "review.json")
    if not smoke:
        if review.owner_decision is None:
            raise PolicyError("owner_candidate_decision_required")
        shutil.copyfile(
            review.owner_decision.verify(review_file.parent),
            output / review.owner_decision.path,
        )
        if technical_paths is None:
            raise PolicyError("independent_technical_acceptance_required")
        for technical_path in technical_paths:
            shutil.copyfile(technical_path, output / technical_path.name)
    (output / "admission.json").write_bytes(
        canonical(
            {
                "status": "EXPERIMENTAL",
                "candidate_sha256": digest(manifest),
                "review_sha256": digest(review_file),
                "production_approved": False,
            }
        )
        + b"\n"
    )
    load_candidate(output, smoke=smoke)
    # Hash checks remain mandatory: filesystem permissions alone are not a trust boundary.
    for path in output.rglob("*"):
        path.chmod(0o555 if path.is_dir() else 0o444)
    output.chmod(0o555)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["manifest", "review", "source", "registry"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(
        admit(args.manifest, args.review, args.source, args.registry, smoke=args.smoke)
    )


if __name__ == "__main__":
    main()
