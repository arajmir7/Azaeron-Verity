# Similarity review

Open a document and choose **Review similarity**, or use
`/similarity?document=<id>&version=<version-id>`.

The workflow compares only indexed documents in the active private workspace.
It displays unique-word overlap, four quotation/citation match groups, ranked
source versions, exact source/target passages, review flags and reproducible
exclusions. It does not determine plagiarism, misconduct, intent or AI use.

## Available corpus

- `PRIVATE_WORKSPACE`: indexed, non-archived documents in the active tenant,
  excluding every version of the target document. Historical source versions
  retain their own identities and fingerprints.
- `PUBLIC_METADATA`: the existing citation resolver can retrieve bibliographic
  metadata. This is not a full-text similarity corpus and is not searched here.
- `AUTHORIZED_CORPUS`: reserved source category; currently `UNAVAILABLE` because
  no authorized external full-text provider is connected.
- `UNAVAILABLE`: no usable comparison corpus. The percentage is `null`, not 0%.

No corpus, benchmark coverage or scholarly-content license is fabricated.

## Evidence and calculation

The similarity service indexes overlapping, word-aligned text windows, retrieves
candidates through a tenant-filtered inverted index and verifies only the bounded
ranked candidates. Token retrieval scores now use the same keys as ranking;
ngram queries preserve token order and repetition. Shape resemblance alone is
not a match. At least five consecutive normalized words must align; Unicode
normalization affects comparison only, never the stored offset coordinates.
Repeated target passages can each match one source passage.

Every match has a deterministic UUID derived from tenant, target/source versions,
exact offsets and pipeline version. Source/target snippets, version content hashes,
processed-text hashes, source title, retrieval time, provider versions and canonical
evidence references are retained. Overlapping collinear windows are coalesced.
Other overlapping matches remain inspectable, but each target word counts once.

`percentage = 100 × unique included target words / eligible target words`

Words are Unicode word tokens, not bytes or whitespace-delimited approximations.
Offsets are zero-based, end-exclusive Python Unicode character indices into
`ProcessedDocument.cleaned_text`. JavaScript consumers must account for surrogate
pairs when slicing: `Array.from(text).slice(start, end).join("")`.

Quote, bibliography and cited-sentence exclusions remove words from both numerator
and denominator. Minimum-match and source exclusions remove evidence from the
numerator only. Partial exclusions trim coverage rather than discard a whole
partially quoted match. A zero denominator produces `null`. Group and source
percentages can overlap and must not be added.

Quote and nearby citation-marker recognition are explicitly experimental.
Supported marks include paired straight/curly quotation marks and Markdown block
quotes; numeric brackets and parenthetical author/year syntax identify nearby
citation markers. Proximity does not establish that the citation identifies the
matched source. Missing-quotation and missing-citation flags request human review.
Their rule version and original classification are stored in the match evidence.

## Reproducibility and bounds

`SimilarityAnalysis` freezes the completed result for one target version and
pipeline. Repeat requests return that snapshot. Newly indexed sources do not
silently change its score. A snapshot records its index cutoff, corpus version
count, candidate identity digest and work limits. Exclusion settings are canonical
JSON with a rules version and analysis-bound SHA-256 fingerprint; they also live
in the review URL. Changing exclusions never destroys recorded matches.

Current bounds: 200 retrieved candidates/window, 25 verified candidates/window,
400 analyzed target windows and 2,000 stored matches. Reaching a bound is displayed
as a bounded search with lower-bound evidence coverage. Incremental indexing is
linear in the input; no all-pairs document scan is used. The candidate lookup has
a composite tenant/index/type/term index. This is not a latency or recall benchmark.

## APIs

All routes require active workspace authentication and validate the requested
version belongs to the authorized document. An omitted version resolves to the
latest document version, without silently falling back to an older analysis.

- `GET /api/v1/similarity/documents/{doc_id}/analysis`: summary, source categories,
  groups, review flags, exclusions and paginated sources/matches.
- `POST /api/v1/similarity/documents/{doc_id}/analysis?document_version_id=...`:
  analyze already extracted text, restricted to users permitted to mutate the
  document. Existing completed snapshots are reused. New uploads run the same
  service through the existing worker.
- `GET /api/v1/similarity/documents/{doc_id}/matches/{match_id}?document_version_id=...`:
  exact evidence for a version-bound match, including canonical graph node ID.
- `GET /api/v1/similarity/documents/{doc_id}/matches`: compatible legacy match
  listing, now version-scoped and paginated. Historical rows without a frozen
  workflow snapshot are not used to fabricate a summary percentage.

Analysis query controls: `document_version_id`, `page`, `page_size` (1–100),
`source_page`, `source_page_size` (1–100), `group`, `source_version_id`,
`show_excluded`, `exclude_quotes`, `exclude_cited`, `exclude_bibliography`,
`min_match_words` (5–100), repeated `excluded_source_version_ids` (maximum 100).
Pagination/group/source filters do not alter the overall summary; exclusions do.
The legacy match listing supports page sizes up to 200.

## Supporting changes and boundaries

Migration `20260913_0023` adds the tenant-RLS-protected snapshot table, source-version
and analysis links, the lookup index, and per-version processed-text uniqueness.
It preserves existing data. Downgrade refuses to restore document-wide uniqueness
when multiple processed versions exist, rather than deleting history.

Text processing preserves line boundaries so quotation/bibliography exclusions
have real structure to inspect; its pipeline version is now `document-processing-v3`.
Older processed text remains unchanged and its limitation is displayed. Worker
fingerprints and graph source references now use the requested immutable version.

This work adds only the Similarity workflow. It does not connect Write to re-check,
train a detector, add semantic paraphrase detection, fetch external full-text
corpora or redesign the other analysis modules. Existing generic detector/citation
views still have the independent version/state gaps recorded in the product audit.
