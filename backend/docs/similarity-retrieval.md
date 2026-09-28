# Similarity retrieval engine

The current implementation is documented in [Similarity review](similarity-workflow.md).
It extends the existing tenant-local inverted index with immutable analysis snapshots,
source-version provenance, deterministic match identities, overlapping word-aligned
windows and exact token-span verification. Only contiguous lexical evidence contributes
to coverage; structural resemblance and unvalidated semantic providers do not.

The workflow supports source ranking, four quotation/citation groups, exact side-by-side
passages, reproducible exclusions and paginated results. Retrieval/verification limits
are explicit. No whole-web or scholarly-corpus coverage is claimed.

`benchmark_retrieval` remains a resource/bounds harness. Its synthetic smoke checks are
not evidence of representative precision, recall or production latency.
