# Production model candidate program

**2026-10-01 hardening:** Native training and evaluation now use the same rights-reviewed v2 datasets as derivative training, with separate TRAIN/VAL/CAL/TEST/OOD inputs and hash-bound review metadata. V1 three-split manifests are accepted only for historical `TEST_ONLY` fixtures; marking them `PRODUCTION` cannot bypass v2 admission, even with `--smoke`. The four-family native smoke runner now executes this five-split path in CI.

Detector decision metrics now apply the same confidence/region abstention mask to false positives, recall, F1 and selective accuracy. Raw accuracy, Brier, ECE and ranking metrics still describe all observations. Frozen CAL thresholds use an O(n log n) computation with tie preservation; each TEST operating point reports a conservative FPR upper bound as well as its empirical rate and sample resolution. Native evaluation records a separate OOD split hash and refuses to certify unvalidated serving regions. The private classification contract uses `HUMAN`, `AI`, `MIXED`, `UNCERTAIN`; abstention requires `probabilities: null`, and the gateway rejects conflicting payloads. This contract change affects the currently unapproved specialist endpoint; no production detector exists. Validated-region runtime enforcement and real calibration remain outstanding.

The production registry remains empty. The nine-step native models and new tiny derivative-path fixtures are **TEST_ONLY**, never capable product models. The current model classes are `AZAERON_NATIVE` and `AZAERON_DERIVATIVE`; historical `AZAERON_ORIGINAL` fixture manifests are retained unchanged as evidence, not migrated into production approvals.

The candidate program adds working offline SFT, full fine-tuning, LoRA and a CUDA-gated QLoRA implementation. Full and LoRA optimization, safe-tensor export, adapter merging, repeated-seed weight equality and a common three-entrant benchmark were executed on generated random architecture fixtures. QLoRA has **not** been executed: this Mac has no CUDA GPU. This evidence tests mechanics only. No pretrained model was downloaded or selected, no legal approval was created, and no production training ran.

## Admission and immutable datasets

Run these commands from `backend` with the isolated derivative environment. JSON schemas are in `config/model-platform/`. Paths inside a manifest are relative, confined and hash verified. All output directories are exclusive; admitted bundles and dataset versions become read-only. Every subsequent load verifies content again. An operator must separately authorize any download; these commands have no download implementation.

```sh
python -m app.modules.model_platform.admission --manifest candidate.json --review legal-review.json --source approved-local-bundle --registry private-candidate-registry
python -m app.modules.model_platform.datasets --manifest dataset.json --registry private-dataset-registry
python -m app.modules.model_platform.derivative --config training.json --output new-run-directory
python -m app.modules.model_platform.bakeoff --config bakeoff.json --output new-benchmark-directory
```

Candidate admission requires repository, immutable revision, complete weight/tokenizer/file hashes, model card, license, commercial-training/use review, redistribution/attribution/AUP requirements, supported languages, architecture, context and runtime compatibility. Executable/pickle files, unknown artifact types, symlinks, remote-code mappings, malformed safe tensors and unlisted files fail. Human attestations are inputs, not legal conclusions made by software. Filesystem access cannot establish a reviewer's authority; organizational review and access controls remain mandatory.

Dataset v2 requires source, license, granted commercial training, redistribution permission, acquisition, provenance, PII/copyright review, language/domain, quality tier, allowed families, and an attestation covering all metadata and split hashes. Customer content is prohibited by this ingestion path. Unknown rights fail validation. The version cannot be overwritten. Five nonempty splits are mandatory: train, validation, calibration, test, OOD. IDs, normalized inputs and source groups cannot cross splits. Detector AI/MIXED rows need generator lineage; generator families cannot cross splits. This is intentionally stricter than merely de-duplicating generator outputs.

Writer task categories and MeaningLock stress categories are defined in `datasets.py`. No real corpus has been acquired or approved. Data sourcing, human curation, meaningful adversarial coverage and provenance review remain **BLOCKED**. Generated review records exist only in the explicit smoke script with TEST_ONLY purpose and TEST_FIXTURE reviewer identity; production loaders reject them.

## Training and hardware boundaries

Full, LoRA and QLoRA share a plain, explicit instruction/response format, masked prompt loss, fixed seed, AdamW, linear warmup/decay, gradient accumulation/clipping, optional checkpointing, finite-loss checks and overflow rejection. Bundle chat templates are never executed. All Hugging Face loading uses verified local paths, immutable revisions, `local_files_only=True`, `trust_remote_code=False`, offline environment flags and safe tensors. No inference provider is involved.

The trainer inspects the architecture on the meta device and counts parameters before allocating weights. Memory planning includes weights, Adam moments, gradients, master weights, activations, attention/logits, overhead, sequence length, batch/accumulation and total tokens/FLOPs. Device and host limits reserve headroom; large runs on the 16 GB Mac fail preflight. Estimates are not peak-memory certification. Sustained compute time and an exact production GPU configuration remain blocked until an admitted candidate, reviewed token budget and measured GPU throughput exist. QLoRA requires CUDA and an independently installed/audited bitsandbytes environment; automatic quantized merging is prohibited.

