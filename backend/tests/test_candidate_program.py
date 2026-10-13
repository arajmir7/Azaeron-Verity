"""Admission, leakage, compute and release attacks; no production model fixtures."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from app.modules.model_platform.admission import (
    Candidate,
    CandidateReview,
    TechnicalEvidence,
    admit,
    load_candidate,
    require_technical_acceptance,
    verify_bundle,
)
from app.modules.model_platform import admission as base_admission
from app.modules.model_platform.datasets import (
    Dataset,
    DatasetReview,
    read_dataset,
    register,
    review_subject,
    Example,
    LeakageIndex,
)
from app.modules.model_platform.derivative import DerivativeConfig
from app.modules.model_platform.detector_metrics import (
    detector_report,
    operating_thresholds,
)
from app.modules.model_platform.hardware import enforce, plan
from app.modules.model_platform.owner_decision import (
    OwnerDecision,
    ReviewedSubject,
    require_owner_approval,
)
from app.modules.model_platform import owner_decision as approval
from app.modules.model_platform.policy import FileRef, PolicyError, canonical, digest
from app.modules.model_platform.release import promote
from app.modules.model_platform.human_review import writer_review
from app.modules.inference.registry import AzaeronModelRegistry
from tests.test_private_inference import approved_model


def candidate_fixture(root):
    root.mkdir()
    header = canonical(
        {"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}
    )
    (root / "model.safetensors").write_bytes(
        len(header).to_bytes(8, "little") + header + b"\x00" * 4
    )
    (root / "config.json").write_bytes(
        canonical(
            {
                "model_type": "gpt2",
                "n_positions": 64,
                "n_layer": 1,
                "n_embd": 16,
                "n_head": 2,
                "vocab_size": 8,
            }
        )
    )
    (root / "tokenizer.json").write_text("{}")
    (root / "LICENSE").write_text("TEST_ONLY")
    (root / "README.md").write_text("TEST_ONLY")
    return Candidate(
        candidate_id="fixture",
        purpose="TEST_ONLY",
        repository="local/fixture",
        revision="a" * 40,
        artifacts={p.name: digest(p) for p in root.iterdir()},
        weights=["model.safetensors"],
        tokenizer=["tokenizer.json"],
        license_file="LICENSE",
        model_card="README.md",
        license="TEST_ONLY",
        architecture="gpt2",
        parameters=1,
        context=64,
        languages=["fixture"],
        runtime_compatibility=["fixture"],
    )


def technical_fixture(root, candidate, candidate_sha256):
    fixture_file = root / "technical-fixtures.json"
    fixture_file.write_bytes(
        canonical(
            {
                "tasks": [
                    {
                        "id": f"task-{i}",
                        "prompt": f"prompt-{i}",
                        "kind": "exact",
                        "expected": f"answer-{i}",
                    }
                    for i in range(32)
                ],
                "stopping": [
                    {
                        "id": f"stop-{i}",
                        "prompt": f"stop-{i}",
                        "expected": f"response-{i}",
                    }
                    for i in range(8)
                ],
                "resources": [
                    {
                        "id": "resource-1",
                        "prompt": "resource-prompt",
                        "expected": "resource-response",
                        "minimum_tokens": 64,
                    }
                ],
            }
        )
    )
    protocol_file = root / "technical-protocol.json"
    protocol_file.write_bytes(
        canonical(
            {
                "candidate_sha256": candidate_sha256,
                "baseline_id": "fixture-bf16",
                "score_definition": "Exact fixture task score from 0 to 1",
                "fixtures": {
                    "path": fixture_file.name,
                    "sha256": digest(fixture_file),
                },
                "scoring_rule": "exact_or_invariants_v1",
                "task_cases_min": 32,
                "mean_score_drop_max": 0.05,
                "stopping_cases_min": 8,
                "stopping_violations_max": 0,
                "reasoning_leaks_max": 0,
                "peak_memory_gib_max": 2.0,
                "context_tokens_min": 64,
            }
        )
    )
    raw_file = root / "technical-raw-results.json"
    raw_file.write_bytes(
        canonical(
            {
                "candidate_sha256": candidate_sha256,
                "protocol_sha256": digest(protocol_file),
                "fixtures_sha256": digest(fixture_file),
                "baseline_id": "fixture-bf16",
                "upstream_revision": candidate.revision,
                "artifact_hashes": candidate.artifacts,
                "source_checkpoint_verified": True,
                "tokenizer_verified": True,
                "runtime_conversion_verified": True,
                "tasks": [
                    {
                        "id": f"task-{i}",
                        "prompt_sha256": hashlib.sha256(
                            f"prompt-{i}".encode()
                        ).hexdigest(),
                        "baseline_response_sha256": hashlib.sha256(
                            f"answer-{i}".encode()
                        ).hexdigest(),
                        "candidate_response_sha256": hashlib.sha256(
                            f"answer-{i}".encode()
                        ).hexdigest(),
                        "baseline_response": f"answer-{i}",
                        "candidate_response": f"answer-{i}",
                        "reasoning_visible": False,
                        "baseline_score": 1.0,
                        "candidate_score": 1.0,
                    }
                    for i in range(32)
                ],
                "stopping": [
                    {
                        "id": f"stop-{i}",
                        "prompt_sha256": hashlib.sha256(
                            f"stop-{i}".encode()
                        ).hexdigest(),
                        "response_sha256": hashlib.sha256(
                            f"response-{i}".encode()
                        ).hexdigest(),
                        "response": f"response-{i}",
                        "finish_reason": "stop",
                        "reasoning_visible": False,
                        "expected_exact_match": True,
                    }
                    for i in range(8)
                ],
                "resources": [
                    {
                        "id": "resource-1",
                        "prompt_sha256": hashlib.sha256(b"resource-prompt").hexdigest(),
                        "response_sha256": hashlib.sha256(
                            b"resource-response"
                        ).hexdigest(),
                        "response": "resource-response",
                        "input_tokens": 64,
                        "peak_memory_gib": 1.0,
                        "finish_reason": "stop",
                        "reasoning_visible": False,
                        "success": True,
                    }
                ],
            }
        )
    )
    execution_file = root / "technical-execution.json"
    execution_file.write_bytes(
        canonical(
            {
                "candidate_sha256": candidate_sha256,
                "protocol_sha256": digest(protocol_file),
                "raw_results": {"path": raw_file.name, "sha256": digest(raw_file)},
                "task_cases": 32,
                "stopping_cases": 8,
                "baseline_mean_score": 1.0,
                "candidate_mean_score": 1.0,
                "stopping_violations": 0,
                "reasoning_leaks": 0,
                "peak_memory_gib": 1.0,
                "tested_context_tokens": 64,
            }
        )
    )
    evidence_file = root / "technical-evidence.json"
    evidence_file.write_bytes(
        canonical(
            {
                "candidate_sha256": candidate_sha256,
                "status": "PASS",
                "protocol": {
                    "path": protocol_file.name,
                    "sha256": digest(protocol_file),
                },
                "execution": {
                    "path": execution_file.name,
                    "sha256": digest(execution_file),
                },
                "known_limitations": [
                    "Synthetic test fixture; not a product quality claim"
                ],
                "reviewer_rationale": "Fixture-only independent review of all declared technical checks.",
            }
        )
    )
    body = base_admission._technical_confirmation_body(
        candidate_sha256, digest(evidence_file)
    )
    acceptance_file = root / "technical-acceptance.json"
    acceptance_file.write_bytes(
        canonical(
            {
                "candidate_sha256": candidate_sha256,
                "evidence": {
                    "path": evidence_file.name,
                    "sha256": digest(evidence_file),
                },
                "reviewer_github_login": "independent-fixture",
                "reviewer_github_id": 123456,
                "decision": "PASS",
                "confirmation_reference": "github-issue-comment:123:sha256:"
                + hashlib.sha256(body.encode()).hexdigest(),
            }
        )
    )
    return {
        "fixtures": fixture_file,
        "protocol": protocol_file,
        "raw": raw_file,
        "execution": execution_file,
        "evidence": evidence_file,
        "acceptance": acceptance_file,
        "body": body,
    }


def rebind_technical_fixture(files, candidate_sha256):
    protocol = json.loads(files["protocol"].read_bytes())
    protocol["fixtures"]["sha256"] = digest(files["fixtures"])
    files["protocol"].write_bytes(canonical(protocol))
    raw = json.loads(files["raw"].read_bytes())
    raw["protocol_sha256"] = digest(files["protocol"])
    raw["fixtures_sha256"] = digest(files["fixtures"])
    files["raw"].write_bytes(canonical(raw))
    execution = json.loads(files["execution"].read_bytes())
    execution["protocol_sha256"] = digest(files["protocol"])
    execution["raw_results"]["sha256"] = digest(files["raw"])
    files["execution"].write_bytes(canonical(execution))
    evidence = json.loads(files["evidence"].read_bytes())
    if "protocol" in evidence:
        evidence["protocol"]["sha256"] = digest(files["protocol"])
    if "execution" in evidence:
        evidence["execution"]["sha256"] = digest(files["execution"])
    files["evidence"].write_bytes(canonical(evidence))
    acceptance = json.loads(files["acceptance"].read_bytes())
    acceptance["evidence"]["sha256"] = digest(files["evidence"])
    body = base_admission._technical_confirmation_body(
        candidate_sha256, digest(files["evidence"])
    )
    acceptance["confirmation_reference"] = (
        "github-issue-comment:123:sha256:" + hashlib.sha256(body.encode()).hexdigest()
    )
    files["acceptance"].write_bytes(canonical(acceptance))
    files["body"] = body


@pytest.mark.parametrize("mutation", ["tamper", "extra", "remote", "symlink", "header"])
def test_candidate_inventory_attacks(tmp_path, mutation):
    root = tmp_path / "source"
    model = candidate_fixture(root)
    verify_bundle(model, root)
    if mutation == "tamper":
        (root / "LICENSE").write_text("changed")
    elif mutation == "extra":
        (root / "evil.py").write_text("pass")
    elif mutation == "symlink":
        (root / "tokenizer.json").unlink()
        (root / "tokenizer.json").symlink_to(root / "config.json")
    else:
        if mutation == "remote":
            data = json.loads((root / "config.json").read_bytes())
            data["auto_map"] = {"AutoModel": "evil.Model"}
            (root / "config.json").write_bytes(canonical(data))
        else:
            (root / "model.safetensors").write_bytes((2**62).to_bytes(8, "little"))
        model = model.model_copy(
            update={"artifacts": {p.name: digest(p) for p in root.iterdir()}}
        )
    with pytest.raises(PolicyError):
        verify_bundle(model, root)


def test_hash_bound_chat_template_is_tokenizer_lineage_only(tmp_path):
    root = tmp_path / "source"
    fixture = candidate_fixture(root)
    template = root / "chat_template.jinja"
    template.write_text("{{ messages[0].content }}", encoding="utf-8")
    manifest = fixture.model_dump()
    manifest["artifacts"][template.name] = digest(template)

    with pytest.raises(ValidationError):
        Candidate.model_validate(manifest)

    manifest["tokenizer"].append(template.name)
    candidate = Candidate.model_validate(manifest)
    verify_bundle(candidate, root)

    template.write_text("{{ messages[0].role }}", encoding="utf-8")
    with pytest.raises(PolicyError, match="artifact_hash_mismatch"):
        verify_bundle(candidate, root)

    for payload, reason in (
        (b"x" * (64 * 1024 + 1), "candidate_chat_template_too_large"),
        (b"\xff", "candidate_chat_template_not_utf8"),
        (b"hello\x00world", "candidate_chat_template_invalid"),
    ):
        template.write_bytes(payload)
        manifest["artifacts"][template.name] = digest(template)
        with pytest.raises(PolicyError, match=reason):
            verify_bundle(Candidate.model_validate(manifest), root)

    template.rename(root / "other_template.jinja")
    manifest["artifacts"] = {
        name if name != template.name else "other_template.jinja": value
        for name, value in manifest["artifacts"].items()
    }
    manifest["tokenizer"] = [
        name if name != template.name else "other_template.jinja"
        for name in manifest["tokenizer"]
    ]
    with pytest.raises(ValidationError):
        Candidate.model_validate(manifest)


def test_hash_bound_quantized_u32_weight_layout(tmp_path):
    root = tmp_path / "source"
    fixture = candidate_fixture(root)
    weight = root / "model.safetensors"
    header = canonical(
        {"weight": {"dtype": "U32", "shape": [1], "data_offsets": [0, 4]}}
    )
    weight.write_bytes(len(header).to_bytes(8, "little") + header + b"\x01\x00\x00\x00")
    manifest = fixture.model_dump()
    manifest["artifacts"][weight.name] = digest(weight)
    verify_bundle(Candidate.model_validate(manifest), root)

    broken = canonical(
        {"weight": {"dtype": "U32", "shape": [1], "data_offsets": [0, 3]}}
    )
    weight.write_bytes(len(broken).to_bytes(8, "little") + broken + b"\x01\x00\x00")
    manifest["artifacts"][weight.name] = digest(weight)
    with pytest.raises(PolicyError, match="invalid_safetensors_shape"):
        verify_bundle(Candidate.model_validate(manifest), root)


def test_floating_revision_and_fake_review_rejected(tmp_path):
    candidate = candidate_fixture(tmp_path / "source")
    with pytest.raises(ValidationError):
        Candidate.model_validate({**candidate.model_dump(), "revision": "main"})
    with pytest.raises(ValidationError):
        CandidateReview.model_validate({"commercial_use": "UNKNOWN"})


def test_owner_decision_is_exactly_bound_and_fail_closed(tmp_path, monkeypatch):
    subject = {
        "kind": "DATASET",
        "identifier": "fixture-only",
        "sha256": "a" * 64,
        "license": "TEST_ONLY",
        "rights": "UNRESOLVED",
        "provenance": "PASS",
        "copyright": "PASS",
        "privacy": "PASS",
        "permitted_uses": ["commercial_training"],
        "findings": ["TEST FIXTURE ONLY"],
        "evidence": ["TEST_FIXTURE_ONLY"],
        "risks": ["Unknown training rights"],
        "restrictions": [],
    }
    record = {
        "schema_version": 1,
        "subjects": [subject],
        "subject_sha256": hashlib.sha256(canonical([subject])).hexdigest(),
        "decision": "PENDING",
        "approver_role": "AZAERON_PROJECT_OWNER",
        "approver_name": None,
        "decided_at": None,
        "rationale": None,
    }
    path = tmp_path / "owner-decision.json"
    path.write_bytes(canonical(record))
    assert OwnerDecision.model_validate_json(path.read_bytes()).decision == "PENDING"
    pending_hash = digest(path)
    with pytest.raises(PolicyError, match="not_approved"):
        require_owner_approval(path, "DATASET", "a" * 64, "commercial_training")
    record.update(
        decision="REJECT",
        approver_name="TEST FIXTURE ONLY",
        decided_at="2026-10-11",
        rationale="TEST FIXTURE REJECTION",
        reviewed_record_sha256=pending_hash,
        confirmation_status="PENDING",
    )
    path.write_bytes(canonical(record))
    assert OwnerDecision.model_validate_json(path.read_bytes()).decision == "REJECT"
    with pytest.raises(PolicyError, match="not_approved"):
        require_owner_approval(path, "DATASET", "a" * 64, "commercial_training")
    record.update(
        decision="APPROVE_WITHIN_SCOPE",
        approver_name="TEST FIXTURE ONLY",
        decided_at="2026-10-11T00:00:00Z",
        rationale="TEST FIXTURE ONLY",
        reviewed_record_sha256=pending_hash,
    )
    path.write_bytes(canonical(record))
    with pytest.raises(ValidationError, match="explicit owner confirmation"):
        OwnerDecision.model_validate_json(path.read_bytes())
    record.update(
        confirmation_status="CONFIRMED",
        confirmation_reference="[Insert actual authenticated confirmation reference]",
    )
    path.write_bytes(canonical(record))
    with pytest.raises(ValidationError, match="non-placeholder"):
        OwnerDecision.model_validate_json(path.read_bytes())
    record["confirmation_reference"] = "TEST FIXTURE ONLY"
    path.write_bytes(canonical(record))
    with pytest.raises(PolicyError, match="unresolved"):
        require_owner_approval(path, "DATASET", "a" * 64, "commercial_training")
    subject["rights"] = "PASS"
    record["subject_sha256"] = hashlib.sha256(canonical([subject])).hexdigest()
    path.write_bytes(canonical(record))
    # The remaining checks exercise rights/scope after separately tested
    # account authentication; these are deliberately fixture decisions.
    monkeypatch.setattr(approval, "_verify_authenticated_confirmation", lambda *_: None)
    require_owner_approval(path, "DATASET", "a" * 64, "commercial_training")
    with pytest.raises(PolicyError, match="subject_mismatch"):
        require_owner_approval(path, "DATASET", "b" * 64, "commercial_training")
    with pytest.raises(PolicyError, match="scope_unresolved"):
        require_owner_approval(path, "DATASET", "a" * 64, "production_release")
    subject["rights"] = "UNRESOLVED"
    path.write_bytes(canonical(record))
    with pytest.raises(ValidationError, match="hash mismatch"):
        OwnerDecision.model_validate_json(path.read_bytes())


def test_candidate_admission_requires_the_same_explicit_owner(tmp_path, monkeypatch):
    source = tmp_path / "source"
    candidate = candidate_fixture(source).model_copy(update={"purpose": "PRODUCTION"})
    manifest = tmp_path / "candidate.json"
    manifest.write_bytes(canonical(candidate.model_dump(mode="json")))
    subject = {
        "kind": "BASE_MODEL",
        "identifier": "TEST FIXTURE ONLY",
        "sha256": digest(manifest),
        "license": "TEST_ONLY",
        "rights": "PASS",
        "provenance": "PASS",
        "copyright": "PASS",
        "privacy": "NOT_APPLICABLE",
        "permitted_uses": ["commercial_derivative_training"],
        "findings": ["TEST FIXTURE ONLY"],
        "evidence": ["TEST FIXTURE ONLY"],
        "risks": [],
        "restrictions": [],
    }
    decision = {
        "schema_version": 1,
        "subjects": [subject],
        "subject_sha256": hashlib.sha256(canonical([subject])).hexdigest(),
        "decision": "PENDING",
        "approver_role": "AZAERON_PROJECT_OWNER",
        "approver_name": None,
        "decided_at": None,
        "rationale": None,
    }
    owner_file = tmp_path / "owner-decision.json"
    owner_file.write_bytes(canonical(decision))
    pending_hash = digest(owner_file)
    technical_files = technical_fixture(tmp_path, candidate, digest(manifest))
    technical_body = technical_files["body"]
    technical_file = technical_files["acceptance"]
    review = {
        "subject_sha256": digest(manifest),
        "purpose": "PRODUCTION",
        "reviewer": "OTHER TEST FIXTURE",
        "reviewer_kind": "HUMAN",
        "reviewed_at": "2026-10-11",
        "reference": "TEST FIXTURE ONLY",
        "license": "TEST_ONLY",
        "commercial_use": "PASS",
        "commercial_training": "PASS",
        "redistribution_requirements": "TEST FIXTURE ONLY",
        "attribution_requirements": "TEST FIXTURE ONLY",
        "acceptable_use_restrictions": "TEST FIXTURE ONLY",
        "technical_review": "PASS",
        "technical_acceptance": {
            "path": technical_file.name,
            "sha256": digest(technical_file),
        },
        "owner_decision": {
            "path": owner_file.name,
            "sha256": digest(owner_file),
        },
    }
    review_file = tmp_path / "review.json"
    review_file.write_bytes(canonical(review))
    with pytest.raises(PolicyError, match="not_approved"):
        admit(manifest, review_file, source, tmp_path / "registry")
    decision.update(
        decision="APPROVE_WITHIN_SCOPE",
        approver_name="TEST FIXTURE OWNER",
        decided_at="2026-10-11T00:00:00Z",
        rationale="TEST FIXTURE ONLY",
        reviewed_record_sha256=pending_hash,
        confirmation_status="CONFIRMED",
        confirmation_reference="TEST FIXTURE ONLY",
    )
    owner_file.write_bytes(canonical(decision))
    review["owner_decision"]["sha256"] = digest(owner_file)
    review_file.write_bytes(canonical(review))
    monkeypatch.setattr(approval, "_verify_authenticated_confirmation", lambda *_: None)
    with pytest.raises(PolicyError, match="not_project_owner"):
        admit(manifest, review_file, source, tmp_path / "registry")
    review["reviewer"] = "TEST FIXTURE OWNER"
    review_file.write_bytes(canonical(review))
    monkeypatch.setattr(
        base_admission,
        "_fetch_technical_comment",
        lambda comment_id: {
            "id": comment_id,
            "issue_url": "https://api.github.com/repos/arajmir7/Azaeron-Verity/issues/2",
            "html_url": "https://github.com/arajmir7/Azaeron-Verity/pull/2#issuecomment-123",
            "user": {
                "login": "independent-fixture",
                "id": 123456,
                "type": "User",
            },
            "author_association": "COLLABORATOR",
            "body": technical_body,
            "created_at": "2026-10-12T10:00:00Z",
            "updated_at": "2026-10-12T10:00:00Z",
        },
    )
    admitted = admit(manifest, review_file, source, tmp_path / "registry")
    assert load_candidate(admitted)[0].purpose == "PRODUCTION"
    for name in ("evidence", "acceptance", "protocol", "fixtures", "execution", "raw"):
        file = technical_files[name]
        assert digest(admitted / file.name) == digest(file)
    assert (
        json.loads((admitted / "admission.json").read_bytes())["status"]
        == "EXPERIMENTAL"
    )
    monkeypatch.setattr(
        base_admission,
        "_fetch_technical_comment",
        lambda *_: (_ for _ in ()).throw(PolicyError("technical_lookup_unavailable")),
    )
    with pytest.raises(PolicyError, match="technical_lookup_unavailable"):
        load_candidate(admitted)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("accepted", None),
        ("wrong_candidate", "technical_acceptance_subject_or_independence_mismatch"),
        ("owner", "technical_acceptance_subject_or_independence_mismatch"),
        ("tampered_evidence", "artifact_hash_mismatch"),
        ("tampered_protocol", "artifact_hash_mismatch"),
        ("tampered_fixtures", "artifact_hash_mismatch"),
        ("missing_execution", "technical_evidence_missing"),
        ("oversized_raw", "technical_evidence_too_large"),
        ("unbound_protocol", "technical_evidence_lineage_mismatch"),
        ("unbound_artifact", "technical_evidence_lineage_mismatch"),
        ("failed_raw_stopping", "technical_protocol_threshold_failed"),
        ("wrong_stop_answer", "technical_protocol_threshold_failed"),
        ("forged_stop_match", "technical_stopping_score_or_reasoning_mismatch"),
        ("failed_task_quality", "technical_protocol_threshold_failed"),
        ("forged_task_score", "technical_task_score_or_reasoning_mismatch"),
        ("task_reasoning_leak", "technical_protocol_threshold_failed"),
        ("hidden_task_reasoning", "technical_task_score_or_reasoning_mismatch"),
        ("tampered_response", "technical_task_binding_mismatch"),
        ("resource_false_success", "technical_resource_score_or_reasoning_mismatch"),
        ("vacuous_threshold", "less than or equal to 0.1"),
        ("duplicate_case", "Technical case IDs must be unique"),
        ("mismatched_summary", "technical_execution_summary_mismatch"),
        ("content_free_evidence", "Field required"),
        ("content_free_raw", "Field required"),
        ("wrong_pr", "technical_confirmation_comment_mismatch"),
        ("wrong_author", "technical_confirmation_comment_mismatch"),
        ("bot", "technical_confirmation_comment_mismatch"),
        ("edited", "technical_confirmation_comment_mismatch"),
        ("wrong_body", "technical_confirmation_comment_mismatch"),
        ("wrong_reference_hash", "technical_confirmation_body_hash_mismatch"),
    ],
)
def test_independent_technical_acceptance_requires_authenticated_exact_evidence(
    tmp_path, monkeypatch, mutation, reason
):
    candidate_sha256 = "a" * 64
    candidate = candidate_fixture(tmp_path / "source")
    files = technical_fixture(tmp_path, candidate, candidate_sha256)
    acceptance = json.loads(files["acceptance"].read_bytes())
    if mutation == "wrong_candidate":
        acceptance["candidate_sha256"] = "b" * 64
    elif mutation == "owner":
        acceptance["reviewer_github_login"] = approval.OWNER_GITHUB_LOGIN
        acceptance["reviewer_github_id"] = approval.OWNER_GITHUB_ID
    elif mutation == "tampered_evidence":
        files["evidence"].write_bytes(b"changed")
    elif mutation == "tampered_protocol":
        files["protocol"].write_bytes(b"changed")
    elif mutation == "tampered_fixtures":
        files["fixtures"].write_bytes(b"changed")
    elif mutation == "missing_execution":
        files["execution"].unlink()
    elif mutation == "oversized_raw":
        files["raw"].write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    elif mutation == "unbound_protocol":
        protocol = json.loads(files["protocol"].read_bytes())
        protocol["candidate_sha256"] = "b" * 64
        files["protocol"].write_bytes(canonical(protocol))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "unbound_artifact":
        raw = json.loads(files["raw"].read_bytes())
        raw["artifact_hashes"]["tokenizer.json"] = "b" * 64
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "failed_raw_stopping":
        raw = json.loads(files["raw"].read_bytes())
        raw["stopping"][0]["finish_reason"] = "length"
        files["raw"].write_bytes(canonical(raw))
        execution = json.loads(files["execution"].read_bytes())
        execution["stopping_violations"] = 1
        files["execution"].write_bytes(canonical(execution))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "wrong_stop_answer":
        raw = json.loads(files["raw"].read_bytes())
        raw["stopping"][0]["response"] = "WRONG"
        raw["stopping"][0]["response_sha256"] = hashlib.sha256(b"WRONG").hexdigest()
        raw["stopping"][0]["expected_exact_match"] = False
        files["raw"].write_bytes(canonical(raw))
        execution = json.loads(files["execution"].read_bytes())
        execution["stopping_violations"] = 1
        files["execution"].write_bytes(canonical(execution))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "forged_stop_match":
        raw = json.loads(files["raw"].read_bytes())
        raw["stopping"][0]["response"] = "WRONG"
        raw["stopping"][0]["response_sha256"] = hashlib.sha256(b"WRONG").hexdigest()
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "failed_task_quality":
        raw = json.loads(files["raw"].read_bytes())
        for case in raw["tasks"][:4]:
            case["candidate_response"] = "WRONG"
            case["candidate_response_sha256"] = hashlib.sha256(b"WRONG").hexdigest()
            case["candidate_score"] = 0.0
        files["raw"].write_bytes(canonical(raw))
        execution = json.loads(files["execution"].read_bytes())
        execution["candidate_mean_score"] = 0.875
        files["execution"].write_bytes(canonical(execution))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "forged_task_score":
        raw = json.loads(files["raw"].read_bytes())
        raw["tasks"][0]["candidate_score"] = 0.0
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "task_reasoning_leak":
        raw = json.loads(files["raw"].read_bytes())
        raw["tasks"][0]["candidate_response"] = "<think>internal</think>"
        raw["tasks"][0]["candidate_response_sha256"] = hashlib.sha256(
            b"<think>internal</think>"
        ).hexdigest()
        raw["tasks"][0]["candidate_score"] = 0.0
        raw["tasks"][0]["reasoning_visible"] = True
        files["raw"].write_bytes(canonical(raw))
        execution = json.loads(files["execution"].read_bytes())
        execution["candidate_mean_score"] = 31 / 32
        execution["reasoning_leaks"] = 1
        files["execution"].write_bytes(canonical(execution))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "hidden_task_reasoning":
        raw = json.loads(files["raw"].read_bytes())
        raw["tasks"][0]["candidate_response"] = "<think>internal</think>"
        raw["tasks"][0]["candidate_response_sha256"] = hashlib.sha256(
            b"<think>internal</think>"
        ).hexdigest()
        raw["tasks"][0]["candidate_score"] = 0.0
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "tampered_response":
        raw = json.loads(files["raw"].read_bytes())
        raw["tasks"][0]["candidate_response"] = "WRONG"
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "resource_false_success":
        raw = json.loads(files["raw"].read_bytes())
        raw["resources"][0]["response"] = "WRONG"
        raw["resources"][0]["response_sha256"] = hashlib.sha256(b"WRONG").hexdigest()
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "vacuous_threshold":
        protocol = json.loads(files["protocol"].read_bytes())
        protocol["mean_score_drop_max"] = 1.0
        files["protocol"].write_bytes(canonical(protocol))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "duplicate_case":
        raw = json.loads(files["raw"].read_bytes())
        raw["tasks"][1]["id"] = raw["tasks"][0]["id"]
        files["raw"].write_bytes(canonical(raw))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "mismatched_summary":
        execution = json.loads(files["execution"].read_bytes())
        execution["task_cases"] = 33
        files["execution"].write_bytes(canonical(execution))
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "content_free_evidence":
        files["evidence"].write_bytes(
            canonical({"candidate_sha256": candidate_sha256, "status": "PASS"})
        )
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "content_free_raw":
        files["raw"].write_bytes(
            canonical(
                {
                    "candidate_sha256": candidate_sha256,
                    "protocol_sha256": digest(files["protocol"]),
                }
            )
        )
        rebind_technical_fixture(files, candidate_sha256)
    elif mutation == "wrong_reference_hash":
        acceptance["confirmation_reference"] = (
            "github-issue-comment:123:sha256:" + "f" * 64
        )
    if mutation in {"wrong_candidate", "owner", "wrong_reference_hash"}:
        files["acceptance"].write_bytes(canonical(acceptance))
    comment = {
        "id": 123,
        "issue_url": "https://api.github.com/repos/arajmir7/Azaeron-Verity/issues/2",
        "html_url": "https://github.com/arajmir7/Azaeron-Verity/pull/2#issuecomment-123",
        "user": {"login": "independent-fixture", "id": 123456, "type": "User"},
        "author_association": "COLLABORATOR",
        "body": files["body"],
        "created_at": "2026-10-12T10:00:00Z",
        "updated_at": "2026-10-12T10:00:00Z",
    }
    if mutation == "owner":
        comment["user"] = {
            "login": approval.OWNER_GITHUB_LOGIN,
            "id": approval.OWNER_GITHUB_ID,
            "type": "User",
        }
        comment["author_association"] = "OWNER"
    elif mutation == "wrong_pr":
        comment["issue_url"] = (
            "https://api.github.com/repos/arajmir7/Azaeron-Verity/issues/1"
        )
    elif mutation == "wrong_author":
        comment["author_association"] = "NONE"
    elif mutation == "bot":
        comment["user"]["type"] = "Bot"
    elif mutation == "edited":
        comment["updated_at"] = "2026-10-12T10:01:00Z"
    elif mutation == "wrong_body":
        comment["body"] += "\nextra"
    acceptance_file = files["acceptance"]
    review = CandidateReview.model_construct(
        technical_acceptance=FileRef(
            path=acceptance_file.name, sha256=digest(acceptance_file)
        )
    )
    monkeypatch.setattr(base_admission, "_fetch_technical_comment", lambda *_: comment)
    if reason is None:
        assert require_technical_acceptance(
            tmp_path, review, candidate, candidate_sha256
        ) == (
            files["acceptance"],
            files["evidence"],
            files["protocol"],
            files["fixtures"],
            files["execution"],
            files["raw"],
        )
    else:
        with pytest.raises((PolicyError, ValidationError), match=reason):
            require_technical_acceptance(tmp_path, review, candidate, candidate_sha256)


def test_production_technical_pass_without_independent_attestation_is_rejected():
    review = {
        "subject_sha256": "a" * 64,
        "purpose": "PRODUCTION",
        "reviewer": "TEST FIXTURE OWNER",
        "reviewer_kind": "HUMAN",
        "reviewed_at": "2026-10-12",
        "reference": "TEST FIXTURE ONLY",
        "license": "TEST_ONLY",
        "commercial_use": "PASS",
        "commercial_training": "PASS",
        "redistribution_requirements": "TEST FIXTURE ONLY",
        "attribution_requirements": "TEST FIXTURE ONLY",
        "acceptable_use_restrictions": "TEST FIXTURE ONLY",
        "technical_review": "PASS",
        "owner_decision": {"path": "owner-decision.json", "sha256": "a" * 64},
    }
    with pytest.raises(ValidationError, match="independent technical acceptance"):
        CandidateReview.model_validate(review)
    review["purpose"] = "TEST_ONLY"
    assert CandidateReview.model_validate(review).technical_acceptance is None


def test_short_targeted_probe_is_not_a_substantive_technical_pass():
    probe = {
        "classification": "DEV_ONLY_NON_TRAINING_TARGETED_BASE_PROBE",
        "results": [{}] * 5,
    }
    with pytest.raises(ValidationError, match="Field required"):
        TechnicalEvidence.model_validate(probe)


def test_owner_confirmation_authenticates_bound_packet_and_account(
    tmp_path, monkeypatch
):
    subject_sha256 = "a" * 64
    subject = ReviewedSubject(
        kind="BASE_MODEL",
        identifier="TEST FIXTURE",
        sha256=subject_sha256,
        license="TEST_ONLY",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        privacy="NOT_APPLICABLE",
        permitted_uses=["commercial_derivative_training"],
        findings=["TEST FIXTURE"],
        evidence=["TEST FIXTURE"],
        risks=[],
        restrictions=[],
    )
    pending = OwnerDecision(
        subjects=[subject],
        subject_sha256=hashlib.sha256(
            canonical([subject.model_dump(mode="json")])
        ).hexdigest(),
        decision="PENDING",
    )
    values = pending.model_dump(mode="json")
    packet = tmp_path / "pending.json"
    packet.write_bytes(canonical(values))
    values.update(
        decision="APPROVE_WITHIN_SCOPE",
        approver_name=approval.OWNER_NAME,
        decided_at="2026-10-12T10:00:00Z",
        rationale="Commercial derivative training for this base only",
        reviewed_record_sha256=digest(packet),
        confirmation_status="CONFIRMED",
    )
    record = OwnerDecision.model_validate(
        {**values, "confirmation_reference": "TEST FIXTURE ONLY"}
    )
    body = approval._confirmation_body(
        record, record.subjects[0], "commercial_derivative_training"
    )
    assert body == "\n".join(
        (
            "AZAERON_OWNER_CONFIRMATION_V1",
            "Decision: APPROVE_WITHIN_SCOPE",
            f"Packet-SHA256: {digest(packet)}",
            "Subject-kind: BASE_MODEL",
            f"Subject-SHA256: {subject_sha256}",
            "Permitted-use: commercial_derivative_training",
            "Scope: exactly this reviewed subject and use only",
        )
    )
    qwen_record = record.model_copy(
        update={"reviewed_record_sha256": approval.QWEN_BASE_PACKET_SHA256}
    )
    qwen_subject = subject.model_copy(update={"sha256": approval.QWEN_BASE_SHA256})
    assert approval._confirmation_body(
        qwen_record, qwen_subject, "commercial_derivative_training"
    ).endswith(
        "Scope: exact controlled third-party Qwen3-4B base only\n"
        "Excludes: dataset admission, human technical acceptance, production release"
    )
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    comment_id = 12345
    values["confirmation_reference"] = (
        f"github-issue-comment:{comment_id}:sha256:{body_hash}"
    )
    decision = tmp_path / "owner-decision.json"
    decision.write_bytes(canonical(values))
    comment = {
        "id": comment_id,
        "issue_url": (
            f"https://api.github.com/repos/{approval.CONFIRMATION_REPOSITORY}"
            f"/issues/{approval.CONFIRMATION_PR}"
        ),
        "html_url": (
            f"https://github.com/{approval.CONFIRMATION_REPOSITORY}/pull/"
            f"{approval.CONFIRMATION_PR}#issuecomment-{comment_id}"
        ),
        "user": {
            "login": approval.OWNER_GITHUB_LOGIN,
            "id": approval.OWNER_GITHUB_ID,
            "type": "User",
        },
        "author_association": "OWNER",
        "body": body,
        "created_at": "2026-10-12T10:00:00Z",
        "updated_at": "2026-10-12T10:00:00Z",
    }
    monkeypatch.setattr(approval, "_fetch_confirmation", lambda _id: comment)
    require_owner_approval(
        decision,
        "BASE_MODEL",
        subject_sha256,
        "commercial_derivative_training",
    )
    monkeypatch.setattr(
        approval,
        "_fetch_confirmation",
        lambda _id: {**comment, "body": body.replace("\n", "\r\n")},
    )
    require_owner_approval(
        decision,
        "BASE_MODEL",
        subject_sha256,
        "commercial_derivative_training",
    )
    monkeypatch.setattr(approval, "_fetch_confirmation", lambda _id: comment)
    for changed, reason in (
        ({"confirmation_reference": "TEST FIXTURE ONLY"}, "reference_invalid"),
        ({"reviewed_record_sha256": "f" * 64}, "packet_mismatch"),
    ):
        decision.write_bytes(canonical({**values, **changed}))
        with pytest.raises(PolicyError, match=reason):
            require_owner_approval(
                decision,
                "BASE_MODEL",
                subject_sha256,
                "commercial_derivative_training",
            )
    decision.write_bytes(canonical(values))
    for changed in (
        {"id": comment_id + 1},
        {"issue_url": "https://api.github.com/repos/elsewhere/other/issues/2"},
        {"author_association": "COLLABORATOR"},
        {"user": {**comment["user"], "id": 1}},
        {"updated_at": "2026-10-12T10:01:00Z"},
        {"body": body + "\nadditional scope"},
        {"body": body.replace("\n", "\r")},
    ):
        monkeypatch.setattr(
            approval, "_fetch_confirmation", lambda _id, c=changed: {**comment, **c}
        )
        with pytest.raises(PolicyError, match="comment_mismatch"):
            require_owner_approval(
                decision,
                "BASE_MODEL",
                subject_sha256,
                "commercial_derivative_training",
            )


def dataset_fixture(root):
    rows = {}
    for split in ["train", "validation", "calibration", "test", "ood"]:
        path = root / (split + ".jsonl")
        row = {
            "id": split,
            "group": split,
            "input": split,
            "target": "AI",
            "language": "en",
            "domain": "fixture",
            "task": "classify",
            "slices": [],
            "generator_family": split,
        }
        path.write_bytes(canonical(row) + b"\n")
        rows[split] = {"path": path.name, "sha256": digest(path)}
    return Dataset(
        dataset_id="fixture",
        version="1",
        purpose="TEST_ONLY",
        source="fixture",
        license="TEST_ONLY",
        commercial_training_permission="GRANTED",
        redistribution_permission="PROHIBITED",
        provenance="fixture",
        acquisition_method="generated",
        copyright_review="PASS",
        pii_review="PASS",
        language=["en"],
        domain=["fixture"],
        quality_tier="TEST_FIXTURE",
        allowed_model_families=["detector"],
        contains_customer_content=False,
        splits=rows,
        review={"path": "review.json", "sha256": "0" * 64},
    )


def save_dataset(root, manifest):
    review = DatasetReview(
        subject_sha256=review_subject(manifest),
        reviewer="TEST_ONLY",
        reviewer_kind="TEST_FIXTURE",
        reviewed_at="2026-09-30",
        evidence_reference="TEST_ONLY",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        pii="PASS",
    )
    (root / "review.json").write_bytes(canonical(review.model_dump()) + b"\n")
    manifest = manifest.model_copy(
        update={
            "review": FileRef(path="review.json", sha256=digest(root / "review.json"))
        }
    )
    (root / "dataset.json").write_bytes(canonical(manifest.model_dump()) + b"\n")
    return root / "dataset.json"


@pytest.mark.parametrize("field", ["group", "input", "id", "generator_family"])
def test_five_split_leakage_rejected(tmp_path, field):
    manifest = dataset_fixture(tmp_path)
    path = save_dataset(tmp_path, manifest)
    assert len(read_dataset(path, "detector", smoke=True)[1]) == 5
    test = tmp_path / "test.jsonl"
    row = json.loads(test.read_bytes())
    row[field] = "train"
    test.write_bytes(canonical(row) + b"\n")
    values = manifest.model_dump()
    values["splits"]["test"]["sha256"] = digest(test)
    path = save_dataset(tmp_path, Dataset.model_validate(values))
    with pytest.raises(PolicyError, match="leakage"):
        read_dataset(path, "detector", smoke=True)


def test_dataset_reviews_bound_and_customer_data_rejected(tmp_path):
    manifest = dataset_fixture(tmp_path)
    path = save_dataset(tmp_path, manifest)
    with pytest.raises(PolicyError, match="purpose"):
        read_dataset(path, "detector")
    values = json.loads(path.read_bytes())
    values["license"] = "changed"
    path.write_bytes(canonical(values))
    with pytest.raises(PolicyError, match="binding"):
        read_dataset(path, "detector", smoke=True)
    with pytest.raises(ValidationError):
        Dataset.model_validate(
            {**manifest.model_dump(), "contains_customer_content": True}
        )


@pytest.mark.parametrize(
    "field", ["source_id", "author_id", "document_id", "synthetic_parent_id"]
)
def test_multi_axis_lineage_leakage_rejected(field):
    index = LeakageIndex()
    row = dict(
        id="a",
        group="a",
        input="original",
        target="HUMAN",
        language="en",
        domain="fixture",
        task="classify",
        slices=[],
        **{field: "shared"},
    )
    index.add(Example.model_validate(row), "train")
    with pytest.raises(PolicyError, match="lineage_split_leakage"):
        index.add(
            Example.model_validate({**row, "id": "b", "input": "independent wording"}),
            "test",
        )


def test_near_duplicate_and_derived_lineage_rejected():
    index = LeakageIndex()
    text = " ".join("word" + str(i) for i in range(80))
    row = dict(
        id="a",
        group="a",
        input=text,
        target="HUMAN",
        language="en",
        domain="fixture",
        task="classify",
        slices=[],
    )
    index.add(Example.model_validate(row), "train")
    with pytest.raises(PolicyError, match="near_duplicate"):
        index.add(
            Example.model_validate({**row, "id": "b", "input": text + " new ending"}),
            "ood",
        )
    with pytest.raises(PolicyError, match="lineage_split_leakage"):
        index.add(
            Example.model_validate(
                {**row, "id": "c", "input": "unrelated", "derived_from": ["a"]}
            ),
            "test",
        )


@pytest.mark.parametrize("overlap", ["exact_target", "near_target", "cross_field"])
def test_writer_answer_leakage_rejected(overlap):
    index = LeakageIndex()
    answer = " ".join(f"distinctword{i}" for i in range(40))
    first = Example.model_validate(
        {
            "id": "train-row",
            "group": "train-group",
            "input": "Describe a quiet harbor at sunrise in natural prose.",
            "target": answer,
            "language": "en",
            "domain": "prose",
            "task": "natural_prose",
            "slices": [],
        }
    )
    index.add(first, "train", include_target=True)
    input_text = (
        answer if overlap == "cross_field" else "Write about an unrelated forest."
    )
    target_text = (
        "A wholly different completion."
        if overlap == "cross_field"
        else answer + " a new closing sentence" if overlap == "near_target" else answer
    )
    second = Example.model_validate(
        {
            **first.model_dump(),
            "id": "test-row",
            "group": "test-group",
            "input": input_text,
            "target": target_text,
        }
    )
    with pytest.raises(PolicyError, match="split_leakage"):
        index.add(second, "test", include_target=True)


def test_production_dataset_missing_derivative_rights_fails_before_review(tmp_path):
    manifest = dataset_fixture(tmp_path).model_copy(update={"purpose": "PRODUCTION"})
    path = save_dataset(tmp_path, manifest)
    with pytest.raises(PolicyError, match="derivative_rights"):
        read_dataset(path, "detector")


def test_production_dataset_requires_owner_record(tmp_path):
    manifest = dataset_fixture(tmp_path).model_copy(
        update={
            "purpose": "PRODUCTION",
            "derivative_permission": "GRANTED",
            "quality_tier": "CURATED",
            "allowed_tasks": ["classify"],
        }
    )
    path = save_dataset(tmp_path, manifest)
    review_path = tmp_path / "review.json"
    review = json.loads(review_path.read_bytes())
    review["reviewer_kind"] = "HUMAN"
    review_path.write_bytes(canonical(review))
    values = json.loads(path.read_bytes())
    values["review"]["sha256"] = digest(review_path)
    path.write_bytes(canonical(values))
    with pytest.raises(PolicyError, match="owner_dataset_decision_required"):
        read_dataset(path, "detector")


def test_registered_production_dataset_preserves_owner_decision(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    manifest = dataset_fixture(source).model_copy(
        update={
            "purpose": "PRODUCTION",
            "derivative_permission": "GRANTED",
            "quality_tier": "CURATED",
            "allowed_tasks": ["classify"],
        }
    )
    values = manifest.model_dump(mode="json")
    for split in values["splits"]:
        path = source / f"{split}.jsonl"
        row = json.loads(path.read_bytes())
        row.update(
            source_id=f"source-{split}",
            author_id=f"author-{split}",
            document_id=f"document-{split}",
        )
        path.write_bytes(canonical(row) + b"\n")
        values["splits"][split]["sha256"] = digest(path)
    reviewed = Dataset.model_validate(values)
    subject = {
        "kind": "DATASET",
        "identifier": "TEST FIXTURE ONLY",
        "sha256": review_subject(reviewed),
        "license": "TEST_ONLY",
        "rights": "PASS",
        "provenance": "PASS",
        "copyright": "PASS",
        "privacy": "PASS",
        "permitted_uses": ["commercial_training"],
        "findings": ["TEST FIXTURE ONLY"],
        "evidence": ["TEST FIXTURE ONLY"],
        "risks": [],
        "restrictions": [],
    }
    decision = {
        "schema_version": 1,
        "subjects": [subject],
        "subject_sha256": hashlib.sha256(canonical([subject])).hexdigest(),
        "decision": "PENDING",
        "approver_role": "AZAERON_PROJECT_OWNER",
        "approver_name": None,
        "decided_at": None,
        "rationale": None,
        "reviewed_record_sha256": None,
        "confirmation_status": "PENDING",
        "confirmation_reference": None,
    }
    decision["reviewed_record_sha256"] = hashlib.sha256(canonical(decision)).hexdigest()
    decision.update(
        decision="APPROVE_WITHIN_SCOPE",
        approver_name=approval.OWNER_NAME,
        decided_at="2026-10-12T10:00:00Z",
        rationale="TEST FIXTURE ONLY",
        confirmation_status="CONFIRMED",
        confirmation_reference="TEST FIXTURE ONLY",
    )
    owner_file = source / "owner-decision.json"
    owner_file.write_bytes(canonical(decision))
    review = DatasetReview(
        subject_sha256=review_subject(reviewed),
        reviewer=approval.OWNER_NAME,
        reviewer_kind="HUMAN",
        reviewed_at="2026-10-12T10:00:00Z",
        evidence_reference="TEST FIXTURE ONLY",
        rights="PASS",
        provenance="PASS",
        copyright="PASS",
        pii="PASS",
        owner_decision=FileRef(path=owner_file.name, sha256=digest(owner_file)),
    )
    review_file = source / "review.json"
    review_file.write_bytes(canonical(review.model_dump(mode="json")))
    values["review"] = {"path": review_file.name, "sha256": digest(review_file)}
    manifest_file = source / "dataset.json"
    manifest_file.write_bytes(canonical(values))
    monkeypatch.setattr(approval, "_verify_authenticated_confirmation", lambda *_: None)

    registered = register(manifest_file, tmp_path / "registry")
    assert digest(registered / owner_file.name) == digest(owner_file)
    assert len(read_dataset(registered / "dataset.json", "detector")[1]) == 5


def test_production_release_requires_new_checkpoint_bound_owner_record(tmp_path):
    model = approved_model(model_id="fixture-writer")
    (tmp_path / "lineage.json").write_bytes(
        canonical(model.lineage.model_dump(mode="json"))
    )
    with pytest.raises(PolicyError, match="owner_release_decision_required"):
        promote(
            tmp_path, {}, model.release.model_dump(mode="json"), AzaeronModelRegistry()
        )


def test_gpu_plan_blocks_oversized_training():
    value = plan(
        7_000_000_000,
        7_000_000_000,
        method="full",
        precision="bfloat16",
        layers=32,
        width=4096,
        heads=32,
        vocab=128000,
        sequence=2048,
        microbatch=1,
        accumulation=16,
        checkpointing=True,
        tokens=10_000_000,
    )
    assert value["optimizer_bytes"] == 56_000_000_000
    with pytest.raises(PolicyError, match="memory"):
        enforce(
            value,
            {
                "cuda": [],
                "memory_total_bytes": 16 * 1024**3,
                "memory_available_bytes": 10 * 1024**3,
                "disk_free_bytes": 60 * 1024**3,
            },
            "cpu",
            output_bytes=28_000_000_000,
        )
    with pytest.raises(ValidationError):
        DerivativeConfig.model_validate({"method": "qlora", "device": "mps"})


def test_same_base_verifier_rejected_even_with_new_weights():
    writer = approved_model(model_id="writer")
    verifier = approved_model(model_id="verifier", tasks=["verify"])
    shared = {
        "classification": "AZAERON_DERIVATIVE",
        "base_model": "fixture/base",
        "base_revision": "a" * 40,
        "base_checkpoint_sha256": "a" * 64,
        "base_approval_sha256": "b" * 64,
    }
    writer = approved_model(
        model_id="writer", lineage={**writer.lineage.model_dump(), **shared}
    )
    verifier = approved_model(
        model_id="verifier",
        tasks=["verify"],
        lineage={**verifier.lineage.model_dump(), **shared},
    )
    with pytest.raises(ValidationError, match="independent base"):
        AzaeronModelRegistry(models=[writer, verifier])


def test_detector_ties_calibration_thresholds_and_region_abstention():
    threshold = operating_thresholds([0.1, 0.9, 0.8], [0, 1, 2])
    probs = [[0.9, 0.05, 0.05], [0.01, 0.98, 0.01], [0.01, 0.01, 0.98]]
    result = detector_report(probs, [0, 1, 2], ["en", "en", "ood"], {"en"}, threshold)
    assert result["auroc"] == result["auprc"] == 1
    assert result["coverage"] == pytest.approx(2 / 3)
    assert result["subgroups"]["ood"]["coverage"] == 0
    assert result["operating_points"]["0.001"]["insufficient_fpr_resolution"]
    tied = detector_report(
        [[0.5, 0.25, 0.25]] * 2, [0, 1], ["en"] * 2, {"en"}, threshold
    )
    assert tied["auroc"] == tied["auprc"] == 0.5
    with pytest.raises(PolicyError):
        detector_report([[float("nan"), 0, 1]], [0], ["en"], {"en"}, threshold)


def test_model_self_rating_is_not_human_review(tmp_path):
    path = tmp_path / "review.json"
    path.write_bytes(
        canonical(
            {
                "checkpoint_sha256": "a" * 64,
                "dataset_manifest_sha256": "b" * 64,
                "method": "blinded_independent_ratings_v1",
                "reviewer_kind": "MODEL",
                "ratings": [],
            }
        )
    )
    with pytest.raises(PolicyError):
        writer_review(path, "a" * 64, "b" * 64, {"sample": "c" * 64})
