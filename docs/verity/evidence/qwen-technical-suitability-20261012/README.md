# Controlled Qwen conversion — local technical screen

**Classification: DEV_ONLY, non-training compatibility screen.** The 16 self-authored cases, objective-marker scoring code, local paths, greedy generation parameters and screening thresholds were [sealed](seal.json) in commit `6617ca2` before either model run. The seal SHA-256 is `f9b4b5cdd15148e836b8d2a06945f89ff52f6df44fa753acfd56f6caf0e909aa`. The pinned BF16 source and controlled 4-bit bundle ran sequentially through MLX-LM 0.32.0 with offline Hub/Transformers settings and `enable_thinking=False`. This did not train, admit, promote or publish a model. No external inference API was used.

The **predeclared engineering screen PASSED** all 12 checks in [comparison.json](comparison.json): BF16 passed 15/16 objective-marker cases; controlled 4-bit passed 14/16 and 14/15 where BF16 passed. No controlled-only critical fact or injection failure occurred. All 16 prompts had identical chat-template token IDs; both models stopped with `<|im_end|>` (token 151645) in all 16 generations, with no length stop or visible thinking/special-token markup. The source's first case repeated exactly. This is a narrow local screen, not proof of logit equivalence or independently reviewed writing quality.

| Observation | BF16 source | Controlled 4-bit |
| --- | ---: | ---: |
| Objective-marker pass | 15/16 | 14/16 |
| MLX peak memory, GB | 8.142 | 2.344 |
| Warm first-token p95, seconds | 0.4424 | 0.2926 |
| Median decode, tokens/s | 12.731 | 46.791 |
| Final stop token 151645 | 16/16 | 16/16 |

Both models changed the exact single-quoted sentence `'No samples were lost.'` to double quotes on `rewrite-negation`, despite the explicit preservation instruction. This shared **MeaningLock failure** requires deterministic rejection or a stronger model before Humaniser approval. The 4-bit output alone failed `chat-uncertainty`: rather than acknowledge that the filename was unknown, it said it would check records, though no such tool was available. There was no quantized-only failure on the protected date/number/citation or prompt-injection cases in this tiny sample. Raw responses are retained only for these self-authored fixtures in [source results](source-results.json) and [controlled results](controlled-results.json).

The earlier ten-prompt [logit comparison](../qwen-controlled-conversion-20261011/inference-comparison.json) remains unresolved: 7/10 top-token agreement, minimum cosine 0.79986734 and maximum softmax total variation 0.919681. The 4-bit screen passing does **not** establish source inference equivalence, broad task suitability, human preference, commercial rights or production release readiness. The source `config.json` scalar EOS becomes a list in the conversion, but both pinned `generation_config.json` files and MLX tokenizers use stop IDs `{151643,151645}`; this run observed only 151645 stops. That addresses stopping in these 16 cases, not every Qwen3 thinking-mode path. The no-thinking chat template itself inserts a closed, empty `<think></think>` prefix before generation; generated user-visible text did not contain thinking tags here.

Installed MLX-LM also exposes higher-bit and mixed-bit conversion options. No alternative conversion or extra BF16 load was attempted after the source run because disk headroom had fallen near the 15 GiB guard. Free space measured during the runs never went below **19.127 GiB** and was approximately **20 GiB** afterward. Results are in-process, warm, short-context measurements on one Mac; they exclude API overhead, concurrency, long-context scaling and sustained load. The owner base decision remains pending, Writer dataset rows admitted remain zero, and the production registry remains unchanged.
