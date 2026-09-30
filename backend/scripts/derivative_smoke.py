"""Execute real full/LoRA optimization on fresh, tiny local fixtures only.

Generated inputs, reviewer records and random GPT-2 architecture weights here
are TEST_ONLY. They are not third-party assets or legal/quality evidence.
"""

import argparse
import json
from pathlib import Path

from app.modules.model_platform.admission import admit
from app.modules.model_platform.bakeoff import run
from app.modules.model_platform.datasets import Dataset, register, review_subject
from app.modules.model_platform.derivative import offline, train
from app.modules.model_platform.policy import canonical, digest


def write(path, value):
    path.write_bytes(canonical(value) + b"\n")
    return {"path": path.name, "sha256": digest(path)}


def execute(root: Path):
    offline()
    import torch
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

    root.mkdir(parents=True, exist_ok=False)
    admissions = []
    for index in range(2):
        source = root / ("source" + str(index))
        source.mkdir()
        torch.manual_seed(123 + index)
        token = Tokenizer(
            WordLevel(
                {
                    "[UNK]": 0,
                    "[EOS]": 1,
                    "[PAD]": 2,
                    "Instruction": 3,
                    "Response": 4,
                    ":": 5,
                    "fixture": 6,
                    "answer": 7,
                },
                unk_token="[UNK]",
            )
        )
        token.pre_tokenizer = Whitespace()
        tokenizer = PreTrainedTokenizerFast(
            tokenizer_object=token,
            eos_token="[EOS]",
            pad_token="[PAD]",
            unk_token="[UNK]",
        )
        tokenizer.save_pretrained(source)
        model = GPT2LMHeadModel(
            GPT2Config(
                vocab_size=8,
                n_positions=64,
                n_embd=16,
                n_layer=1,
                n_head=2,
                bos_token_id=1,
                eos_token_id=1,
                pad_token_id=2,
            )
        )
        model.save_pretrained(source, safe_serialization=True)
        (source / "LICENSE").write_text(
            "TEST FIXTURE ONLY. No commercial approval. Generated random weights for code verification.\n"
        )
        (source / "README.md").write_text(
            "TEST ONLY. Fresh random GPT2 architecture fixture; not a pretrained GPT2 checkpoint.\n"
        )
        candidate = root / ("candidate" + str(index) + ".json")
        write(
            candidate,
            {
                "candidate_id": "fixture-" + str(index),
                "purpose": "TEST_ONLY",
                "repository": "local/test-fixture-" + str(index),
                "revision": str(index + 1) * 40,
                "artifacts": {p.name: digest(p) for p in source.iterdir()},
                "weights": ["model.safetensors"],
                "tokenizer": ["tokenizer.json", "tokenizer_config.json"],
                "license_file": "LICENSE",
                "model_card": "README.md",
                "license": "TEST_ONLY",
                "architecture": "gpt2",
                "parameters": sum(p.numel() for p in model.parameters()),
                "context": 64,
                "languages": ["fixture"],
                "runtime_compatibility": ["transformers-local-test"],
            },
        )
        review = root / ("review" + str(index) + ".json")
        write(
            review,
            {
                "subject_sha256": digest(candidate),
                "purpose": "TEST_ONLY",
                "reviewer": "TEST_FIXTURE_NOT_LEGAL_REVIEW",
                "reviewer_kind": "TEST_FIXTURE",
                "reviewed_at": "2026-09-30",
                "reference": "TEST_ONLY",
                "license": "TEST_ONLY",
                "commercial_use": "PASS",
                "commercial_training": "PASS",
                "redistribution_requirements": "TEST_ONLY",
                "attribution_requirements": "TEST_ONLY",
                "acceptable_use_restrictions": "CI_ONLY",
                "technical_review": "PASS",
                "strong_baseline": True,
                "strong_baseline_evidence": "TEST_FIXTURE_NOT_STRONG_MODEL",
            },
        )
        admissions.append(
            admit(candidate, review, source, root / "candidates", smoke=True)
        )
    data = root / "data"
    data.mkdir()
    splits = {}
    for split in ["train", "validation", "calibration", "test", "ood"]:
        path = data / (split + ".jsonl")
        path.write_text(
            "".join(
                canonical(
                    {
                        "id": split + str(i),
                        "group": split + str(i),
                        "input": "fixture " + split + str(i),
                        "target": "answer",
                        "language": "fixture",
                        "domain": "fixture",
                        "task": "instruction",
                        "slices": [],
                    }
                ).decode()
                + "\n"
                for i in range(4)
            )
        )
        splits[split] = {"path": path.name, "sha256": digest(path)}
    values = {
        "dataset_id": "derivative-fixture",
        "version": "1",
        "purpose": "TEST_ONLY",
        "source": "Program generated fixture symbols",
        "license": "TEST_ONLY",
        "commercial_training_permission": "GRANTED",
        "redistribution_permission": "PROHIBITED",
        "provenance": "derivative_smoke.py",
        "acquisition_method": "generated_fixture",
        "copyright_review": "PASS",
        "pii_review": "PASS",
        "language": ["fixture"],
        "domain": ["fixture"],
        "quality_tier": "TEST_FIXTURE",
        "allowed_model_families": ["writer"],
        "contains_customer_content": False,
        "splits": splits,
        "review": {"path": "review.json", "sha256": "0" * 64},
    }
    review = data / "review.json"
    values["review"] = write(
        review,
        {
            "subject_sha256": review_subject(Dataset.model_validate(values)),
            "reviewer": "TEST_FIXTURE",
            "reviewer_kind": "TEST_FIXTURE",
            "reviewed_at": "2026-09-30",
            "evidence_reference": "TEST_ONLY_NO_PRODUCTION_RIGHTS",
            "rights": "PASS",
            "provenance": "PASS",
            "copyright": "PASS",
            "pii": "PASS",
        },
    )
    manifest = data / "dataset.json"
    write(manifest, values)
    registered = register(manifest, root / "datasets", smoke=True) / "dataset.json"

    def ref(path):
        return {"path": str(path.relative_to(root)), "sha256": digest(path)}

    outcomes = {}
    for method in ["full", "lora"]:
        config = root / (method + ".json")
        write(
            config,
            {
                "candidate": ref(admissions[0] / "candidate.json"),
                "dataset": ref(registered),
                "method": method,
                "device": "cpu",
                "precision": "float32",
                "seed": 42,
                "epochs": 1,
                "sequence_length": 32,
                "microbatch": 1,
                "gradient_accumulation": 2,
                "learning_rate": 0.001,
                "lora_rank": 2,
                "lora_alpha": 4,
                "target_modules": ["c_attn"],
                "merge_adapter": method == "lora",
            },
        )
        outcomes[method] = train(config, root / (method + "-run"), smoke=True)
        assert outcomes[method]["steps"] == 2
        assert outcomes[method]["classification"] == "AZAERON_DERIVATIVE"
        assert outcomes[method]["production_approval"] == "NOT_APPROVED"
        repeated = train(config, root / (method + "-repeat"), smoke=True)
        assert repeated["checkpoint_sha256"] == outcomes[method]["checkpoint_sha256"]
    protocol = root / "benchmark.json"
    write(
        protocol,
        {
            "dataset": ref(registered),
            "device": "cpu",
            "seed": 5,
            "max_input_tokens": 32,
            "max_output_tokens": 4,
            "entrants": [
                {
                    "id": "baseline-" + str(i),
                    "role": "BASELINE",
                    "admission": ref(path / "candidate.json"),
                }
                for i, path in enumerate(admissions)
            ]
            + [
                {
                    "id": "lora-candidate",
                    "role": "CANDIDATE",
                    "admission": ref(admissions[0] / "candidate.json"),
                    "training_manifest": ref(
                        root / "lora-run" / "training-manifest.json"
                    ),
                }
            ],
        },
    )
    benchmark = run(protocol, root / "bakeoff", smoke=True)
    assert benchmark["status"] == "BLOCKED" and benchmark["winner"] is None
    summary = {
        "purpose": "TEST_ONLY",
        "quality_evidence": False,
        "production_approval": "NOT_APPROVED",
        "full": {
            key: outcomes["full"][key]
            for key in ["steps", "checkpoint_sha256", "tokens_processed", "metrics"]
        },
        "lora": {
            key: outcomes["lora"][key]
            for key in [
                "steps",
                "checkpoint_sha256",
                "adapter_sha256",
                "merged_checkpoint_sha256",
                "tokens_processed",
                "metrics",
            ]
        },
        "reproducible_weights": True,
        "qlora": "BLOCKED_NO_CUDA_EXECUTION",
        "bakeoff": benchmark,
    }
    write(root / "result.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args.output), indent=2))
