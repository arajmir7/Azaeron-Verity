# Model-layer execution — 2026-10-01

**NOT PRODUCTION READY. Approved models: 0. External AI APIs: NONE.**

## Repository truth and admission

[Repo audit](repo-truth.json) verifies empty model, candidate and dataset registries. Previous exact-head [hosted run 36758345197](https://github.com/arajmir7/Azaeron-Verity/actions/runs/36758345197), commit `6632f2b2e5f418f80fbb0121c3669d30c89d61bf`, passed 11 platform gates and 12 image scans. The recorded 411 HIGH / 20 CRITICAL findings belong to historical images, not that run. This is prior-source evidence, not certification of the current patch.

[Candidate admission](candidate-admission.json) rechecks the exact local metadata hashes for three pinned upstream review candidates:

| Candidate | Immutable upstream revision | Admission |
| --- | --- | --- |
| Qwen/Qwen3-4B-Instruct-2507 | `cdbee75f17c01a7cc42f958dc650907174af0554` | BLOCKED: no accountable commercial review or verified local weight/tokenizer payload |
| HuggingFaceTB/SmolLM3-3B | `a07cc9a04f16550a088caea529712d1d335b0ac1` | BLOCKED: model-card Apache-2.0 declaration only; no LICENSE file in captured inventory, commercial review or verified payload |
| Qwen/Qwen3-Embedding-0.6B | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` | BLOCKED: model-card Apache-2.0 declaration only; no LICENSE file in captured inventory, commercial review or verified payload |

The pinned [Qwen writer LICENSE](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/resolve/cdbee75f17c01a7cc42f958dc650907174af0554/LICENSE) was retrieved again; its actual SHA-256 matches the stored notice. This verifies notice bytes, not all commercial obligations or checkpoint rights. Upstream payload hashes in the inventory remain publisher declarations; no weight/tokenizer bytes were acquired or falsely marked verified. Exact local paths, source URLs and hashes are in the JSON dossier. All candidates remain third-party assets, not Azaeron models.

[Dataset admission](dataset-rights-admission.json) remains BLOCKED: Dolly and OASST1 require accountable source/provenance/PII/copyright/commercial-rights review; no_robots is excluded for noncommercial rights and Dolci for unresolved mixed-source rights. No legal or human-review attestation was fabricated. Customer text was not read for training.

[Hardware](hardware.json): Apple arm64, 16 GiB unified memory, MPS available, CUDA absent; about 2.74 GiB memory available when measured. This is not a GPU training or latency certification.

## Fixes and verification

1. Native v1 production manifests previously bypassed v2 five-split rights controls. Native training/evaluation now delegates v2 admission to the same loader as derivatives; legacy v1 is TEST_ONLY. Both ordinary and smoke-mode attempts to use legacy production data fail before training.
2. Detector region abstention previously changed coverage/F1 but left false-positive and recall summaries using confidence alone. All decision metrics now share the region/confidence mask; raw ranking/calibration scores remain explicitly separate. Zero accepted examples yield null selective accuracy, not a perfect score.
3. An abstaining runtime previously returned class probabilities. The contract now uses HUMAN/AI/MIXED/UNCERTAIN, with null probabilities on abstention. The gateway rejects mismatched labels, probability disclosure while abstaining, and substituted checkpoint hashes.
4. Threshold selection previously repeatedly scanned all human calibration scores. Sorted scores plus binary search preserve tie behavior and reference results with O(n log n) work. Operating-point reports include conservative FPR bounds; empirical zero false positives cannot establish a low-FPR target with tiny samples.

[47 targeted tests](narrow-tests.log), [315 full backend/security tests](backend-full.log), [mypy: 197 modules](mypy.log) and [lint](lint.log) pass locally. The backend tests use current mounted source with the existing local verification image; hosted rebuilding remains the source for final dependency/image verification. Unit/mock tests do not constitute a red-team assessment of a deployed approved model. No new tenant leak was observed in the executed suite.

[Native five-split training regression](native-v2-training.log) executed all four tiny families, nine optimizer steps each, through actual optimization, safe serialization and held-out evaluation. [Checkpoint paths and hashes](native-checkpoints.json), [manifests and evaluations](native-v2-smoke/) are retained. All are TEST_ONLY; all four production evaluations are BLOCKED. The test/ OOD split hashes are separate. Detector regions remain unvalidated and its gate remains false. Training regressions verify this changed code path, not progress toward useful model quality.

[Threshold benchmark](threshold-benchmark.json) executes five repetitions at 1,000, 10,000 and 50,000 synthetic scores; the largest median is approximately 27 ms on this Mac. This is a computation microbenchmark, not inference latency, detector quality, throughput under load or a strong-baseline comparison. [Reproduction script](benchmark-reproduction.py) records seeded inputs and their hashes.

## Remaining release blockers

| Priority | State |
| --- | --- |
| P0 | Zero approved production checkpoints/data; model-backed API remains fail-closed. No capable four-family serving deployment can be certified. |
| P1 | Accountable model/data rights reviews; full payload/tokenizer verification; specialist derivative training and export/runtime compatibility; validated-region detector runtime enforcement; strong-baseline bakeoff; independent human review; private GPU/runtime/security/load evidence. |
| P2 | Context scaling, production TTFT/tokens per second, batching/KV-cache measurements and soak remain unmeasured. |

Human actions required: accountable legal/commercial review of immutable model and dataset dossiers (or a separately licensed rights-cleared corpus), access to a private CUDA host for scaled experiments, and at least two independent blinded human reviewers per writer evaluation item. No credentials should be placed in these evidence files. Review metadata alone cannot replace verified payloads and subsequent training/evaluation/security work.

Verdict: **NOT PRODUCTION READY**.