Runs record base repository/revision and every artifact hash, candidate review, dataset/split hashes, original tokenizer lineage, adapter/merged/new checkpoint hashes, before/after trainable-parameter hashes, code hash, seed/hyperparameters, optimizer/scheduler/precision, hardware/software, wall time, token counts and train/validation losses. Exports are immutable and explicitly EXPERIMENTAL. Adapter-only output is not a standalone owned production model. Export into the serving registry, runtime compatibility, security, evaluation and independent release review remain separate and **BLOCKED**.

Use `requirements-derivative-macos.lock` for the tested Python 3.13 Mac environment. `requirements-derivative-linux-cpu.lock` pins the official CPython 3.12 AMD64 CPU wheel and dependencies for hosted mechanics CI. Neither belongs in the API image. A production CUDA/runtime image and CUDA dependency lock are not certified.

## Evaluation and independence

The new offline bake-off can compare experimental candidates without first granting production serving approval. It requires two distinct, commercially reviewed, evidenced strong baselines plus a candidate. All share the same held-out dataset, prompt format, greedy decoding, input/output limits, seed and device. It records raw outputs/output hashes for later blinded review, latency, TTFT, token throughput, failure rate, 20 ms sampled process RSS, CUDA allocation peak when available and per-context observations. Serial reference measurements are not production batching/load evidence. A tiny fixture substitutes for neither strong baselines nor a quality benchmark. The older `scripts/model_bakeoff.py` remains for post-approval private-runtime evaluation.

Human review requires explicit HUMAN identity, independence attestation, a protocol reference, exact dataset/checkpoint/output bindings and at least two reviewers per sample. Thirteen rating dimensions cover quality, fidelity, grounded answers and tool correctness. The harness cannot authenticate reviewer identity or manufacture reviews. No human reviews are present. No automatic winner or APPROVED decision is emitted.

Detector metric utilities now include tie-correct AUROC/AUPRC, class precision/recall/F1, Brier/ECE, coverage/abstention, calibration-only thresholds for 0.1%/1%/5% FPR, held-out achieved FPR/TPR, sample-resolution warnings and region subgroup reports. Region abstention in this utility is **not** certification of the currently unapproved detector or a completed real-data five-split experiment. Existing native retrieval evaluation adds Recall@1/5/10 to MRR/nDCG@10. Real-world detector calibration/OOD and hard retrieval judgments remain missing.

The serving registry additionally rejects a Writer/Verifier sharing the same base checkpoint hash, base repository/revision or initialization hash even when fine-tuned output hashes differ. Existing independent verification, typed/server-authorized tools, one normal rewrite generation, MeaningLock, tenant-private optional VoiceLock and workspace similarity remain intact. Additional VoiceLock statistics, specialist derivative training and validated-region serving integration remain unfinished; they are not prerequisites for the blocked Writer experiment. No reranker was added without empirical benefit. No corpus was represented as licensed or web-wide without rights and infrastructure.

## Evidence and stop conditions

Local evidence: `docs/verity/evidence/model-bakeoff-20260930/`. Generated checkpoints and raw fixture runs: `.verity-local/derivative-smoke-final/`. CI uploads derivative mechanics and repository/image/SBOM artifacts for the submitted head. All fixture outputs are NOT APPROVED.

Candidate manifests/commercial reviews for the discovered Qwen/MiniLM bundles: **NOT FOUND**. Production datasets, independent reviewers and approved strong baselines: **NOT FOUND**. Production checkpoints, GPU evidence and runtime approval: **BLOCKED**. Existing exact local asset paths remain in `docs/verity/LOCAL_MODEL_ASSETS.md`. Do not relabel those assets.

The later commercial continuation installs Debian stable security OpenSSL 3.5.7-1~deb13u3 and uses a controlled PostgreSQL 16 image with a new-volume logical migration. Local candidate scans pass; exact-head hosted status is tracked in `docs/verity/EXECUTION_STATE.md`. Scanner thresholds remain unchanged. No merge or production approval follows from repository tests alone.

Real candidate training/promotion remains blocked by missing rights, reviewers and GPU/runtime evidence. The next productive input is an operator-selected local candidate with accountable commercial review and an independently reviewed dataset, not more fixture training.

Implementation references: [Transformers local loading](https://huggingface.co/docs/transformers/main/en/main_classes/model), [PEFT LoRA](https://huggingface.co/docs/peft/main/en/package_reference/lora), [PEFT quantized training](https://huggingface.co/docs/peft/main/en/developer_guides/quantization). Execution uses pinned packages, not floating documentation versions.
