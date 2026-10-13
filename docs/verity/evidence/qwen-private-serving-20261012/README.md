# Controlled Qwen local HTTP serving — 12 October 2026

**DEV_ONLY measurement; production serving NOT CERTIFIED.** The original synthetic workload was [sealed](seal.json) before the complete run. The exact controlled 4-bit `model.safetensors` SHA-256 was verified before and after serving: `55467c6157306f2a4463e9d149b0ed2552943f187778cc67d02e5bef4735773d`. MLX-LM 0.32.0 loaded the local path with offline Hub settings, no remote code, no external AI API, and a listener on `127.0.0.1:18080` only. The temporary service was stopped after the run. It did not touch the original Qwen bundle, the application server, customer data, or the production model registry.

The first sealed attempt completed its generation stages but hit an MLX-LM 0.32.0 behavior: a malformed request missing `messages` raised `AssertionError` in the server request thread and abruptly closed the connection. It is retained in [attempt-1.json](attempt-1.json). The harness was amended and resealed before the second complete run. The malformed request again returned `REMOTE_DISCONNECT`, and the next valid streamed request completed with HTTP 200. Closing a stream after the first visible delta caused a server-side `BrokenPipeError`; the next valid streamed request also completed with HTTP 200. [Selected process-output excerpts](server-log-excerpts.txt) preserve the error messages. These recoveries establish only that this local server process remained usable; malformed-input handling is not production-grade.

| Warm HTTP result | Measurement |
| --- | ---: |
| Serial streamed requests | 12/12 completed, `stop` finish, zero visible `<think>` markers |
| Serial first-visible-token p95 | 364.43 ms |
| Serial end-to-end p95 | 1,024.97 ms |
| Approximate serial decode median | 37.82 tokens/s |
| Two concurrent requests, four rounds, wall p95 | 1,449.20 ms |
| Four concurrent requests, two rounds, wall p95 | 3,106.85 ms |
| Process physical footprint / observed peak | 2,474 MB after / 2,614 MB peak |
| Free disk before run | 20.228 GiB |

The server was configured with one prompt and one decode worker; concurrent calls therefore mainly measured queueing on this 16 GiB shared Mac. The [result](result.json) retains individual timings, token counts, response hashes, concurrency rounds, and recovery outcomes without raw generated text. The server's `/v1/models` advertised both a publisher alias and the local path; every generation request used the **exact local path**, and the benchmark checked its response identity. A disk hash and process command do not cryptographically attest the bytes resident in memory.

This is a small, warm, short-context test of the raw MLX HTTP server. It excludes authenticated Azaeron API overhead, mTLS, sustained load, long-context behavior, production isolation, independent quality review, and an approved Azaeron checkpoint. MLX-LM itself warns that its basic HTTP server is not recommended for production. No production SLO, owner admission, or commercial release claim follows from these numbers.
