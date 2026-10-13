# arXivEdits commercial-license filter — 12 October 2026

**QUARANTINED_REVIEW_ONLY; zero rows admitted, zero training authorized.** The [publisher repository pinned at `113913d68522c1c8428d8e191d5c9bed633da6ce`](https://github.com/chaojiang06/arXivEdits/tree/113913d68522c1c8428d8e191d5c9bed633da6ce) contains human scientific sentence revisions with arXiv paper IDs. Its [README](https://github.com/chaojiang06/arXivEdits/blob/113913d68522c1c8428d8e191d5c9bed633da6ce/README.md) says `sentence_alignment` records each version's license. The source files' six verified SHA-256 values and the exact filter are in [audit-summary.json](audit-summary.json); [audit.py](audit.py) reproduces the counts without exporting text.

The filter requires **both** source and revised paper-version licenses to be publisher-recorded CC BY 3.0/4.0, CC0 or public domain. It excludes arXiv nonexclusive-distribution, assumed, noncommercial, share-alike, missing and mixed-permission version pairs. The published edit files have 600/200/200 train/dev/test rows. Paper IDs are disjoint across those splits. Only **18 train edits** have matching papers whose first two versions pass this provisional license filter; **zero** dev and **zero** test edits do. This is a license-metadata screen, not a confirmation that every sentence maps to those two versions or that a paper contains no third-party content. Row-level privacy, copyright and quality review has not occurred.

The 18 possible edits cover scientific sentence revision only. They cannot support held-out evaluation, CAL/OOD, general rewriting, Humaniser voice, chat, summarization or grounded document Q&A. No five-way Writer dataset or owner-reviewable admission was produced. Downloaded source text remains only in `/private/tmp/azaeron-arxiv-edits-audit-20261012`.

To reproduce, fetch the six exact `data/edits/{train,dev,test}.json` and `data/sentence_alignment/{train,dev,test}.json` files from the pinned repository revision, then run:

```bash
python3 docs/verity/evidence/new-data-arxiv-edits-20261012/audit.py \
  --source-dir /private/tmp/azaeron-arxiv-edits-audit-20261012 \
  --summary /private/tmp/azaeron-arxiv-edits-audit-rerun.json
```
