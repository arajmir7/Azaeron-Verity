# AI capability truth

WRITE currently uses `editorial-rules-v2-protected-spans`: deterministic substitutions and grammar
rules with persisted suggestions. It is not a self-hosted LLM. Detection combines
observable signals and explicit unavailable states; no trained, calibrated
production detector is supplied. MiniLM assets are local and hash checked but
experimental; embeddings do not establish factual preservation or authorship.

Production model adoption requires exact model/tokenizer/runtime revisions,
license review, hardware measurements, provenance-labelled datasets, calibration,
fairness/robustness results and an approved registry record. No model may be
silently selected or promoted. No external detector or AI API is permitted.

Refinement invariants must protect quotations, identifiers, numbers, citations,
code and explicitly locked spans before any rewrite; verify deterministically
afterwards. Independent local semantic verification remains a model release gate.
