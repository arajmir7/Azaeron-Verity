# Controlled Qwen base: targeted technical review input

**Human technical acceptance: PENDING.** This is executed engineering evidence, not an independent human review, an owner rights decision, or production model admission. The exact controlled third-party Qwen 4-bit checkpoint SHA-256 `55467c6157306f2a4463e9d149b0ed2552943f187778cc67d02e5bef4735773d` was verified immediately before and after the probe. The base-only owner packet remains unchanged at SHA-256 `eb6f3f0615628abedd9baecd5eab2b5595e1841f844157e35a8449963c6a2314` and **PENDING**. No model weights, owner record, production registry or application source were changed.

The [protocol](protocol.json), [runner](run.py) and hashes were committed in `3e9ea1a` before generation; [seal](seal.json), [result](result.json) and [run log](run.log) are retained. The runner used MLX-LM 0.32.0 offline, greedy decoding and at most 96 generated tokens per case on the 16 GiB Mac. It did not train. Peak MLX memory was 2.308 GB; disk free after the run was 25.326 GiB.

| Targeted observation | Controlled 4-bit result |
| --- | --- |
| Explicit single-quoted negation | Exact quoted sentence and negation retained |
| Explicit double-quoted date/name | Exact quotation, name and date retained |
| No available records or tools | Said it could not determine the exact file |
| No-thinking stopping and visibility | 4/4 stopped on `<|im_end|>` (151645); no visible special/thinking tags or length stops |
| Thinking enabled | Raw `<think>` appeared and generation reached the 96-token limit; this path is not acceptable for user-facing output |

The earlier [sealed BF16 comparison](../qwen-technical-suitability-20261012/comparison.json) remains the broader task screen: BF16 15/16, 4-bit 14/16, with 12/12 predeclared engineering checks passing. Its exact protected-quotation failure occurred in **both** models and remains unresolved by the successful targeted wording above. The 4-bit model alone failed one uncertainty case in that screen. The earlier ten-prompt [logit diagnostic](../qwen-controlled-conversion-20261011/inference-comparison.json) recorded 7/10 top-token agreement, minimum cosine 0.7999 and maximum softmax total variation 0.9197. Repeated conversion hashes and matching tokenizer tokens establish lineage and operational compatibility, but **do not establish BF16/4-bit inference equivalence**. Four no-thinking stops here and 16 in the earlier screen do not prove all contexts or modes will stop safely.

**Engineering recommendation:** the controlled 4-bit bundle is a feasible subject for a *bounded, offline LoRA training trial* after separate legal base and dataset admissions, with thinking disabled, output filtering and deterministic MeaningLock rejection. That is a limited feasibility recommendation, not a `technical_review=PASS` record. A real human technical reviewer still must assess quantization drift, the prompt-dependent quotation failure, stopped/unfinished reasoning behavior, target tasks and training constraints and issue a hash-bound decision. The candidate-review schema requires `reviewer_kind=HUMAN`; this agent has not impersonated one. No commercial-quality or release suitability claim follows.
