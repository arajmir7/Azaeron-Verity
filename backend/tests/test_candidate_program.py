"""Admission, leakage, compute and release attacks; no production model fixtures."""

import hashlib
import json
from pathlib import Path
import runpy

import pytest
from pydantic import ValidationError

from app.modules.model_platform.admission import (
    Candidate,
    CandidateReview,
    admit,
    load_candidate,
    verify_bundle,
)
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
    admitted = admit(manifest, review_file, source, tmp_path / "registry")
    assert load_candidate(admitted)[0].purpose == "PRODUCTION"
    assert (
        json.loads((admitted / "admission.json").read_bytes())["status"]
        == "EXPERIMENTAL"
    )


def test_owner_confirmation_authenticates_exact_qwen_packet_and_account(
    tmp_path, monkeypatch
):
    root = Path(__file__).resolve().parents[2]
    packet = (
        root
        / "docs/verity/evidence/qwen-controlled-conversion-20261011"
        / "base-owner-decision-pending.json"
    )
    values = json.loads(packet.read_bytes())
    assert digest(packet) == approval.QWEN_BASE_PACKET_SHA256
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
    published = runpy.run_path(str(root / "scripts/verity_owner_confirmation.py"))
    assert body == published["COMMENT_BODY"]
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
        approval.QWEN_BASE_SHA256,
        "commercial_derivative_training",
    )
    for changed, reason in (
        ({"confirmation_reference": "TEST FIXTURE ONLY"}, "reference_invalid"),
        ({"reviewed_record_sha256": "f" * 64}, "packet_mismatch"),
    ):
        decision.write_bytes(canonical({**values, **changed}))
        with pytest.raises(PolicyError, match=reason):
            require_owner_approval(
                decision,
                "BASE_MODEL",
                approval.QWEN_BASE_SHA256,
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
    ):
        monkeypatch.setattr(
            approval, "_fetch_confirmation", lambda _id, c=changed: {**comment, **c}
        )
        with pytest.raises(PolicyError, match="comment_mismatch"):
            require_owner_approval(
                decision,
                "BASE_MODEL",
                approval.QWEN_BASE_SHA256,
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
