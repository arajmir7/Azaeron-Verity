# Azaeron controlled model platform

The platform has four executable reference trainers and a private native runtime. **There is no production-approved Azaeron model.** Existing Qwen and MiniLM assets are third-party baselines, not Azaeron checkpoints. The only newly trained weights are tiny, synthetic `TEST_ONLY` mechanics fixtures. Their hashes and exact local paths are recorded in [checkpoint inventory](../../docs/verity/evidence/owned-model-platform-20260930/checkpoint-inventory.json). They cannot be promoted.

## Implemented training and evidence

`app.modules.model_platform.train` trains original byte-token Transformer networks from seeded random initialization. Writer uses masked causal next-token loss; Verifier uses four-way semantic classification; Detector uses human/AI/mixed classification; Embed uses symmetric in-batch contrastive loss with normalized vectors. Each family is trained separately. The reference implementation uses bounded batches, deterministic CPU execution, finite-loss checks, clipped gradients and safe tensor serialization. It rejects context overflow instead of silently dropping text. It has no base-model download, external teacher or hosted inference call.

Every dataset has three disjoint splits (`train`, `calibration`, `evaluation`), a source, license, permitted families, split hashes, and a hash-bound review for each split. Reviews must attest commercial training rights, provenance, PII review and copyright review, with named reviewer, date and evidence reference. Unknown, missing or mismatched rights block training before ML imports. Repeated normalized inputs, duplicate IDs and overlapping source groups across splits fail. These are operator attestations, not automated legal approval; fabricated reviewer records are not acceptable evidence. Customer documents never become training data implicitly.

Schemas live in `config/model-platform/*.schema.json`. JSONL rows contain exactly `id`, `group`, `input`, `target`. Classifier targets use the labels above; embedding targets are positive passages. Writer training inputs must use the same serialized system/user message envelope as the runtime. Verifier inputs must use the gateway's original/candidate/mode envelope; labels must reflect the declared equivalence or support policy. Reviewers must group source-derived examples before splitting. Generated numeric smoke labels are intentionally meaningless for quality evaluation.

Train from the backend directory in an isolated dependency environment:

```sh
python -m app.modules.model_platform.train --config /private/run/config.json --output /private/run/new-bundle
python -m app.modules.model_platform.evaluate --bundle /private/run/new-bundle --dataset /private/data/dataset.json --output /private/run/evaluation.json
```

The trainer writes a new safetensors checkpoint, tokenizer/architecture, reproducible configuration, initialization/checkpoint hashes, dataset/review hashes, code hash, environment, actual step count, lineage and a model card. It never writes approval. `--smoke` requires `TEST_ONLY` data and never yields a promotable artifact. The supported trainer is from scratch; fine-tuning an approved third-party base is **not implemented**. Registry policy already requires any future derivative to declare `AZAERON_DERIVATIVE` and its approved immutable base lineage. Merely renaming a checkpoint cannot satisfy ownership.

## Evaluation and promotion

Evaluation executes the saved checkpoint on held-out rows. Classifiers fit a bounded temperature on the calibration split and measure accuracy, ECE, Brier, coverage, class recall and OOD groups. Detector checks include mixed recall and a conservative upper confidence bound on human false positives. Verifier additionally requires number/date/entity/citation/negation stress groups. Retrieval reports Recall@10, MRR, nDCG@10 and measured latency. Writer reports reference invariant preservation and exact reference match; these do not establish writing quality. Checkpoint/output-bound ratings from at least two independent blinded reviewers per example are required for naturalness, instruction following, semantic/factual/citation preservation and hallucination-free output (`--review`).

Promotion requires at least 1,000 evaluation examples and every applicable quality check. A baseline comparison and production load benchmark must separately pass; the evaluator never fabricates those results. The reference thresholds are release minima, not evidence that a trained model meets them. The existing `scripts/model_bakeoff.py` remains blocked until licensed real candidate data and approved private runtimes exist. The native CPU runtime has no KV/prefix cache, GPU certification or production throughput claim. Shared cross-tenant text caches are not introduced.

`app.modules.model_platform.release` verifies the bundle and all eight checkpoint-bound gates: license, rights, provenance, training, checkpoint, evaluation, security and private runtime. It accepts an independently supplied approval and writes a new registry file exclusively; it cannot overwrite the active registry. Runtime initialization repeats artifact, tokenizer, training-lineage, evaluation and calibration binding checks. Test-only lineage, unchanged weights, missing evidence and the same checkpoint assigned to different specialist families are rejected. An empty registry means no approved models.

## API and private runtime

Customers use the existing Azaeron `/api/v1` authentication boundary:

| Route | Behavior / API-key scope |
| --- | --- |
| `POST /ai/chat`, `POST /ai/chat/stream` | One writer plus independent verifier; `ai:chat` |
| `POST /humanize` | Natural rewrite preserving facts/voice, then MeaningLock verification; `text:refine` |
| `POST /detect` | Separate calibrated detector, explicit uncertainty; `text:analyze` |
| `POST /plagiarism/check` | Version-pinned private-workspace similarity, never a plagiarism accusation; `documents:write` |
| `POST /documents/{id}/summarize`, `POST /documents/{id}/ask` | Pinned version, tenant checks and independent verification; `documents:write` |
| `GET /jobs/{id}`, `GET /models`, `GET /usage` | Existing job, capability and metering contracts |

Each mutating request requires an operation UUID. Generation uses quota reservations, encrypted replay receipts, actual model token accounting and failure release. Streams relay real tokens marked provisional; completion includes independent verification. Cancellation does not start another generation. Session/membership/key revocation is rechecked before output release. Document Q&A uses a bounded lexical candidate pass followed by the owned embedding route, returning source offsets/hashes and limited-coverage metadata. Summarization reads the pinned document with explicit context limits. No request automatically saves a document revision.

The existing interactive agent also uses the owned registry, independent chat/summary verification, closed user-selected tools and exact-candidate save receipts. Existing deterministic authorship signals abstain; they are not relabeled as an owned trained detector. Third-party local embeddings are disabled in ordinary application operation, including development. An explicit baseline-only constructor remains for offline experiments. Workspace lexical similarity remains available without making neural-quality claims.

The gateway permits private HTTPS destinations only, verifies DNS, requires mTLS, rejects redirects/proxy inheritance, bounds bodies/time/concurrency and never calls a hosted fallback. Specialist responses bind model/revision/checkpoint/calibration and validate finite normalized vectors/probabilities. Native runtime uses safetensors and mandatory client certificates; it validates the approved bundle before loading. Deployment generators support the existing pinned vLLM runtime or the native Python runtime on internal networks with no public ports, dropped privileges and offline environment. A digest-pinned, audited native runtime image and real model deployment are still **NOT FOUND / BLOCKED**.

## Current limits

Production datasets, commercial-use review records for existing bases, production checkpoints, blinded writer ratings, comparative model benchmarks and production approvals are **NOT FOUND**. Training mechanics can be exercised on this Mac; producing and certifying a capable model family requires the missing reviewed data and independently evaluated training runs. No production readiness or ranking claim follows from smoke tests, UI appearance or existing repository test counts.
