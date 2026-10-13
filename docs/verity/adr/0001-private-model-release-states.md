# ADR 0001 — Separate local preview from commercial model admission

**Status:** Accepted as the current engineering boundary, 2026-10-11. **Scope:** PRD-006/013/014/021, TRD-006/013/014/021.

## Context

The first-party API, auth/RLS/quota controls and private inference gateway already exist. A third-party Qwen3-4B MLX checkpoint generates useful local responses, but its integration is DEV_ONLY, its outputs are UNVERIFIED, and no rights-reviewed training corpus, independent approved Verifier or production checkpoint is available. The production route registry is empty. An unchanged base checkpoint cannot honestly become an Azaeron-owned model by renaming it.

## Decision

Keep the existing architecture and distinct states: `BASELINE`/`TEST_ONLY` assets for engineering evidence, `DEV_ONLY` loopback preview, `CANDIDATE` only after an Azaeron-controlled training run with rights and immutable lineage, and `APPROVED` only after all release gates and accountable approval. Production gateway reads only APPROVED hash-bound routes; no fallback to DEV_ONLY, external AI API or unapproved local weight. Writer and Verifier checkpoint identities must be independent; on verifier failure the output remains UNVERIFIED. The UI and receipt show actual state, including source coverage and human acceptance.

## Consequences and alternatives

This lets local users exercise chat, stream, rewriting and grounded document actions without claiming commercial readiness. It leaves production intelligence unavailable until rights, training, benchmarks, blinded review, private serving and security are proven. We rejected (a) relabeling Qwen, (b) using the Writer as its own Verifier, and (c) hosted AI fallback, because each violates the provenance or trust contract. A new GPU runtime may implement the existing private inference contract without changing public API or tenancy boundaries.

**Verification:** `backend/tests/test_dev_mlx.py`, `backend/tests/security/test_zero_external_ai.py`, `backend/tests/test_model_layer_hardening.py`, and the release registry admission checks. This ADR records a boundary, not a model approval.
