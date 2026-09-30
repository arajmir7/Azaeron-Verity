# Core intelligence attack coverage

This matrix maps test coverage, not a production security approval. The current [certification](RELEASE_CERTIFICATION.md) supplies dated outcomes and failures. One confirmed tenant leak blocks release; no such leak was observed in the executed focused agent tests.

| Boundary | Executable checks | Limit of evidence |
| --- | --- | --- |
| Cross-tenant chat IDs/search/stream/cancel/delete | `test_agent.py`, `integration/test_agent_rls.py` | API and actual non-owner PostgreSQL actor/tenant isolation. |
| Cross-tenant document IDs and RAG sources | `test_agent.py`, `test_tenant_authorization.py`, `test_postgres_rls.py` | Literal workspace retrieval, document tools and version attachments. No deployed neural RAG model was attacked. |
| Cross-tenant embeddings | Existing similarity engine/workflow tests and forced RLS | Expanded gateway embedding/rerank transport is unavailable. Deployed vector runtime isolation remains BLOCKED. |
| Prompt/tool injection | `test_private_inference.py`, `test_agent.py` | Untrusted prompt boundary, closed user-selected tools, model tool-call rejection, no implicit version save. Behavioral prompt-injection resistance of a real model remains BLOCKED. |
| Tool authorization/API-key escalation | `test_agent.py`, `test_api_keys.py`, readonly and document mutation security tests | Session-only agent endpoints, membership rechecks and scoped tool schemas. Complete production route recertification remains BLOCKED. |
| Quota races/retry/cancellation | `integration/test_usage_concurrency.py`, `test_usage.py`, `test_agent.py` | Real concurrent PostgreSQL quota checks include agent runs/tools. Durable operation identities and expired-worker replay refusal. |
| Concurrent edits/receipt forgery | Editor revision tests, agent receipt tests, PostgreSQL agent tests, live editor/similarity workflows | Exact candidate approval, immutable evidence, result lineage and conflict-safe saves. |
| Privacy erasure/RAG derivatives | `integration/test_agent_rls.py`, privacy and storage integration tests | Immediate source-erasure fencing and dependent chat/receipt/profile cleanup; local restore is separately gated. |
| SSRF/runtime egress | Private inference and zero-external-AI security tests | Private endpoint/DNS/mTLS contracts. Citation inspection and offline indexing perform no arbitrary fetches. Actual model-runtime egress attack remains BLOCKED. |
| Unsafe parsing/SQL injection/CSRF/XSS | Upload, session and security tests; agent literal-search and browser script-text checks | Known bounded parsing/authentication/rendering contracts. No general absence-of-vulnerabilities claim. |
| Scientific validity | Semantic-verification, detector evaluation and similarity fixtures | Contract evidence only. Real Humaniser fidelity, calibrated detector fairness/OOD, public semantic retrieval and model recovery are BLOCKED. |

The fixture runtime identifies itself as test-only. Its successful output is never inserted into the production model registry or represented as a measured production result. Secret findings are reviewed by exact fingerprint; no new secret exemption or image vulnerability waiver was added by this implementation.
