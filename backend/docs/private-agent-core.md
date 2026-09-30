# Private agent core

Implemented September 29, 2026. This document records implementation boundaries, not production certification. See [release certification](../../docs/verity/RELEASE_CERTIFICATION.md) for executed evidence and blockers.

## Request and execution

`/api/v1/ai/conversations` supports actor-private list/title search and creation; `/{id}` supports read, rename and deletion. `/{id}/messages` reads or admits immutable messages. Admission requires an interactive session, current workspace editorial-write permission, a closed schema, caller operation UUID, quota reservation and audit event. Reusing an operation with different content is rejected. A conversation has one active run. Edited prompts append messages referencing previous prompts.

The Celery document-processing queue executes admitted runs. Delivery repeats never repeat generation. Workers recheck membership/session, poll cancellation during inference, and recheck before committing output. No document lock is held across a model request. Expired runs reconcile on a new request, conversation read or SSE reconnect; there is no continuous background run reconciler. `/api/v1/ai/runs/{id}/cancel` stops pending work and requests interruption of running work.

`/{id}/stream?run_id=...` emits durable SSE events (`queued`, `started`, `tool`, `delta`, `message`, `result`, `done`). Run-scoped sequence IDs support `Last-Event-ID` replay. Chunks remain provisional until model identity, usage and finish reason validate. Failure discards provisional output. Connections periodically reauthenticate and release their database connection before writing frames.

## Data and authorization

Migrations 0037–0039 add conversations, immutable messages, runs, calls/results, version attachments, events, receipts and voice profiles. Every table has organization/actor scope and forced PostgreSQL RLS. Parent relationships include scope. Chats and profiles are actor-private inside shared workspaces. Document access retains workspace permission semantics. Attachments pin immutable versions and normalized input hashes.

Triggers guard lineage and immutable evidence. Pending source erasure immediately hides derived chats, receipts and profiles through restrictive policies; privacy execution then removes them. Conversation deletion retains independent receipts and accepted document history. Document erasure removes dependent receipts/conversations. Future retrieval adapters must register every source dependency before exposing content.

The closed tool set is `document.search`, `document.read`, `document.summarize`, `document.compare`, `writing.refine`, `detection.analyze`, `similarity.analyze`, `similarity.resolve`, `citation.inspect`, and `document.create_version`. Only authenticated UI intent chooses tools. Model output cannot execute a tool. Search is bounded literal workspace title/filename search. Citation inspection reads existing evidence without arbitrary URL fetching. Prompts label retrieved history/documents as untrusted data. API keys cannot use interactive agent endpoints.

## Candidate, verification and receipt

Refinement extracts protected spans before one writer generation, checks invariants and independently verifies changed text. Selection bounds preserve surrounding text. VoiceLock supplies bounded numeric style statistics derived from approved owned versions, rechecking ownership/hashes. This is not benchmarked voice fidelity or comprehensive multilingual name extraction.

Candidates cannot create revisions by themselves. Receipts persist actor/workspace, source document/version, input/candidate hashes, candidate text/diff, model/policy evidence, tool arguments, protected spans, verification, decision and result version/hash. Approval requires the exact candidate hash and uses conflict-safe immutable saves. Unavailable, failed or uncertain generative verification blocks acceptance. Saving an existing model reply uses `USER_REVIEW_REQUIRED` and makes no semantic/factual proof claim. Existing deterministic editorial acceptance records its limited evidence too.

Resolve Match supports citation, quotation/citation, attributed paraphrase, duplicate removal and justified retention. Paraphrase needs private generation and verification. Human approval precedes all revisions; accepted resolutions rerun workspace similarity and retain both reports. Concurrent edits produce a conflict.

## Model and corpus boundaries

The registry recognizes chat, summarize, refine, extract, classify, embed, rerank and verify. Chat has private-runtime SSE transport. Embedding and reranking transport in this gateway remains unavailable; task registration is not a deployed capability. Existing workspace similarity retrieval remains separate. Deployment manifests retain private networks and mTLS. No external inference fallback exists.

`scripts/model_bakeoff.py` requires at least two commercially approved candidates and a rights-reviewed dataset. It records actual private-runtime outcomes when supplied. The current empty registry cannot produce a winner. RAM/VRAM measurements, concurrency/recovery campaigns and human semantic adjudication remain incomplete. The script does not promote models.

Corpus classes are PRIVATE_WORKSPACE, PUBLIC_WEB, OPEN_SCHOLARLY and LICENSED_SCHOLARLY. Only workspace coverage is available. `scripts/index_public_corpus.py` builds a new offline SQLite snapshot from supplied text with license, permission, rights-review and content-hash records. It normalizes text, canonicalizes URLs, deduplicates content and builds shingles, MinHash and lexical retrieval. It does not crawl/fetch. Public semantic retrieval, deployment and corpus-scale relevance evaluation remain unavailable.

The detector abstains without approved production calibration. Existing ensemble/dataset/evaluation code and fixture tests do not establish trained-classifier, fairness, OOD or production quality evidence.

## Operations

Worker metrics record queue wait, first-token time, run/tool duration, reported tokens and failures using bounded labels. Grafana includes these series. GPU/model queue panels require actual DCGM/runtime exporters. Local tests cannot certify production SLOs, runtime egress, offsite recovery, SMTP delivery, screen-reader speech or production soak.
