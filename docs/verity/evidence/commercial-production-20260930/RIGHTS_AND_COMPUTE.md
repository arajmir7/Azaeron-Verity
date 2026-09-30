# Commercial candidate decision record

2026-09-30. **Zero models admitted. Zero datasets approved. No production training
executed.** This is a technical and source review, not an accountable legal approval
or independent human quality review. No customer text or external AI inference was
used. Only public cards, configuration and licenses were downloaded; weight/data
payload hashes in the dossiers are **publisher declarations, not locally verified
checkpoint hashes**. Each dossier binds the captured revision and metadata bytes.

| Intended role | Exact upstream | Current decision |
| --- | --- | --- |
| Writer candidate | [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | REVIEW_REQUIRED; Apache-2.0 declaration; 4,022,468,096 publisher parameters; native qwen3 config. |
| Writer candidate | [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) | REVIEW_REQUIRED; Apache-2.0 declaration; hybrid/multimodal architecture needs separate loader compatibility validation. |
| Writer candidate | [SmolLM3-3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | REVIEW_REQUIRED; Apache-2.0 declaration; 3,075,098,624 publisher parameters; native smollm3 config. |
| Independent baseline candidate | [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | REJECTED in its captured form: auto_map violates current admission policy. MIT does not waive the technical gate. |
| Independent baseline candidate | [Ministral-3-8B-Instruct-2512-BF16](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-BF16) | REVIEW_REQUIRED; Apache-2.0 declaration; 8,918,026,240 publisher parameters; exceeds this Mac's safe full-precision benchmark budget. |
| Embed initialization | [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | REVIEW_REQUIRED; Apache-2.0 declaration; 595,776,512 parameters; retrieval gains unmeasured. |
| Independent Verifier/Detector initialization | [DeBERTa-v3-base](https://huggingface.co/microsoft/deberta-v3-base) | REJECTED in this repository revision: no safe-tensor payload inventory. Do not unpickle unreviewed weights or invent a conversion lineage. |

These are research candidates, not proven strong internal baselines. No benchmark
winner is selected. The complete immutable revisions, primary URLs, local metadata
hashes, available payload declarations and per-model blockers are in
[the dossier index](rights-research/index.json).

Apache-2.0 candidates require review of the exact LICENSE/NOTICE, attribution,
modification notices, redistribution obligations and any additional upstream terms.
MIT candidates require preservation of the applicable copyright/license notice.
These observations do not settle third-party training-data rights, trademark,
privacy or jurisdictional questions. No model is rebranded as Azaeron; any trained
derivative must be AZAERON_DERIVATIVE with a new Azaeron-controlled checkpoint.

| Dataset | Decision and outstanding review |
| --- | --- |
| [Dolly 15k](https://huggingface.co/datasets/databricks/databricks-dolly-15k) | REVIEW_REQUIRED. CC-BY-SA-3.0 declaration; inspect contributor and source-context provenance, attribution/share-alike obligations, factual quality and PII before acquisition for training. |
| [OpenAssistant OASST1](https://huggingface.co/datasets/OpenAssistant/oasst1) | REVIEW_REQUIRED. Apache-2.0 declaration; contributor/source rights, personal data, copied passages, conversation-tree lineage and quality still require review. |
| [No Robots](https://huggingface.co/datasets/HuggingFaceH4/no_robots) | REJECTED for commercial training: CC-BY-NC-4.0 declaration. |
| [Dolci Instruct SFT](https://huggingface.co/datasets/allenai/Dolci-Instruct-SFT) | REJECTED pending source-by-source rights: aggregate ODC-BY metadata cannot establish all underlying text/generation rights. |

The production dataset registry remains empty. Real source data, author/document/
synthetic-parent lineage, allowed tasks, commercial training and derivative rights,
copyright and PII review, five disjoint splits and human sign-off are all required.
The validator now checks these additional rights/lineage fields and cross-split
5-word-shingle Jaccard similarity at 0.8. It fails closed at its bounded indexing
capacity; it does not claim to detect every semantic paraphrase.

[Compute scenarios](compute-plan.json) record the actual 16 GiB M4 Mac and proposal
dimensions for Qwen3 4B and SmolLM3 3B: LoRA/QLoRA rank 16 on seven projections,
BF16, sequence 2048, microbatch 1, accumulation 16, checkpointing, and a **planning
scenario** of 10 million tokens. GPU class: one CUDA device with 24 GiB VRAM;
host proposal: 64 GiB RAM and 150 GiB free disk. These are conservative estimates,
not a measured procurement guarantee. No CUDA device is present. QLoRA dependency
validation and sustained throughput are unexecuted; runtime cannot honestly be
estimated precisely without those measurements. No CPU training is launched to
substitute for missing rights or compute.

External requirements: accountable commercial-rights reviewer and dispositions
for exact assets; rights-reviewed real examples and evaluation data; at least two
independent human reviewers per output; actual private training/serving GPU access.
The assistant cannot attest as a human or grant a commercial license.
